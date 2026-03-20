import os
import json
import sys
import sqlite3
import webbrowser
import urllib.request
import urllib.parse
import ssl
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv()

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
from datetime import datetime, timezone

REPORTS_DIR = "reports"
OUTPUT_PATH = "website/companies.html"
DB_PATH = "marketpulse_v5.db"


def load_price_data():
    """Load all stock_prices rows → {ticker: [(date, close, pct), ...]} sorted oldest→newest."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT ticker, date, close, percent_change FROM stock_prices ORDER BY ticker, date ASC"
        ).fetchall()
        conn.close()
    except Exception:
        return {}
    data = defaultdict(list)
    for ticker, date, close, pct in rows:
        data[ticker].append((date, close, pct))
    return dict(data)


MARKET_INDEX_META = [
    ("^GSPC",   "S&P 500"),
    ("^DJI",    "DJIA"),
    ("^IXIC",   "NASDAQ"),
    ("^RUT",    "RUT 2000"),
    ("BTC-USD", "BTC"),
]

def load_market_indices():
    """Return list of {label, ticker, close, pct} for the market summary bar.
    Tries DB first; falls back to live yfinance fetch if DB is empty."""
    # Try DB first
    try:
        conn = sqlite3.connect(DB_PATH)
        result = []
        for ticker, label in MARKET_INDEX_META:
            row = conn.execute(
                "SELECT close, percent_change FROM stock_prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
                (ticker,)
            ).fetchone()
            if row:
                result.append({"label": label, "ticker": ticker, "close": row[0], "pct": row[1]})
        conn.close()
        if result:
            return result
    except Exception:
        pass

    # Fallback: fetch live from yfinance
    try:
        import yfinance as yf
        result = []
        for ticker, label in MARKET_INDEX_META:
            try:
                t = yf.Ticker(ticker)
                info = t.fast_info
                close = float(info.last_price)
                prev  = float(info.previous_close)
                pct   = round((close - prev) / prev * 100, 2) if prev else None
                result.append({"label": label, "ticker": ticker, "close": close, "pct": pct})
            except Exception:
                pass
        return result
    except Exception:
        return []


def render_market_bar(indices):
    if not indices:
        return ""
    items = []
    for idx in indices:
        pct = idx["pct"]
        close = idx["close"]
        pct_str = (f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%") if pct is not None else "—"
        cls = "up" if pct and pct >= 0 else "dn"
        # Format large numbers with commas, BTC needs 2 dp, indices are large integers
        if idx["ticker"] == "BTC-USD":
            close_str = f"${close:,.0f}"
        else:
            close_str = f"{close:,.2f}"
        items.append(
            f'<span class="mkt-item">'
            f'<span class="mkt-label">{idx["label"]}</span>'
            f'<span class="mkt-close">{close_str}</span>'
            f'<span class="mkt-pct {cls}">{pct_str}</span>'
            f'</span>'
        )
    inner = '<span class="mkt-sep">|</span>'.join(items)
    return f'<div class="market-bar"><div class="market-bar-inner">{inner}</div></div>'


def sparkline_svg(closes, width=80, height=28):
    """Generate an inline SVG polyline sparkline from a list of close prices."""
    if len(closes) < 2:
        return ""
    min_p, max_p = min(closes), max(closes)
    rng = max_p - min_p or 1
    pts = []
    for i, p in enumerate(closes):
        x = round(i / (len(closes) - 1) * width, 1)
        y = round(height - (p - min_p) / rng * (height - 4) - 2, 1)
        pts.append(f"{x},{y}")
    color = "#16a34a" if closes[-1] >= closes[0] else "#dc2626"
    poly = " ".join(pts)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="display:block;">'
        f'<polyline points="{poly}" fill="none" stroke="{color}" '
        f'stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )

# Names of channel hosts / podcasters — exclude from entity output
CHANNEL_HOSTS = {
    "marques brownlee", "mkbhd",
    "nikhil kamath",
    "tom bilyeu",
    "dwarkesh patel",
    "jeff su",
    "aaron jack",
    "ray dalio",
    "tina huang",
    "johnny harris",
    "steven bartlett",
    "andrew ng",
    "patrick boyle",
    "peter diamandis",
    "simon clark",
    "rob mulla",
    "varun mayya",
    "aarav narula",
    "harkirat singh",
    "ivy fung",
    "alex lee",
    "martin zeman",
    "lei",
}


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


# Color palette per entity type — used for the card's color block
TYPE_COLORS = {
    "company":    ("#e8f0fe", "#1a56db"),
    "brand":      ("#e8f0fe", "#1a56db"),
    "technology": ("#fef3c7", "#d97706"),
    "product":    ("#fce7f3", "#db2777"),
    "gpu":        ("#f0fdf4", "#16a34a"),
    "ai_model":   ("#ede9fe", "#7c3aed"),
    "platform":   ("#fff7ed", "#ea580c"),
    "person":     ("#f0f9ff", "#0284c7"),
    "event":      ("#fdf2f8", "#a21caf"),
    "policy":     ("#fef9c3", "#ca8a04"),
    "other":      ("#f5f5f4", "#78716c"),
}


TYPE_LABEL = {
    "company": "Company", "brand": "Brand", "technology": "Technology",
    "product": "Product", "gpu": "GPU", "ai_model": "AI Model",
    "platform": "Platform", "person": "Person", "event": "Event",
    "policy": "Policy", "other": "Other",
}


def type_label(t):
    return TYPE_LABEL.get(t, t.replace("_", " ").capitalize() if t else "Other")


def fetch_pexels_image(query):
    """Fetch a photo from Pexels for the given query. Returns image URL or None."""
    if not PEXELS_API_KEY:
        return None
    try:
        q = urllib.parse.quote(query)
        url = f"https://api.pexels.com/v1/search?query={q}&per_page=1&orientation=landscape"
        req = urllib.request.Request(url, headers={
            "Authorization": PEXELS_API_KEY,
            "User-Agent": "MarketPulse/1.0"
        })
        with urllib.request.urlopen(req, timeout=5, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
            photos = data.get("photos", [])
            if photos:
                return photos[0]["src"]["large"]
    except Exception:
        pass
    return None


def fetch_wiki_image(name):
    """Fetch Wikipedia thumbnail."""
    try:
        t = urllib.parse.quote(name.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{t}"
        req = urllib.request.Request(url, headers={"User-Agent": "MarketPulse/1.0"})
        with urllib.request.urlopen(req, timeout=4, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
            return data.get("thumbnail", {}).get("source")
    except Exception:
        return None


# Context suffixes to make Pexels searches more accurate per entity type
TYPE_CONTEXT = {
    "company":    "{name} company headquarters office",
    "brand":      "{name} brand store",
    "technology": "{name} technology",
    "gpu":        "{name} GPU graphics chip semiconductor",
    "ai_model":   "{name} artificial intelligence AI software",
    "platform":   "{name} app platform software",
    "product":    "{name} product device",
    "policy":     "{name} government policy",
    "event":      "{name} event",
    "other":      "{name}",
}


def fetch_clearbit_logo(name, ticker=None):
    """Check if Clearbit has a logo for the company. Returns URL if valid, else None."""
    candidates = []
    if ticker:
        candidates.append(f"{ticker.lower()}.com")
    # Common domain guesses
    clean = name.lower().replace(" ", "").replace(".", "").replace(",", "")
    candidates += [f"{clean}.com", f"{name.lower().replace(' ', '-')}.com"]
    for domain in candidates:
        url = f"https://logo.clearbit.com/{domain}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MarketPulse/1.0"})
            with urllib.request.urlopen(req, timeout=3, context=_SSL_CTX) as resp:
                if resp.status == 200:
                    return url
        except Exception:
            continue
    return None


# Disambiguation suffixes for Wikipedia to avoid wrong matches
WIKI_DISAMBIG = {
    "company": "{name} company",
    "brand":   "{name} brand company",
    "gpu":     "{name} GPU graphics",
    "ai_model":"{name} AI language model",
    "platform":"{name} software platform",
    "technology": "{name} technology",
    "product": "{name} product",
}


def fetch_wiki_search_image(query):
    """Search Wikipedia with query, return thumbnail of top result."""
    try:
        q = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "MarketPulse/1.0"})
        with urllib.request.urlopen(req, timeout=4, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
            results = data.get("query", {}).get("search", [])
            if results:
                return fetch_wiki_image(results[0]["title"])
    except Exception:
        pass
    return None


def fetch_ticker_image(ticker):
    """Get company logo from financialmodelingprep using stock ticker. Free, no API key."""
    if not ticker:
        return None
    try:
        url = f"https://financialmodelingprep.com/image-stock/{ticker.upper()}.png"
        req = urllib.request.Request(url, headers={"User-Agent": "MarketPulse/1.0"})
        with urllib.request.urlopen(req, timeout=4, context=_SSL_CTX) as resp:
            if resp.status == 200 and int(resp.headers.get("Content-Length", 1000)) > 500:
                return url
    except Exception:
        pass
    return None


def fetch_image(name, etype, ticker=None):
    """Companies: ticker logo first. People: Wikipedia. Tech: Wikipedia with disambiguation."""
    if etype == "person":
        return fetch_wiki_image(name)

    # Companies with ticker → fast, accurate logo
    if etype in ("company", "brand") and ticker:
        img = fetch_ticker_image(ticker)
        if img:
            return img

    # Wikipedia with type-specific title variants
    if etype in ("company", "brand"):
        candidates = [f"{name} Inc", f"{name} (company)", name]
    elif etype == "ai_model":
        candidates = [f"{name} (language model)", f"{name} AI", name]
    elif etype == "gpu":
        candidates = [f"{name} GPU", f"Nvidia {name}", name]
    elif etype == "technology":
        candidates = [f"{name} (software)", f"{name} (operating system)", name]
    elif etype == "platform":
        candidates = [f"{name} (platform)", f"{name} (software)", name]
    else:
        candidates = [name]

    for title in candidates:
        img = fetch_wiki_image(title)
        if img:
            return img

    # Clearbit logo fallback for companies without ticker
    if etype in ("company", "brand"):
        return fetch_clearbit_logo(name, ticker)

    return None


def fetch_all_images(entities):
    """Fetch images for all entities concurrently. Returns dict name→url."""
    print(f"  Fetching images for {len(entities)} entities...")
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_to_entity = {
            pool.submit(fetch_image, e["name"], e.get("type", "other"), e.get("ticker")): e["name"]
            for e in entities
        }
        for future in as_completed(future_to_entity):
            name = future_to_entity[future]
            url = future.result()
            if url:
                results[name] = url
    print(f"  Images found: {len(results)}/{len(entities)}")
    return results


def load_trending_tickers(today_str, limit=15):
    """Load ticker frequency data for today, this week, and this month."""
    try:
        conn = sqlite3.connect(DB_PATH)

        def query(where_clause, params):
            rows = conn.execute(f"""
                SELECT ticker,
                       SUM(appearance_count)  AS total_appearances,
                       MAX(close_price)        AS close_price,
                       MAX(percent_change)     AS percent_change,
                       GROUP_CONCAT(entity_cards, '|||') AS all_cards,
                       GROUP_CONCAT(entity_types, '|||') AS all_types
                FROM ticker_frequency
                WHERE {where_clause}
                GROUP BY ticker
                ORDER BY total_appearances DESC
                LIMIT ?
            """, (*params, limit)).fetchall()

            result = []
            for ticker, count, close, pct, cards_raw, types_raw in rows:
                # Deduplicate entity names across days
                all_cards = []
                seen = set()
                for chunk in (cards_raw or "").split("|||"):
                    try:
                        for c in json.loads(chunk):
                            if c not in seen:
                                all_cards.append(c)
                                seen.add(c)
                    except Exception:
                        pass
                all_types = set()
                for chunk in (types_raw or "").split("|||"):
                    try:
                        all_types.update(json.loads(chunk))
                    except Exception:
                        pass
                result.append({
                    "ticker": ticker,
                    "count": count,
                    "close": close,
                    "pct": pct,
                    "cards": all_cards,
                    "types": sorted(all_types),
                    "multi_type": len(all_types) >= 3,
                })
            return result

        today   = query("date = ?",                    (today_str,))
        weekly  = query("date >= date(?, '-6 days')",  (today_str,))
        monthly = query("date >= date(?, '-29 days')", (today_str,))

        # Load sparkline closes per ticker from stock_prices
        spark_rows = conn.execute("""
            SELECT ticker, date, close FROM stock_prices
            WHERE date >= date(?, '-29 days')
            ORDER BY ticker, date ASC
        """, (today_str,)).fetchall()
        conn.close()

        sparks = defaultdict(list)
        for ticker, date, close in spark_rows:
            sparks[ticker].append(close)

        for group in (today, weekly, monthly):
            for r in group:
                r["sparks"] = sparks.get(r["ticker"], [])

        return today, weekly, monthly

    except Exception as e:
        print(f"  load_trending_tickers error: {e}")
        return [], [], []


def render_ticker_pill(r):
    """Single compact pill: TICKER ±X.XX% (N), color-coded by direction."""
    ticker = escape_html(r["ticker"])
    pct    = r["pct"]
    if pct is None:
        pill_class = "mpill flat"
        pct_str    = "n/a"
    elif pct >= 0:
        pill_class = "mpill up"
        pct_str    = f"+{pct:.2f}%"
    else:
        pill_class = "mpill down"
        pct_str    = f"{pct:.2f}%"
    count = r["count"]
    return (
        f'<span class="{pill_class}">'
        f'<span class="mpill-ticker">{ticker}</span>'
        f'<span class="mpill-pct">{pct_str}</span>'
        f'<span class="mpill-count">({count})</span>'
        f'</span>'
    )


def render_trending_section(today, weekly, monthly):
    if not (today or weekly or monthly):
        return ""
    def pills_html(rows):
        if not rows:
            return '<span class="tt-empty">No data yet</span>'
        return "".join(render_ticker_pill(r) for r in rows)

    return f"""
  <!-- TRENDING TICKERS -->
  <div class="tt-wrap">
    <div class="tt-card">
      <div class="tt-card-header">
        <span class="tt-title">Trending Tickers</span>
        <div class="tt-tabs">
          <button class="tt-tab active" data-tab="today">Today</button>
          <button class="tt-tab" data-tab="week">This Week</button>
          <button class="tt-tab" data-tab="month">This Month</button>
        </div>
      </div>
      <div class="tt-body">
        <div class="tt-panel active" id="tt-today">{pills_html(today)}</div>
        <div class="tt-panel" id="tt-week">{pills_html(weekly)}</div>
        <div class="tt-panel" id="tt-month">{pills_html(monthly)}</div>
      </div>
    </div>
  </div>"""


def generate_html(reports):
    """Accept a list of report dicts, newest first. Renders multi-date sections."""

    def tier_priority(e):
        t1 = e.get("tier1_mentions", False)
        t2 = e.get("tier2_mentions", False)
        return 1 if (not t1 and t2) else 0

    def filter_entities(raw):
        es = sorted(raw, key=lambda e: (tier_priority(e), -e.get("mention_count", 0)))
        es = [e for e in es if e.get("name", "").lower().strip() not in CHANNEL_HOSTS]
        es = [e for e in es if e.get("ticker") or e.get("affected_tickers") or e.get("investor_tickers")]
        return es

    # Build per-report entity lists
    report_sections = []
    for report in reports:
        es = filter_entities(report["entities"])
        report_sections.append((report["date"], es))

    # Fetch images for all unique entities across all dates
    all_entities = {e["name"]: e for _, es in report_sections for e in es}
    price_data = load_price_data()
    image_map = fetch_all_images(list(all_entities.values()))

    # Use the newest date for the page title/header
    today_str = reports[0]["date"]
    trending_today, trending_week, trending_month = load_trending_tickers(today_str)
    try:
        dt = datetime.strptime(today_str, "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y")
    except Exception:
        display_date = today_str

    total_entities = sum(len(es) for _, es in report_sections)
    entities = report_sections[0][1]  # for stats line (newest date)
    companies = [e for e in entities if e.get("type") in ("company", "brand")]
    technologies = [e for e in entities if e.get("type") == "technology"]
    products = [e for e in entities if e.get("type") == "product"]
    entity_count = total_entities
    market_indices = load_market_indices()

    SENTIMENT_META = {
        "bullish":  ("rgba(16,185,129,0.12)",  "Bullish",  "#10B981"),
        "bearish":  ("rgba(230,57,70,0.12)",   "Bearish",  "#E63946"),
        "mixed":    ("rgba(245,158,11,0.12)",  "Mixed",    "#F59E0B"),
        "neutral":  ("rgba(100,116,139,0.12)", "Neutral",  "#64748B"),
    }

    def render_card(entity):
        name = escape_html(entity.get("name", ""))
        ticker = entity.get("ticker")
        etype = entity.get("type", "other")
        mentions = entity.get("mention_count", 0)
        t1 = entity.get("tier1_mentions", False)
        t2 = entity.get("tier2_mentions", False)
        why = escape_html(entity.get("why_talking", ""))
        raw_what = entity.get("what_saying", "")
        quotes = entity.get("key_quotes", [])
        affected = entity.get("affected_tickers", [])
        investor = entity.get("investor_tickers", [])
        sentiment = entity.get("sentiment", "").lower().strip()

        bg, accent = TYPE_COLORS.get(etype, ("#f5f5f4", "#78716c"))
        type_lbl = type_label(etype)

        # Tier badge
        if t1 and not t2:
            tier_html = '<span class="tier t1">Markets</span>'
        elif t2 and not t1:
            tier_html = '<span class="tier t2">Geopolitics</span>'
        else:
            tier_html = '<span class="tier both">Markets + Geo</span>'

        raw_name = entity.get("name", "")
        words = raw_name.strip().split()
        initials = "".join(w[0].upper() for w in words if w)[:2]
        img_url = image_map.get(raw_name)

        is_logo = etype in ("company", "brand") and ticker and img_url and "financialmodelingprep" in img_url
        if img_url and is_logo:
            art_inner = f'''<img class="logo-img" src="{img_url}"
                onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"
                alt="{escape_html(raw_name)}" />
              <div class="logo-fallback" style="display:none;background:{bg};">
                <span class="logo-initials" style="color:{accent};">{escape_html(initials)}</span>
              </div>'''
        elif img_url:
            art_inner = f'''<div class="wiki-img" style="background-image:url('{img_url}');"></div>'''
        elif etype == "person":
            art_inner = f'''<div class="avatar-circle" style="background:{accent}20;border:2px solid {accent}40;">
                <span class="avatar-initials" style="color:{accent};">{escape_html(initials)}</span>
              </div>'''
        else:
            art_inner = f'''<div class="type-art-block" style="background:{bg};">
                <span class="type-art-initials" style="color:{accent};">{escape_html(initials)}</span>
              </div>'''

        # --- Price row (for entities with a direct ticker) ---
        price_html = ""
        spark_html = ""
        if ticker and ticker in price_data:
            rows = price_data[ticker]  # [(date, close, pct), ...]
            latest_close, latest_pct = rows[-1][1], rows[-1][2]
            closes = [r[1] for r in rows]
            pct_sign = "+" if latest_pct and latest_pct >= 0 else ""
            pct_color = "#16a34a" if latest_pct and latest_pct >= 0 else "#dc2626"
            pct_str = f"{pct_sign}{latest_pct:.2f}%" if latest_pct is not None else "—"
            arrow = "▲" if latest_pct and latest_pct >= 0 else "▼"
            price_html = f'''<div class="price-row">
              <span class="price-ticker">{escape_html(ticker)}</span>
              <span class="price-val">${latest_close:,.2f}</span>
              <span class="price-pct" style="color:{pct_color};">{arrow} {pct_str}</span>
            </div>'''
            if len(closes) >= 5:
                spark_html = f'<div class="sparkline">{sparkline_svg(closes)}</div>'

        # --- Affected tickers row (for geo/political entities) ---
        affected_html = ""
        if not ticker and (affected or investor):
            chips = []
            for t in (affected or investor)[:6]:
                t_rows = price_data.get(t, [])
                if t_rows:
                    pct = t_rows[-1][2]
                    sign = "+" if pct and pct >= 0 else ""
                    pct_str = f"{sign}{pct:.1f}%"
                    chip_cls = "affect-chip up" if pct and pct >= 0 else "affect-chip dn"
                    chips.append(
                        f'<span class="{chip_cls}">'
                        f'<span class="affect-chip-ticker">{t}</span>'
                        f'<span class="affect-chip-pct">{pct_str}</span>'
                        f'</span>'
                    )
                else:
                    chips.append(f'<span class="affect-chip flat"><span class="affect-chip-ticker">{t}</span></span>')
            if chips:
                label = "Affects:" if affected else "Via:"
                affected_html = f'<div class="affected-row"><span class="affected-label">{label}</span>{"".join(chips)}</div>'

        # --- Market Chatter dropdown ---
        bullets = []
        if isinstance(raw_what, list):
            for b in raw_what[:4]:
                bullets.append(f'<li class="chatter-bullet">{escape_html(b)}</li>')
        elif raw_what:
            bullets.append(f'<li class="chatter-bullet">{escape_html(str(raw_what)[:300])}</li>')

        dropdown_html = ""
        if bullets:
            bullets_html = f'<ul class="chatter-bullets">{"".join(bullets)}</ul>'
            dropdown_html = f'''<div class="dropdown-wrap">
    <button class="dropdown-btn" onclick="toggleChatter(this)">
      <span class="chatter-label">
        <svg class="chatter-icon" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 2H2a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h2v2.5L7.5 12H14a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
        </svg>
        Market Chatter
      </span>
      <svg class="chevron" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
    <div class="dropdown-body">
      {bullets_html}
    </div>
  </div>'''

        # Sentiment badge
        sent_html = ""
        if sentiment in SENTIMENT_META:
            sbg, slabel, scolor = SENTIMENT_META[sentiment]
            sent_html = f'<span class="sent-badge" style="background:{sbg};color:{scolor};">{slabel}</span>'

        tier_data = 'tier1' if t1 and not t2 else 'tier2' if t2 and not t1 else 'both'
        return f"""<div class="card" data-type="{etype}" data-tier="{tier_data}" data-name="{name.lower()}">
  <div class="card-art" style="background:{bg};">
    {art_inner}
    <div class="card-art-meta">
      <span class="type-tag" style="color:{accent};">{type_lbl}</span>
      {tier_html}
    </div>
  </div>
  <div class="card-body">
    <div class="card-title-row">
      <h3 class="card-title">{name}</h3>
      {sent_html}
    </div>
    {price_html}
    {spark_html}
    <p class="card-why">{why}</p>
    {affected_html}
    {dropdown_html}
    <div class="card-foot">
      <span class="mentions"><strong>{mentions}</strong> mentions</span>
    </div>
  </div>
