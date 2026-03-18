import os
import json
import sys
import webbrowser
from datetime import datetime, timezone

REPORTS_DIR = "reports"
OUTPUT_PATH = "website/index.html"


def load_report(target_date=None):
    if target_date:
        path = os.path.join(REPORTS_DIR, f"{target_date}.json")
    else:
        files = sorted([
            f for f in os.listdir(REPORTS_DIR) if f.endswith(".json")
        ], reverse=True)
        if not files:
            print("No reports found.")
            sys.exit(1)
        path = os.path.join(REPORTS_DIR, files[0])

    with open(path) as f:
        return json.load(f)


def generate_html(report):
    date_str = report["date"]
    video_count = report["video_count"]
    comment_count = report["comment_count"]
    generated_at = report.get("generated_at", "")
    analysis_md = report["analysis"].replace("`", "\\`").replace("$", "\\$")

    # Format date nicely
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y").upper()
    except Exception:
        display_date = date_str.upper()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Market Pulse — {date_str}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@400;600;700&display=swap" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
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
      --accent:   #c0392b;
    }}

    html {{ scroll-behavior: smooth; }}

    body {{
      background: var(--bg);
      color: var(--ink);
      font-family: 'Inter', -apple-system, sans-serif;
      font-size: 15px;
      line-height: 1.7;
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }}

    /* ── TOP NAV BAR ── */
    .topbar {{
      background: var(--navy);
      padding: 0.55rem 2.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .topbar-brand {{
      font-family: 'Inter', sans-serif;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: #ffffff;
    }}

    .topbar-brand span {{ color: #7fa8d4; }}

    .topbar-right {{
      font-size: 0.65rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #7fa8d4;
    }}

    /* ── HEADER ── */
    header {{
      background: var(--surface);
      border-bottom: 3px solid var(--navy);
      padding: 2.5rem 2.5rem 2rem;
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
      margin-bottom: 0.5rem;
    }}

    .masthead {{
      font-family: 'Playfair Display', Georgia, serif;
      font-weight: 700;
      font-size: clamp(1.8rem, 4vw, 2.8rem);
      color: var(--ink);
      line-height: 1.1;
      letter-spacing: -0.01em;
    }}

    .masthead span {{ color: var(--navy); }}

    .tagline {{
      margin-top: 0.5rem;
      font-size: 0.78rem;
      color: var(--ink-dim);
      font-weight: 400;
    }}

    .header-stats {{
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
      align-items: flex-end;
    }}

    .stat-chip {{
      background: var(--bg);
      border: 1px solid var(--border);
      padding: 0.4rem 0.9rem;
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

    /* ── LAYOUT ── */
    .page-wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 0 2.5rem;
      display: grid;
      grid-template-columns: 1fr 260px;
      gap: 2.5rem;
      align-items: start;
    }}

    main {{ padding: 3rem 0 6rem; }}

    /* ── SIDEBAR ── */
    aside {{
      padding: 3rem 0 6rem;
    }}

    .sidebar-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-top: 3px solid var(--navy);
      padding: 1.4rem 1.6rem;
      margin-bottom: 1.4rem;
    }}

    .sidebar-card h4 {{
      font-size: 0.6rem;
      font-weight: 700;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: var(--navy-mid);
      margin-bottom: 1rem;
      padding-bottom: 0.6rem;
      border-bottom: 1px solid var(--border);
    }}

    .sidebar-card p {{
      font-size: 0.82rem;
      color: var(--ink-dim);
      line-height: 1.6;
      margin-bottom: 0.5rem;
    }}

    .sidebar-card .big-number {{
      font-family: 'Playfair Display', serif;
      font-size: 2.2rem;
      font-weight: 700;
      color: var(--navy);
      line-height: 1;
      margin-bottom: 0.2rem;
    }}

    .sidebar-card .big-label {{
      font-size: 0.65rem;
      font-weight: 500;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }}

    /* ── SECTION WRAPPER ── */
    .section-wrap {{
      background: var(--surface);
      border: 1px solid var(--border);
      margin-bottom: 1.5rem;
      overflow: hidden;
    }}

    .section-header {{
      background: var(--navy);
      padding: 0.7rem 1.6rem;
      display: flex;
      align-items: center;
      gap: 1rem;
    }}

    .section-num {{
      font-size: 0.6rem;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: #7fa8d4;
    }}

    .section-title {{
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: #ffffff;
    }}

    .section-body {{ padding: 1.8rem 1.8rem 1.4rem; }}

    /* ── RENDERED MARKDOWN inside sections ── */
    #report h1 {{
      font-family: 'Playfair Display', serif;
      font-size: 1.4rem;
      font-weight: 700;
      color: var(--ink);
      margin: 0 0 1.2rem;
      padding-bottom: 0.7rem;
      border-bottom: 1px solid var(--border);
      letter-spacing: -0.01em;
    }}

    #report h2 {{
      font-size: 0.68rem;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--navy-mid);
      margin: 2rem 0 0.8rem;
      padding-bottom: 0.4rem;
      border-bottom: 1px solid var(--border);
    }}

    #report h3 {{
      font-size: 0.92rem;
      font-weight: 600;
      color: var(--ink);
      margin: 1.4rem 0 0.4rem;
    }}

    #report p {{
      font-size: 0.93rem;
      color: var(--ink-soft);
      margin-bottom: 0.9rem;
      font-weight: 400;
      line-height: 1.75;
    }}

    #report ul {{
      list-style: none;
      padding: 0;
      margin-bottom: 1rem;
    }}

    #report ul li {{
      font-size: 0.91rem;
      color: var(--ink-soft);
      padding: 0.45rem 0 0.45rem 1.2rem;
      position: relative;
      border-bottom: 1px solid var(--border);
      line-height: 1.6;
    }}

    #report ul li:last-child {{ border-bottom: none; }}

    #report ul li::before {{
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 5px;
      height: 5px;
      background: var(--navy-mid);
      border-radius: 50%;
    }}

    #report strong {{
      color: var(--ink);
      font-weight: 600;
    }}

    #report em {{
      color: var(--ink-dim);
      font-style: italic;
    }}

    #report hr {{
      border: none;
      border-top: 1px solid var(--border);
      margin: 1.8rem 0;
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

    /* ── SCROLL TO TOP ── */
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
    <nav style="display:flex;gap:1.5rem;">
      <a href="index.html" style="font-size:0.65rem;letter-spacing:0.12em;text-transform:uppercase;color:#ffffff;text-decoration:none;font-weight:600;">Intelligence Report</a>
      <a href="comments.html" style="font-size:0.65rem;letter-spacing:0.12em;text-transform:uppercase;color:#7fa8d4;text-decoration:none;">All Comments</a>
      <a href="companies.html" style="font-size:0.65rem;letter-spacing:0.12em;text-transform:uppercase;color:#7fa8d4;text-decoration:none;">Companies &amp; Tech</a>
    </nav>
  </div>

  <header>
    <div class="header-left">
      <p class="report-label">Daily Intelligence Briefing</p>
      <h1 class="masthead"><span>Market</span> Pulse</h1>
      <p class="tagline">YouTube consumer signals across 71 channels — 2 tiers — analyzed by AI</p>
    </div>
    <div class="header-stats">
      <div class="stat-chip"><strong>{video_count:,}</strong> videos analyzed</div>
      <div class="stat-chip"><strong>{comment_count:,}</strong> comments processed</div>
      <div class="stat-chip"><strong>71</strong> channels · <strong>2</strong> tiers</div>
    </div>
  </header>

  <div class="dateline">
    <span class="date">{display_date}</span>
    <span class="divider-pipe"></span>
    <span class="meta">Tier 1 — 57 consumer channels</span>
    <span class="divider-pipe"></span>
    <span class="meta">Tier 2 — 14 institutional channels</span>
    <span class="divider-pipe"></span>
    <span class="meta">Powered by Claude Sonnet</span>
  </div>

  <div class="page-wrap">
    <main>
      <div id="report"></div>
    </main>

    <aside>
      <div class="sidebar-card">
        <h4>Today's Coverage</h4>
        <div class="big-number">{video_count:,}</div>
        <div class="big-label">Videos</div>
        <br/>
        <div class="big-number">{comment_count:,}</div>
        <div class="big-label">Comments &amp; Replies</div>
      </div>
      <div class="sidebar-card">
        <h4>Data Sources</h4>
        <p>57 Tier 1 consumer channels<br/>40 comments per video</p>
        <p>14 Tier 2 institutional channels<br/>20 comments per video</p>
        <p>Replies fetched for comments with 3+ responses (up to 10)</p>
      </div>
      <div class="sidebar-card">
        <h4>Report Sections</h4>
        <p>01 — Topics<br/>02 — Catalysts<br/>03 — Cross-topic Links<br/>04 — Brands Affected<br/>05 — Daily Summary</p>
      </div>
    </aside>
  </div>

  <footer>
    <strong>Market Pulse</strong> &nbsp;·&nbsp; Built by Krishna &nbsp;·&nbsp; {date_str}
  </footer>

  <button class="back-top" id="backTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">↑</button>

  <script>
    const md = `{analysis_md}`;
    document.getElementById('report').innerHTML = marked.parse(md);

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
