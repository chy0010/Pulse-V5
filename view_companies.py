import os
import json
import sys
import webbrowser
from datetime import datetime, timezone

REPORTS_DIR = "reports"
OUTPUT_PATH = "website/companies.html"


def load_report(target_date=None):
    if target_date:
        path = os.path.join(REPORTS_DIR, f"{target_date}_companies.json")
    else:
        files = sorted([
            f for f in os.listdir(REPORTS_DIR) if f.endswith("_companies.json")
        ], reverse=True)
        if not files:
            print("No company reports found. Run analyze_companies.py first.")
            sys.exit(1)
        path = os.path.join(REPORTS_DIR, files[0])

    with open(path) as f:
        return json.load(f)


def escape_html(text):
    if not text:
        return ""
    return (str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;"))


def sentiment_color(s):
    return {
        "positive": "#2e7d32",
        "negative": "#c0392b",
        "mixed": "#b8860b",
        "neutral": "#5a6a7a",
    }.get(s, "#5a6a7a")


def type_label(t):
    return {
        "company": "Company",
        "technology": "Technology",
        "product": "Product",
        "brand": "Brand",
        "person": "Person",
        "gpu": "GPU",
        "ai_model": "AI Model",
        "platform": "Platform",
        "event": "Event",
        "policy": "Policy",
        "other": "Other",
    }.get(t, t.replace("_", " ").capitalize() if t else "Other")


def generate_html(report):
    today_str = report["date"]
    entity_count = report["entity_count"]
    entities = report["entities"]

    try:
        dt = datetime.strptime(today_str, "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y").upper()
    except Exception:
        display_date = today_str.upper()

    # Separate by type for filters
    companies = [e for e in entities if e.get("type") in ("company", "brand")]
    technologies = [e for e in entities if e.get("type") == "technology"]
    products = [e for e in entities if e.get("type") == "product"]

    # Build entity cards
    def render_card(entity):
        name = escape_html(entity.get("name", ""))
        ticker = entity.get("ticker")
        etype = entity.get("type", "other")
        mentions = entity.get("mention_count", 0)
        sentiment = entity.get("sentiment", "neutral")
        t1 = entity.get("tier1_mentions", False)
        t2 = entity.get("tier2_mentions", False)
        why = escape_html(entity.get("why_talking", ""))
        raw_what = entity.get("what_saying", "")
        quotes = entity.get("key_quotes", [])
        # what_saying can be a list of bullets or a legacy string
        if isinstance(raw_what, list):
            what_bullets = raw_what
            what = escape_html(" ".join(raw_what))  # for data-what search attr
        else:
            what_bullets = []
            what = escape_html(raw_what)

        s_color = sentiment_color(sentiment)
        type_lbl = type_label(etype)
        ticker_html = f'<span class="ticker">{escape_html(ticker)}</span>' if ticker else ""
        t1_badge = '<span class="tier-badge t1">Tier 1</span>' if t1 else ""
        t2_badge = '<span class="tier-badge t2">Tier 2</span>' if t2 else ""

        quotes_html = ""
        for q in quotes[:3]:
            quotes_html += f'<div class="quote">&ldquo;{escape_html(q)}&rdquo;</div>\n'

        return f"""<div class="entity-card" data-type="{etype}" data-sentiment="{sentiment}" data-name="{name.lower()}" data-why="{why.lower()}" data-what="{what.lower()}">
  <div class="card-header">
    <div class="card-title-row">
      <span class="entity-name">{name}</span>
      {ticker_html}
      <span class="type-badge">{type_lbl}</span>
    </div>
    <div class="card-meta-row">
      <span class="mention-count"><strong>{mentions}</strong> mentions</span>
      <span class="sentiment-dot" style="background:{s_color};"></span>
      <span class="sentiment-label" style="color:{s_color};">{sentiment.capitalize()}</span>
      {t1_badge}{t2_badge}
    </div>
  </div>
  <div class="card-body">
    <div class="section-label">Why they're talking about it</div>
    <p class="why-text">{why}</p>
    <div class="section-label">What they're saying</div>
    {'<ul class="what-bullets">' + ''.join(f'<li>{escape_html(b)}</li>' for b in what_bullets) + '</ul>' if what_bullets else f'<p class="what-text">{what}</p>'}
    {f'<div class="section-label">Key quotes</div><div class="quotes-block">{quotes_html}</div>' if quotes else ''}
  </div>
</div>"""

    all_cards_html = "\n".join(render_card(e) for e in entities)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Market Pulse — Companies & Tech — {today_str}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@400;600;700&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:       #f9f7f4;
      --surface:  #ffffff;
      --border:   #e2ddd7;
      --border-strong: #c8c2b8;
      --ink:      #0f0f0f;
      --ink-soft: #3a3835;
      --ink-dim:  #6b6760;
      --muted:    #9a9590;
      --navy:     #1a3052;
      --navy-mid: #2a4a72;
      --green:    #2e7d32;
      --red:      #c0392b;
      --gold:     #b8860b;
    }}

    html {{ scroll-behavior: smooth; }}

    body {{
      background: var(--bg);
      color: var(--ink);
      font-family: 'Inter', -apple-system, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }}

    /* ── TOPBAR ── */
    .topbar {{
      background: var(--navy);
      padding: 0.55rem 2.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .topbar-brand {{
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: #ffffff;
    }}

    .topbar-brand span {{ color: #7fa8d4; }}

    .topbar-nav {{
      display: flex;
      gap: 1.5rem;
    }}

    .topbar-nav a {{
      font-size: 0.65rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #7fa8d4;
      text-decoration: none;
    }}

    .topbar-nav a.active {{ color: #ffffff; font-weight: 600; }}
    .topbar-nav a:hover {{ color: #ffffff; }}

    /* ── HEADER ── */
    header {{
      background: var(--surface);
      border-bottom: 3px solid var(--navy);
      padding: 2rem 2.5rem 1.6rem;
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 2rem;
      flex-wrap: wrap;
    }}

    .header-left {{ flex: 1; }}

    .report-label {{
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.25em;
      text-transform: uppercase;
      color: var(--navy-mid);
      margin-bottom: 0.4rem;
    }}

    .masthead {{
      font-family: 'Playfair Display', Georgia, serif;
      font-weight: 700;
      font-size: clamp(1.6rem, 3vw, 2.4rem);
      color: var(--ink);
      line-height: 1.1;
    }}

    .masthead span {{ color: var(--navy); }}

    .tagline {{
      margin-top: 0.4rem;
      font-size: 0.78rem;
      color: var(--ink-dim);
    }}

    .header-stats {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      align-items: flex-end;
    }}

    .stat-chip {{
      background: var(--bg);
      border: 1px solid var(--border);
      padding: 0.35rem 0.9rem;
      font-size: 0.7rem;
      font-weight: 500;
      letter-spacing: 0.08em;
      color: var(--ink-dim);
      text-transform: uppercase;
    }}

    .stat-chip strong {{
      color: var(--navy);
      font-weight: 700;
    }}

    /* ── DATE STRIP ── */
    .dateline {{
      background: var(--navy);
      padding: 0.65rem 2.5rem;
      display: flex;
      align-items: center;
      gap: 2rem;
      flex-wrap: wrap;
    }}

    .dateline .date {{
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: #ffffff;
    }}

    .dateline .meta {{
      font-size: 0.65rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #7fa8d4;
    }}

    .divider-pipe {{
      width: 1px;
      height: 12px;
      background: #3a5a7a;
    }}

    /* ── CONTROLS ── */
    .controls {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 0.9rem 2.5rem;
      display: flex;
      align-items: center;
      gap: 1.2rem;
      flex-wrap: wrap;
      position: sticky;
      top: 0;
      z-index: 100;
    }}

    .search-wrap {{
      flex: 1;
      min-width: 200px;
      max-width: 380px;
      position: relative;
    }}

    .search-wrap input {{
      width: 100%;
      padding: 0.5rem 0.9rem 0.5rem 2.2rem;
      border: 1px solid var(--border-strong);
      background: var(--bg);
      font-family: 'Inter', sans-serif;
      font-size: 0.82rem;
      color: var(--ink);
      outline: none;
    }}

    .search-wrap input:focus {{ border-color: var(--navy-mid); }}

    .search-icon {{
      position: absolute;
      left: 0.65rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--muted);
      font-size: 0.75rem;
      pointer-events: none;
    }}

    .filter-group {{
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
    }}

    .filter-btn {{
      padding: 0.4rem 0.9rem;
      font-family: 'Inter', sans-serif;
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      border: 1px solid var(--border-strong);
      background: transparent;
      color: var(--ink-dim);
      cursor: pointer;
    }}

    .filter-btn.active {{
      background: var(--navy);
      border-color: var(--navy);
      color: #ffffff;
    }}

    .filter-btn:hover:not(.active) {{
      border-color: var(--navy-mid);
      color: var(--navy-mid);
    }}

    .sentiment-filter {{
      padding: 0.4rem 0.9rem;
      font-family: 'Inter', sans-serif;
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      border: 1px solid var(--border-strong);
      background: var(--bg);
      color: var(--ink-dim);
      cursor: pointer;
      outline: none;
    }}

    .results-count {{
      font-size: 0.68rem;
      color: var(--muted);
      letter-spacing: 0.06em;
      margin-left: auto;
    }}

    /* ── PAGE WRAP ── */
    .page-wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 2.5rem 2.5rem 6rem;
    }}

    /* ── SUMMARY STRIP ── */
    .summary-strip {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}

    .summary-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-top: 3px solid var(--navy);
      padding: 1rem 1.2rem;
      text-align: center;
    }}

    .summary-card .big {{
      font-family: 'Playfair Display', serif;
      font-size: 2rem;
      font-weight: 700;
      color: var(--navy);
      line-height: 1;
    }}

    .summary-card .big.green {{ color: var(--green); }}
    .summary-card .big.red {{ color: var(--red); }}
    .summary-card .big.gold {{ color: var(--gold); }}

    .summary-card .lbl {{
      font-size: 0.62rem;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
      margin-top: 0.3rem;
    }}

    /* ── CARD GRID ── */
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1.2rem;
    }}

    /* ── ENTITY CARD ── */
    .entity-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      overflow: hidden;
      transition: box-shadow 0.15s;
    }}

    .entity-card:hover {{
      box-shadow: 0 4px 16px rgba(26,48,82,0.1);
    }}

    .entity-card.hidden {{ display: none; }}

    .card-header {{
      background: var(--navy);
      padding: 0.9rem 1.2rem 0.8rem;
    }}

    .card-title-row {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      flex-wrap: wrap;
      margin-bottom: 0.5rem;
    }}

    .entity-name {{
      font-size: 0.95rem;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: 0.01em;
    }}

    .ticker {{
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      color: #7fa8d4;
      background: rgba(127,168,212,0.15);
      border: 1px solid rgba(127,168,212,0.3);
      padding: 0.15rem 0.5rem;
    }}

    .type-badge {{
      font-size: 0.58rem;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: #a0b8d0;
      border: 1px solid rgba(160,184,208,0.3);
      padding: 0.15rem 0.5rem;
    }}

    .card-meta-row {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      flex-wrap: wrap;
    }}

    .mention-count {{
      font-size: 0.68rem;
      color: #a0b8d0;
    }}

    .mention-count strong {{
      color: #ffffff;
      font-weight: 700;
    }}

    .sentiment-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }}

    .sentiment-label {{
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }}

    .tier-badge {{
      font-size: 0.58rem;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 0.1rem 0.4rem;
    }}

    .tier-badge.t1 {{
      background: rgba(46,125,50,0.25);
      color: #81c784;
      border: 1px solid rgba(46,125,50,0.3);
    }}

    .tier-badge.t2 {{
      background: rgba(184,134,11,0.2);
      color: #ffd54f;
      border: 1px solid rgba(184,134,11,0.3);
    }}

    /* ── CARD BODY ── */
    .card-body {{
      padding: 1.1rem 1.2rem;
    }}

    .section-label {{
      font-size: 0.6rem;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--navy-mid);
      margin-bottom: 0.35rem;
      margin-top: 0.9rem;
    }}

    .section-label:first-child {{ margin-top: 0; }}

    .what-bullets {{
      margin: 0;
      padding-left: 1.1rem;
      list-style: disc;
    }}

    .what-bullets li {{
      font-size: 0.84rem;
      color: var(--ink-soft);
      line-height: 1.6;
      margin-bottom: 0.3rem;
    }}

    .why-text, .what-text {{
      font-size: 0.84rem;
      color: var(--ink-soft);
      line-height: 1.65;
    }}

    .quotes-block {{
      margin-top: 0.3rem;
    }}

    .quote {{
      font-size: 0.8rem;
      color: var(--ink-dim);
      font-style: italic;
      padding: 0.45rem 0.7rem;
      border-left: 2px solid var(--border-strong);
      margin-bottom: 0.4rem;
      background: var(--bg);
      line-height: 1.55;
    }}

    /* ── NO RESULTS ── */
    .no-results {{
      text-align: center;
      padding: 4rem;
      color: var(--muted);
      font-size: 0.85rem;
      display: none;
      grid-column: 1 / -1;
    }}

    /* ── FOOTER ── */
    footer {{
      background: var(--navy);
      text-align: center;
      padding: 1.6rem 2rem;
      font-size: 0.65rem;
      font-weight: 500;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: #7fa8d4;
    }}

    footer strong {{ color: #ffffff; font-weight: 600; }}

    .back-top {{
      position: fixed;
      bottom: 2rem;
      right: 2rem;
      width: 38px;
      height: 38px;
      background: var(--navy);
      color: #ffffff;
      font-size: 0.9rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: opacity 0.3s;
      border: none;
    }}

    .back-top.visible {{ opacity: 1; }}
    .back-top:hover {{ background: var(--navy-mid); }}
  </style>
</head>
<body>

  <div class="topbar">
    <span class="topbar-brand">Market <span>Pulse</span></span>
    <nav class="topbar-nav">
      <a href="index.html">Intelligence Report</a>
      <a href="comments.html">All Comments</a>
      <a href="companies.html" class="active">Companies &amp; Tech</a>
    </nav>
  </div>

  <header>
    <div class="header-left">
      <p class="report-label">Entity Intelligence</p>
      <h1 class="masthead"><span>Companies</span> &amp; Tech</h1>
      <p class="tagline">Every company, brand, and technology real consumers are talking about — extracted from {report.get("entity_count", 0):,} entities across 9,789 comments</p>
    </div>
    <div class="header-stats">
      <div class="stat-chip"><strong>{entity_count:,}</strong> entities tracked</div>
      <div class="stat-chip"><strong>{len(companies):,}</strong> companies &amp; brands</div>
      <div class="stat-chip"><strong>{len(technologies) + len(products):,}</strong> technologies &amp; products</div>
    </div>
  </header>

  <div class="dateline">
    <span class="date">{display_date}</span>
    <span class="divider-pipe"></span>
    <span class="meta">Sorted by mention count</span>
    <span class="divider-pipe"></span>
    <span class="meta">AI-extracted from consumer comments</span>
  </div>

  <div class="controls">
    <div class="search-wrap">
      <span class="search-icon">🔍</span>
      <input type="text" id="searchInput" placeholder="Search companies, tickers, tech..." autocomplete="off" />
    </div>
    <div class="filter-group">
      <button class="filter-btn active" data-filter="all">All</button>
      <button class="filter-btn" data-filter="company">Companies</button>
      <button class="filter-btn" data-filter="technology">Tech</button>
      <button class="filter-btn" data-filter="gpu">GPUs</button>
      <button class="filter-btn" data-filter="ai_model">AI Models</button>
      <button class="filter-btn" data-filter="product">Products</button>
      <button class="filter-btn" data-filter="person">People</button>
      <button class="filter-btn" data-filter="platform">Platforms</button>
    </div>
    <select class="sentiment-filter" id="sentimentFilter">
      <option value="all">All Sentiment</option>
      <option value="positive">Positive</option>
      <option value="negative">Negative</option>
      <option value="mixed">Mixed</option>
      <option value="neutral">Neutral</option>
    </select>
    <span class="results-count" id="resultsCount">{entity_count:,} entities</span>
  </div>

  <div class="page-wrap">

    <div class="summary-strip">
      <div class="summary-card">
        <div class="big">{entity_count}</div>
        <div class="lbl">Total Entities</div>
      </div>
      <div class="summary-card">
        <div class="big">{len(companies)}</div>
        <div class="lbl">Companies &amp; Brands</div>
      </div>
      <div class="summary-card">
        <div class="big">{len(technologies)}</div>
        <div class="lbl">Technologies</div>
      </div>
      <div class="summary-card">
        <div class="big green">{len([e for e in entities if e.get("sentiment") == "positive"])}</div>
        <div class="lbl">Positive Sentiment</div>
      </div>
      <div class="summary-card">
        <div class="big red">{len([e for e in entities if e.get("sentiment") == "negative"])}</div>
        <div class="lbl">Negative Sentiment</div>
      </div>
      <div class="summary-card">
        <div class="big gold">{len([e for e in entities if e.get("sentiment") == "mixed"])}</div>
        <div class="lbl">Mixed Sentiment</div>
      </div>
    </div>

    <div class="card-grid" id="cardGrid">
{all_cards_html}
      <div class="no-results" id="noResults">No entities match your search.</div>
    </div>

  </div>

  <footer>
    <strong>Market Pulse</strong> &nbsp;·&nbsp; Built by Krishna &nbsp;·&nbsp; {today_str}
  </footer>

  <button class="back-top" id="backTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">↑</button>

  <script>
    let currentType = 'all';
    let currentSentiment = 'all';
    let searchTerm = '';

    const cards = document.querySelectorAll('.entity-card');
    const resultsCount = document.getElementById('resultsCount');
    const noResults = document.getElementById('noResults');

    function applyFilters() {{
      let visible = 0;

      cards.forEach(card => {{
        const type = card.dataset.type;
        const sentiment = card.dataset.sentiment;
        const name = card.dataset.name || '';
        const why = card.dataset.why || '';
        const what = card.dataset.what || '';

        const typeOk = currentType === 'all' || type === currentType;
        const sentimentOk = currentSentiment === 'all' || sentiment === currentSentiment;
        const searchOk = !searchTerm || name.includes(searchTerm) || why.includes(searchTerm) || what.includes(searchTerm);

        if (typeOk && sentimentOk && searchOk) {{
          card.classList.remove('hidden');
          visible++;
        }} else {{
          card.classList.add('hidden');
        }}
      }});

      resultsCount.textContent = visible.toLocaleString() + ' entities';
      noResults.style.display = visible === 0 ? 'block' : 'none';
    }}

    document.getElementById('searchInput').addEventListener('input', e => {{
      searchTerm = e.target.value.trim().toLowerCase();
      applyFilters();
    }});

    document.querySelectorAll('.filter-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentType = btn.dataset.filter;
        applyFilters();
      }});
    }});

    document.getElementById('sentimentFilter').addEventListener('change', e => {{
      currentSentiment = e.target.value;
      applyFilters();
    }});

    const btn = document.getElementById('backTop');
    window.addEventListener('scroll', () => {{
      btn.classList.toggle('visible', window.scrollY > 400);
    }});
  </script>
</body>
</html>"""

    return html


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    report = load_report(target_date)

    os.makedirs("website", exist_ok=True)
    html = generate_html(report)

    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    abs_path = os.path.abspath(OUTPUT_PATH)
    print(f"Generated: {abs_path}")
    webbrowser.open(f"file://{abs_path}")


if __name__ == "__main__":
    main()