</div>"""

    def fmt_section_date(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%B %d, %Y")
        except Exception:
            return d

    sections_html = []
    for date_str, es in report_sections:
        cards = "\n".join(render_card(e) for e in es)
        label = fmt_section_date(date_str)
        sections_html.append(
            f'<div class="date-section-header"><span class="date-section-label">{label}</span>'
            f'<span class="date-section-count">{len(es)} market signals</span></div>\n{cards}'
        )
    all_cards_html = "\n".join(sections_html)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Market Pulse — Companies & Tech — {today_str}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,700;1,400&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:        #0B1426;
      --white:     #111D33;
      --border:    #1E2D45;
      --ink:       #F1F5F9;
      --ink2:      #94A3B8;
      --muted:     #64748B;
      --red:       #E63946;
      --teal:      #10B981;
      --amber:     #F59E0B;
      --card-radius: 14px;
    }}

    /* ── ANIMATIONS ── */
    @keyframes cardIn {{
      from {{ opacity: 0; transform: translateY(18px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    .card {{
      animation: cardIn 0.45s ease both;
      animation-play-state: paused;
    }}
    .card.visible {{
      animation-play-state: running;
    }}

    body {{
      background: var(--bg);
      color: var(--ink);
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }}

    /* ── MARKET SUMMARY BAR ── */
    .market-bar {{
      background: #070E1A;
      border-bottom: 1px solid #1E3A5F;
      padding: 0 1rem;
      height: 34px;
      display: flex;
      align-items: center;
      overflow: hidden;
      position: sticky;
      top: 0;
      z-index: 300;
    }}
    .market-bar-inner {{
      display: flex;
      align-items: center;
      gap: 0;
      overflow: hidden;
      white-space: nowrap;
    }}
    .mkt-item {{
      display: inline-flex;
      align-items: baseline;
      gap: 0.4rem;
      padding: 0 1.1rem;
    }}
    .mkt-sep {{
      color: #1E3A5F;
      font-size: 0.7rem;
      user-select: none;
    }}
    .mkt-label {{
      font-size: 0.65rem;
      font-weight: 700;
      color: #3D5A80;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .mkt-close {{
      font-size: 0.72rem;
      font-weight: 600;
      color: #94A3B8;
      font-variant-numeric: tabular-nums;
    }}
    .mkt-pct {{
      font-size: 0.68rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }}
    .mkt-pct.up {{ color: var(--teal); }}
    .mkt-pct.dn {{ color: var(--red); }}

    /* ── TOPBAR ── */
    .topbar {{
      background: var(--white);
      border-bottom: 1px solid var(--border);
      padding: 0 2rem;
      height: 52px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 34px;
      z-index: 250;
    }}

    .brand {{
      font-family: 'Playfair Display', Georgia, serif;
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--ink);
      letter-spacing: -0.01em;
    }}

    .brand em {{ color: var(--red); font-style: normal; }}

    .topbar-nav {{
      display: flex;
      gap: 0.2rem;
    }}

    .topbar-nav a {{
      font-size: 0.72rem;
      font-weight: 500;
      letter-spacing: 0.04em;
      color: var(--muted);
      text-decoration: none;
      padding: 0.3rem 0.8rem;
      border-radius: 2rem;
    }}

    .topbar-nav a:hover {{ color: var(--ink); }}
    .topbar-nav a.active {{ background: var(--red); color: #fff; }}

    /* ── PAGE HEADER ── */
    .page-header {{
      border-bottom: 1px solid var(--border);
      background: var(--white);
      padding: 2.5rem 2rem 1.8rem;
    }}

    .page-header-inner {{
      max-width: 1680px;
      margin: 0 auto;
    }}

    .page-eyebrow {{
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--red);
      margin-bottom: 0.5rem;
    }}

    .page-title {{
      font-family: 'Playfair Display', Georgia, serif;
      font-size: clamp(1.8rem, 3vw, 2.6rem);
      font-weight: 700;
      color: var(--ink);
      line-height: 1.1;
      margin-bottom: 0.5rem;
    }}

    .page-meta {{
      font-size: 0.78rem;
      color: var(--muted);
    }}

    .page-meta strong {{ color: var(--ink2); }}

    /* ── CONTROLS ── */
    .controls {{
      background: var(--white);
      border-bottom: 1px solid var(--border);
      padding: 0.7rem 1rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
      position: sticky;
      top: 86px;
      z-index: 100;
    }}

    .controls-inner {{
      max-width: 1680px;
      margin: 0 auto;
      width: 100%;
      display: flex;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }}

    .sort-label {{
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      white-space: nowrap;
    }}

    .pill-group {{
      display: flex;
      gap: 0.3rem;
      flex-wrap: wrap;
    }}

    .pill {{
      padding: 0.3rem 0.9rem;
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.72rem;
      font-weight: 500;
      border: 1px solid #1E3A5F;
      border-radius: 2rem;
      background: transparent;
      color: var(--ink2);
      cursor: pointer;
      transition: background 0.2s, border-color 0.2s, color 0.2s, transform 0.15s;
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }}
    .pill:hover:not(.active) {{ background: rgba(30,58,95,0.4); transform: translateY(-1px); }}

    .pill .dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: currentColor;
      opacity: 0.5;
    }}

    .pill.active {{
      background: var(--red);
      border-color: var(--red);
      color: #fff;
    }}

    .pill.active .dot {{ opacity: 1; }}

    .pill:hover:not(.active) {{
      border-color: var(--ink2);
      color: var(--ink);
    }}

    .divider {{ width: 1px; height: 18px; background: var(--border); }}

    .search-wrap {{
      margin-left: auto;
      position: relative;
    }}

    .search-wrap input {{
      padding: 0.35rem 1rem 0.35rem 2.1rem;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: var(--bg);
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.75rem;
      color: var(--ink);
      width: 220px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
    }}

    .search-wrap input::placeholder {{ color: var(--muted); }}
    .search-wrap input:focus {{
      border-color: var(--red);
      background: var(--white);
      box-shadow: 0 0 0 3px rgba(240,69,69,0.15);
    }}

    .search-icon {{
      position: absolute;
      left: 0.65rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--muted);
      font-size: 0.72rem;
      pointer-events: none;
    }}

    .results-count {{
      font-size: 0.7rem;
      color: var(--muted);
      white-space: nowrap;
    }}

    /* ── GRID ── */
    .grid-wrap {{
      max-width: 1680px;
      margin: 2rem auto;
      padding: 0 2rem 6rem;
    }}

    .card-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 2rem 1.75rem;
      align-items: stretch;
    }}

    /* ── CARD — editorial, no box ── */
    .card {{
      background: transparent;
      border: none;
      border-radius: 0;
      overflow: visible;
      transition: opacity 0.2s;
      cursor: default;
      position: relative;
      z-index: 1;
      display: flex;
      flex-direction: column;
    }}

    .card:hover {{ opacity: 0.95; z-index: 100; }}

    .card.hidden {{ display: none; }}

    /* Color art block — 3:2 aspect ratio keeps all images same height */
    .card-art {{
      aspect-ratio: 3 / 2;
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow: hidden;
      border-radius: 16px;
      flex-shrink: 0;
    }}

    /* No gradient overlay — clean standalone image */
    .card-art::after {{ display: none; }}

    .wiki-img {{
      position: absolute;
      inset: 0;
      background-size: cover;
      background-position: center top;
      transition: transform 0.4s ease;
    }}
    .card:hover .wiki-img {{ transform: scale(1.04); }}

    .logo-img {{
      width: 100px;
      height: 100px;
      object-fit: contain;
      border-radius: 20px;
      background: #EEF2FF;
      padding: 12px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }}

    .logo-fallback {{
      width: 90px;
      height: 90px;
      border-radius: 16px;
      align-items: center;
      justify-content: center;
    }}

    .logo-initials {{
      font-family: 'Playfair Display', Georgia, serif;
      font-size: 2.2rem;
      font-weight: 700;
      opacity: 0.6;
    }}

    .avatar-circle {{
      width: 90px;
      height: 90px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .avatar-initials {{
      font-family: 'Playfair Display', Georgia, serif;
      font-size: 2rem;
      font-weight: 700;
    }}

    .type-art-block {{
      width: 90px;
      height: 90px;
      border-radius: 16px;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .type-art-initials {{
      font-family: 'Playfair Display', Georgia, serif;
      font-size: 2.2rem;
      font-weight: 700;
      opacity: 0.5;
    }}

    /* Card body — flex column so foot always sits at bottom */
    .card-body {{
      padding: 0.85rem 0 0;
      display: flex;
      flex-direction: column;
      flex: 1;
    }}

    /* ── MARKET CHATTER DROPDOWN — in-flow, scrollable ── */
    .dropdown-wrap {{
      position: relative;
      margin-bottom: 0.75rem;
    }}

    .dropdown-btn {{
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.45rem 0.75rem;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 999px;
      cursor: pointer;
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.64rem;
      font-weight: 600;
      color: var(--muted);
      letter-spacing: 0.06em;
      text-transform: uppercase;
      text-align: left;
      transition: border-color 0.18s, color 0.18s, background 0.18s;
    }}
    .dropdown-btn:hover {{
      border-color: var(--red);
      color: var(--red);
      background: rgba(240,69,69,0.07);
    }}
    .dropdown-wrap.open .dropdown-btn {{
      border-color: var(--red);
      color: var(--red);
      border-radius: 999px 999px 0 0;
      background: rgba(240,69,69,0.07);
    }}

    .chatter-label {{
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }}
    .chatter-icon {{
      width: 13px;
      height: 13px;
      color: var(--red);
      flex-shrink: 0;
    }}

    .chevron {{
      width: 14px;
      height: 14px;
      color: var(--muted);
      transition: transform 0.22s ease;
      flex-shrink: 0;
    }}
    .dropdown-wrap.open .chevron {{ transform: rotate(180deg); }}

    .dropdown-body {{
      position: static;
      background: #0D1829;
      border: 1px solid var(--red);
      border-top: none;
      border-radius: 0 0 14px 14px;
      padding: 0 0.85rem;
      max-height: 0;
      overflow: hidden;
      opacity: 0;
      transition: max-height 0.32s ease, opacity 0.22s ease, padding 0.22s ease;
    }}
    .dropdown-wrap.open .dropdown-body {{
      max-height: 230px;
      overflow-y: auto;
      opacity: 1;
      padding: 0.75rem 0.85rem 0.65rem;
    }}
    /* Scrollbar styling */
    .dropdown-body::-webkit-scrollbar {{ width: 4px; }}
    .dropdown-body::-webkit-scrollbar-track {{ background: transparent; }}
    .dropdown-body::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 2px; }}
    .dropdown-body::-webkit-scrollbar-thumb:hover {{ background: var(--muted); }}
    /* Fade gradient at bottom to hint more content */
    .dropdown-wrap.open::after {{
      content: '';
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      height: 28px;
      background: linear-gradient(to bottom, transparent, #0D1829);
      border-radius: 0 0 14px 14px;
      pointer-events: none;
      z-index: 2;
    }}

    /* Bullet summary items — red left accent */
    .chatter-bullets {{
      list-style: none;
      margin: 0 0 0.25rem;
      padding: 0;
    }}
    .chatter-bullet {{
      font-size: 0.79rem;
      color: var(--ink2);
      line-height: 1.55;
      padding: 0.3rem 0 0.3rem 0.75rem;
      border-left: 2px solid var(--red);
      margin-bottom: 0.3rem;
    }}
    .chatter-bullet:last-child {{ margin-bottom: 0; }}

    /* Divider between bullets and raw comments */
    .chatter-divider {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin: 0.6rem 0 0.5rem;
      color: var(--muted);
      font-size: 0.62rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.07em;
    }}
    .chatter-divider::before,
    .chatter-divider::after {{
      content: '';
      flex: 1;
      height: 1px;
      background: var(--border);
    }}

    /* Raw YouTube comment quotes */
    .chatter-quotes {{
      list-style: none;
      margin: 0;
      padding: 0;
      background: #0E0E16;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 0.45rem 0.65rem;
    }}
    .chatter-quote {{
      font-size: 0.73rem;
      font-style: italic;
      color: var(--muted);
      line-height: 1.5;
      padding: 0.25rem 0;
      border-bottom: 1px solid var(--border);
    }}
    .chatter-quote:last-child {{ border-bottom: none; }}
    .chatter-quote::before {{ content: '\201C'; }}
    .chatter-quote::after  {{ content: '\201D'; }}

    .card-art-meta {{
      position: absolute;
      top: 0.65rem;
      left: 0.7rem;
      display: flex;
      align-items: center;
      gap: 0.35rem;
      z-index: 1;
    }}

    .type-tag {{
      font-size: 0.52rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: rgba(255,255,255,0.85);
      background: rgba(0,0,0,0.45);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 999px;
      padding: 0.14rem 0.45rem;
    }}

    .tier {{
      font-size: 0.5rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      padding: 0.14rem 0.4rem;
      border-radius: 999px;
    }}

    .tier.t1   {{ background: rgba(21,128,61,0.7);  color: #fff; }}
    .tier.t2   {{ background: rgba(180,83,9,0.7);   color: #fff; }}
    .tier.both {{ background: rgba(109,40,217,0.7); color: #fff; }}


    .card-title-row {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 0.6rem;
      margin-bottom: 0.55rem;
    }}

    .card-title {{
      font-family: 'Playfair Display', Georgia, serif;
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--ink);
      line-height: 1.2;
      letter-spacing: -0.02em;
      flex: 1;
    }}

    .sent-badge {{
      flex-shrink: 0;
      font-size: 0.52rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 0.18rem 0.55rem;
      border-radius: 999px;
      margin-top: 0.25rem;
      white-space: nowrap;
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      border: 1px solid currentColor;
      opacity: 0.9;
    }}

    .ticker {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      font-size: 0.6rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      color: var(--muted);
      vertical-align: middle;
      margin-left: 0.3rem;
    }}

    .card-why {{
      font-size: 0.75rem;
      font-weight: 400;
      color: var(--ink2);
      line-height: 1.6;
      margin-bottom: 0.75rem;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .bullets {{
      margin: 0 0 0.7rem 1rem;
      list-style: disc;
    }}

    .bullets li {{
      font-size: 0.78rem;
      color: var(--ink2);
      line-height: 1.55;
      margin-bottom: 0.2rem;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .quote {{
      font-size: 0.76rem;
      color: var(--muted);
      font-style: italic;
      border-left: 2px solid var(--border);
      padding: 0.3rem 0.6rem;
      margin-bottom: 0.7rem;
      line-height: 1.5;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .card-foot {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-top: 0.5rem;
      margin-top: auto;
    }}

    .mentions {{
      font-size: 0.6rem;
      font-weight: 300;
      color: var(--muted);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}

    .mentions strong {{ color: var(--muted); font-weight: 300; }}

    /* ── PRICE ROW ── */
    .price-row {{
      display: flex;
      align-items: baseline;
      gap: 0.4rem;
      margin: 0.5rem 0 0.4rem;
      flex-wrap: wrap;
    }}
    .price-ticker {{
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--muted);
      text-transform: uppercase;
    }}
    .price-val {{
      font-size: 1rem;
      font-weight: 700;
      color: var(--ink);
      font-variant-numeric: tabular-nums;
    }}
    .price-pct {{
      font-size: 0.72rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }}

    /* ── SPARKLINE ── */
    .sparkline {{
      margin: 0.35rem 0 0.4rem;
    }}

    /* ── AFFECTED TICKERS ROW ── */
    .affected-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.3rem;
      margin: 0.6rem 0 0.6rem;
    }}
    .affected-label {{
      font-size: 0.6rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-right: 0.1rem;
    }}
    .affect-chip {{
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
      padding: 0.12rem 0.4rem;
      border-radius: 999px;
      border: 1px solid transparent;
      white-space: nowrap;
      transition: filter 0.15s, transform 0.15s;
    }}
    .affect-chip:hover {{ filter: brightness(1.2); transform: translateY(-1px); }}
    .affect-chip.up   {{ background: #0D2E26; border-color: #134D3E; }}
    .affect-chip.dn   {{ background: #2E0D15; border-color: #4D1322; }}
    .affect-chip.flat {{ background: #1E293B; border-color: #334155; }}
    .affect-chip-ticker {{
      font-size: 0.58rem;
      font-weight: 800;
      color: var(--ink);
      letter-spacing: 0.04em;
    }}
    .affect-chip-pct {{
      font-size: 0.56rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }}
    .affect-chip.up   .affect-chip-pct {{ color: var(--teal); }}
    .affect-chip.dn   .affect-chip-pct {{ color: var(--red); }}
    .affect-chip.flat .affect-chip-pct {{ color: var(--muted); }}

    /* ── TRENDING TICKERS ── */
    .tt-wrap {{
      padding: 1rem;
      background: var(--bg);
      border-bottom: 1px solid var(--border);
    }}
    .tt-card {{
      background: linear-gradient(135deg, #111D33 0%, #162440 100%);
      border: 1px solid #1E3A5F;
      border-left: 3px solid var(--red);
      border-radius: 10px;
      box-shadow: 0 4px 20px rgba(0,100,255,0.05), 0 1px 3px rgba(0,0,0,0.3);
      overflow: hidden;
    }}
    .tt-card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.65rem 1rem;
      border-bottom: 1px solid var(--border);
    }}
    .tt-title {{
      font-size: 0.72rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--ink);
    }}
    .tt-tabs {{
      display: flex;
      gap: 0;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }}
    .tt-tab {{
      background: var(--white);
      border: none;
      border-left: 1px solid var(--border);
      padding: 0.28rem 0.75rem;
      font-size: 0.68rem;
      font-weight: 600;
      color: var(--muted);
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
    }}
    .tt-tab:first-child {{ border-left: none; }}
    .tt-tab.active {{
      background: var(--red);
      color: #fff;
      box-shadow: 0 0 10px rgba(230,57,70,0.35);
    }}
    .tt-tab:not(.active):hover {{
      background: rgba(255,255,255,0.05);
      color: var(--ink);
    }}
    .tt-body {{
      padding: 0.6rem 1rem;
    }}
    .tt-panel {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      align-items: center;
      opacity: 0;
      pointer-events: none;
      max-height: 0;
      overflow: hidden;
      transition: opacity 0.25s ease;
    }}
    .tt-panel.active {{
      opacity: 1;
      pointer-events: auto;
      max-height: none;
      overflow: visible;
    }}
    .tt-empty {{
      font-size: 0.7rem;
      color: var(--muted);
    }}
    .mpill {{
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
      padding: 0.15rem 0.4rem;
      border: 1px solid transparent;
      border-radius: 999px;
      cursor: default;
      transition: filter 0.15s, transform 0.15s;
    }}
    .mpill:hover {{ filter: brightness(1.25); transform: translateY(-1px); }}
    .mpill.up   {{ background: #0D2E26; border-color: #134D3E; }}
    .mpill.down {{ background: #2E0D15; border-color: #4D1322; }}
    .mpill.flat {{ background: #1E293B; border-color: #334155; }}
    .mpill-ticker {{
      font-size: 0.62rem;
      font-weight: 800;
      color: var(--ink);
      letter-spacing: 0.04em;
    }}
    .mpill-pct {{
      font-size: 0.6rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }}
    .mpill.up   .mpill-pct {{ color: var(--teal); }}
    .mpill.down .mpill-pct {{ color: var(--red); }}
    .mpill-count {{
      font-size: 0.57rem;
      color: var(--muted);
    }}

    /* ── DATE SECTION HEADER ── */
    .date-section-header {{
      grid-column: 1 / -1;
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 2rem 0 1rem;
      margin-top: 0.5rem;
      position: relative;
    }}
    .date-section-header::before {{
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 1px;
      background: linear-gradient(to right, transparent, var(--border) 20%, var(--border) 80%, transparent);
    }}
    .date-section-header:first-child {{
      padding-top: 0;
      margin-top: 0;
    }}
    .date-section-header:first-child::before {{ display: none; }}
    .date-section-label {{
      font-family: 'Playfair Display', serif;
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--ink);
    }}
    .date-section-count {{
      font-size: 0.72rem;
      color: var(--muted);
      font-weight: 500;
      letter-spacing: 0.04em;
    }}

    /* ── NO RESULTS ── */
    .no-results {{
      grid-column: 1 / -1;
      text-align: center;
      padding: 5rem;
      color: var(--muted);
      font-size: 0.9rem;
      display: none;
    }}

    /* ── FOOTER ── */
    footer {{
      text-align: center;
      padding: 3rem 2rem;
      border-top: 1px solid var(--border);
      font-size: 0.65rem;
      font-weight: 300;
      color: var(--muted);
      letter-spacing: 0.06em;
    }}
    .footer-brand {{
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--ink2);
      letter-spacing: -0.01em;
      margin-bottom: 0.5rem;
    }}
    .footer-brand em {{ color: var(--red); font-style: normal; }}
    .footer-tagline {{
      color: var(--muted);
      font-size: 0.65rem;
      font-weight: 300;
      margin-bottom: 1rem;
      letter-spacing: 0.04em;
    }}
    .footer-links {{
      display: flex;
      justify-content: center;
      gap: 1.5rem;
    }}
    .footer-links a {{
      color: var(--muted);
      text-decoration: none;
      font-size: 0.65rem;
      font-weight: 400;
      letter-spacing: 0.06em;
      transition: color 0.15s;
    }}
    .footer-links a:hover {{ color: var(--red); }}

    /* ── BACK TOP ── */
    .back-top {{
      position: fixed;
      bottom: 2rem;
      right: 2rem;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: var(--ink);
      color: #fff;
      border: none;
      font-size: 1rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: opacity 0.3s;
    }}

    .back-top.visible {{ opacity: 1; }}
    .back-top:hover {{ background: var(--red); }}
  </style>
</head>
<body>

{render_market_bar(market_indices)}
  <!-- TOPBAR -->
  <div class="topbar">
    <span class="brand">Market<em>Pulse</em></span>
    <nav class="topbar-nav">
      <a href="index.html">Intelligence Report</a>
      <a href="comments.html">All Comments</a>
      <a href="companies.html" class="active">Companies &amp; Tech</a>
    </nav>
  </div>


{render_trending_section(trending_today, trending_week, trending_month)}

  <!-- CONTROLS -->
  <div class="controls">
    <div class="controls-inner">
      <span class="sort-label">Filter by</span>

      <div class="pill-group" id="typeFilters">
        <button class="pill active" data-filter="all">All</button>
        <button class="pill" data-filter="companies_tech"><span class="dot" style="background:#1a56db"></span>Companies &amp; Tech</button>
        <button class="pill" data-filter="person"><span class="dot" style="background:#0284c7"></span>People</button>
      </div>

      <div class="divider"></div>

      <div class="pill-group" id="tierFilters">
        <button class="pill active" data-tier="all">All Tiers</button>
        <button class="pill" data-tier="tier1"><span class="dot" style="background:#15803d"></span>Markets</button>
        <button class="pill" data-tier="tier2"><span class="dot" style="background:#b45309"></span>Geopolitics</button>
      </div>

      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input type="text" id="searchInput" placeholder="Search entities..." autocomplete="off" />
      </div>

      <span class="results-count" id="resultsCount">{entity_count} entities</span>
    </div>
  </div>

  <!-- GRID -->
  <div class="grid-wrap">
    <div class="card-grid" id="cardGrid">
{all_cards_html}
      <div class="no-results" id="noResults">No entities match your filters.</div>
    </div>
  </div>

  <footer>
    <div class="footer-brand">Market<em>Pulse</em></div>
    <div class="footer-tagline">Powered by YouTube Comment Intelligence &nbsp;·&nbsp; {today_str}</div>
    <nav class="footer-links">
      <a href="index.html">Intelligence Report</a>
      <a href="comments.html">All Comments</a>
      <a href="companies.html">Companies &amp; Tech</a>
    </nav>
  </footer>

  <button class="back-top" id="backTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">↑</button>

  <script>
    let currentType = 'all';
    let currentTier = 'all';
    let searchTerm = '';

    const cards = Array.from(document.querySelectorAll('.card'));
    const resultsCount = document.getElementById('resultsCount');
    const noResults = document.getElementById('noResults');

    function applyFilters() {{
      let visible = 0;
      cards.forEach(card => {{
        const type = card.dataset.type;
        const tier = card.dataset.tier || 'both';
        const name = card.dataset.name || '';

        const companiesTechTypes = new Set(['company','brand','technology','product','gpu','ai_model','platform']);
        const typeOk = currentType === 'all'
          || (currentType === 'companies_tech' && companiesTechTypes.has(type))
          || (currentType === 'person' && type === 'person');
        const tierOk = currentTier === 'all' ||
                       (currentTier === 'tier1' && (tier === 'tier1' || tier === 'both')) ||
                       (currentTier === 'tier2' && (tier === 'tier2' || tier === 'both'));
        const searchOk = !searchTerm || name.includes(searchTerm);

        if (typeOk && tierOk && searchOk) {{
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

    document.querySelectorAll('#typeFilters .pill').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('#typeFilters .pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentType = btn.dataset.filter;
        applyFilters();
      }});
    }});

    document.querySelectorAll('#tierFilters .pill').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('#tierFilters .pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTier = btn.dataset.tier;
        applyFilters();
      }});
    }});

    const backBtn = document.getElementById('backTop');
    window.addEventListener('scroll', () => {{
      backBtn.classList.toggle('visible', window.scrollY > 400);
    }});

    // Staggered card fade-in
    (function() {{
      const allCards = document.querySelectorAll('.card');
      const observer = new IntersectionObserver((entries) => {{
        entries.forEach(entry => {{
          if (entry.isIntersecting) {{
            const card = entry.target;
            const idx = parseInt(card.dataset.animIdx || 0);
            setTimeout(() => card.classList.add('visible'), idx * 60);
            observer.unobserve(card);
          }}
        }});
      }}, {{ threshold: 0.05 }});
      allCards.forEach((card, i) => {{
        card.dataset.animIdx = i;
        observer.observe(card);
      }});
    }})();

    // Market Chatter toggle — accordion: only one open at a time
    function toggleChatter(btn) {{
      const wrap = btn.closest('.dropdown-wrap');
      const isOpen = wrap.classList.contains('open');
      document.querySelectorAll('.dropdown-wrap.open').forEach(w => w.classList.remove('open'));
      if (!isOpen) wrap.classList.add('open');
    }}

    // Trending Tickers tab switcher
    document.querySelectorAll('.tt-tab').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tt-tab').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tt-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tt-' + btn.dataset.tab).classList.add('active');
      }});
    }});
  </script>
</body>
</html>"""

    return html


def load_recent_reports(n=2):
    """Load the n most recent *_companies.json reports, newest first."""
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.endswith("_companies.json")],
        reverse=True,
    )[:n]
    reports = []
    for fname in files:
        with open(os.path.join(REPORTS_DIR, fname)) as f:
            reports.append(json.load(f))
    return reports


def main():
    os.makedirs("website", exist_ok=True)
    reports = load_recent_reports(n=2)
    if not reports:
        print("No reports found. Run analyze_companies.py first.")
        sys.exit(1)
    html = generate_html(reports)

    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    abs_path = os.path.abspath(OUTPUT_PATH)
    print(f"Generated: {abs_path}")
    webbrowser.open(f"file://{abs_path}")


if __name__ == "__main__":
    main()
