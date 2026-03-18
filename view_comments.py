import os
import sqlite3
import sys
import webbrowser
from datetime import datetime, timezone

DB_PATH = "marketpulse_v5.db"
OUTPUT_PATH = "website/comments.html"


def load_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get today's date (UTC) or the passed-in date
    if len(sys.argv) > 1:
        today_str = sys.argv[1]
    else:
        today_str = datetime.now(timezone.utc).date().isoformat()

    cursor.execute("""
        SELECT video_id, channel_handle, channel_name, video_title, source_tier
        FROM videos
        WHERE DATE(created_at) = ?
        ORDER BY source_tier, channel_handle, channel_name
    """, (today_str,))
    videos = cursor.fetchall()

    result = []
    for video_id, channel_handle, channel_name, video_title, source_tier in videos:
        cursor.execute("""
            SELECT comment_id, text, author, like_count, reply_count, is_reply, parent_comment_id
            FROM comments
            WHERE video_id = ?
            ORDER BY is_reply ASC, reply_count DESC, like_count DESC
        """, (video_id,))
        rows = cursor.fetchall()

        top_level = [r for r in rows if r[5] == 0]
        replies_map = {}
        for r in rows:
            if r[5] == 1 and r[6]:
                replies_map.setdefault(r[6], []).append(r)

        result.append({
            "video_id": video_id,
            "channel_handle": channel_handle,
            "channel_name": channel_name,
            "video_title": video_title,
            "source_tier": source_tier,
            "comments": top_level,
            "replies_map": replies_map,
        })

    conn.close()

    total_comments = sum(
        len(v["comments"]) + sum(len(r) for r in v["replies_map"].values())
        for v in result
    )
    return today_str, result, total_comments


def escape_html(text):
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;"))


def build_comments_html(today_str, data, total_comments):
    try:
        dt = datetime.strptime(today_str, "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y").upper()
    except Exception:
        display_date = today_str.upper()

    video_count = len(data)
    tier1_videos = [v for v in data if v["source_tier"] == "tier1"]
    tier2_videos = [v for v in data if v["source_tier"] == "tier2"]

    # Group by channel
    tier1_channels = {}
    for v in tier1_videos:
        tier1_channels.setdefault(v["channel_name"], []).append(v)

    tier2_channels = {}
    for v in tier2_videos:
        tier2_channels.setdefault(v["channel_name"], []).append(v)

    # Build comment blocks HTML
    def render_video_block(v, tier_class):
        lines = []
        channel_slug = v["channel_name"].replace(" ", "-").replace("'", "").lower()
        lines.append(f'<div class="video-block {tier_class}" data-channel="{escape_html(v["channel_name"])}" data-tier="{tier_class}">')
        lines.append(f'  <div class="video-title">')
        lines.append(f'    <span class="vt-label">{escape_html(v["channel_name"])} · {escape_html(v["channel_handle"])}</span>')
        lines.append(f'    <span class="vt-name">{escape_html(v["video_title"])}</span>')
        c_count = len(v["comments"]) + sum(len(r) for r in v["replies_map"].values())
        lines.append(f'    <span class="vt-count">{c_count} comments</span>')
        lines.append(f'  </div>')
        lines.append(f'  <div class="comment-list">')

        for c in v["comments"]:
            cid, text, author, likes, reply_count, _, _ = c
            text_safe = escape_html(text)
            author_safe = escape_html(author or "")
            hot = reply_count > 2
            hot_class = " hot" if hot else ""
            hot_badge = '<span class="hot-badge">★ HIGH ENGAGEMENT</span>' if hot else ""

            lines.append(f'    <div class="comment{hot_class}" data-text="{text_safe.lower()}">')
            lines.append(f'      <div class="comment-meta">')
            lines.append(f'        <span class="comment-author">{author_safe}</span>')
            lines.append(f'        <span class="comment-stats">{likes:,} likes · {reply_count} replies</span>')
            if hot:
                lines.append(f'        {hot_badge}')
            lines.append(f'      </div>')
            lines.append(f'      <div class="comment-text">{text_safe}</div>')

            replies = v["replies_map"].get(cid, [])
            if replies:
                lines.append(f'      <div class="replies">')
                for reply in replies:
                    _, rtext, rauthor, rlikes, _, _, _ = reply
                    rtext_safe = escape_html(rtext)
                    rauthor_safe = escape_html(rauthor or "")
                    lines.append(f'        <div class="reply" data-text="{rtext_safe.lower()}">')
                    lines.append(f'          <div class="comment-meta">')
                    lines.append(f'            <span class="comment-author">{rauthor_safe}</span>')
                    lines.append(f'            <span class="comment-stats">{rlikes:,} likes</span>')
                    lines.append(f'          </div>')
                    lines.append(f'          <div class="comment-text">{rtext_safe}</div>')
                    lines.append(f'        </div>')
                lines.append(f'      </div>')

            lines.append(f'    </div>')

        lines.append(f'  </div>')
        lines.append(f'</div>')
        return "\n".join(lines)

    # Build channel sections
    def render_channel_section(channel_name, videos, tier_class):
        lines = []
        total = sum(len(v["comments"]) + sum(len(r) for r in v["replies_map"].values()) for v in videos)
        lines.append(f'<div class="channel-section {tier_class}" data-channel="{escape_html(channel_name)}">')
        lines.append(f'  <div class="channel-header">')
        lines.append(f'    <span class="ch-name">{escape_html(channel_name)}</span>')
        lines.append(f'    <span class="ch-stats">{len(videos)} video{"s" if len(videos) != 1 else ""} · {total:,} comments</span>')
        lines.append(f'  </div>')
        for v in videos:
            lines.append(render_video_block(v, tier_class))
        lines.append(f'</div>')
        return "\n".join(lines)

    all_blocks = []
    for ch, vids in sorted(tier1_channels.items()):
        all_blocks.append(render_channel_section(ch, vids, "tier1"))
    for ch, vids in sorted(tier2_channels.items()):
        all_blocks.append(render_channel_section(ch, vids, "tier2"))

    blocks_html = "\n".join(all_blocks)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Market Pulse — All Comments — {today_str}</title>
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
      --navy-light: #3a6a9a;
      --accent:   #c0392b;
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

    /* ── TOP NAV ── */
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

    /* ── CONTROLS BAR ── */
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
      max-width: 420px;
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

    .search-wrap input:focus {{
      border-color: var(--navy-mid);
    }}

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
      background: var(--bg);
      border-color: var(--navy-mid);
      color: var(--navy-mid);
    }}

    .results-count {{
      font-size: 0.68rem;
      color: var(--muted);
      letter-spacing: 0.06em;
      margin-left: auto;
    }}

    .hot-only-btn {{
      padding: 0.4rem 0.9rem;
      font-family: 'Inter', sans-serif;
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      border: 1px solid var(--gold);
      background: transparent;
      color: var(--gold);
      cursor: pointer;
    }}

    .hot-only-btn.active {{
      background: var(--gold);
      color: #ffffff;
    }}

    /* ── MAIN LAYOUT ── */
    .page-wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 2.5rem 2.5rem 6rem;
    }}

    /* ── TIER LABEL ── */
    .tier-divider {{
      font-size: 0.6rem;
      font-weight: 700;
      letter-spacing: 0.24em;
      text-transform: uppercase;
      color: var(--navy-mid);
      padding: 1.2rem 0 0.6rem;
      border-bottom: 2px solid var(--navy);
      margin-bottom: 1.2rem;
    }}

    /* ── CHANNEL SECTION ── */
    .channel-section {{
      margin-bottom: 1.8rem;
    }}

    .channel-header {{
      background: var(--navy);
      padding: 0.6rem 1.2rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }}

    .ch-name {{
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: #ffffff;
    }}

    .ch-stats {{
      font-size: 0.63rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #7fa8d4;
    }}

    /* ── VIDEO BLOCK ── */
    .video-block {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-top: none;
      margin-bottom: 1px;
    }}

    .video-title {{
      background: #f0eee9;
      border-bottom: 1px solid var(--border);
      padding: 0.6rem 1.2rem;
      display: flex;
      align-items: baseline;
      gap: 0.8rem;
      flex-wrap: wrap;
    }}

    .vt-label {{
      font-size: 0.62rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--navy-mid);
      white-space: nowrap;
    }}

    .vt-name {{
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--ink);
      flex: 1;
    }}

    .vt-count {{
      font-size: 0.62rem;
      color: var(--muted);
      white-space: nowrap;
    }}

    /* ── COMMENT LIST ── */
    .comment-list {{
      padding: 0;
    }}

    .comment {{
      padding: 0.75rem 1.2rem;
      border-bottom: 1px solid var(--border);
    }}

    .comment:last-child {{ border-bottom: none; }}

    .comment.hot {{
      background: #fffdf5;
      border-left: 3px solid var(--gold);
    }}

    .comment.hidden {{ display: none; }}

    .comment-meta {{
      display: flex;
      align-items: center;
      gap: 0.8rem;
      margin-bottom: 0.3rem;
      flex-wrap: wrap;
    }}

    .comment-author {{
      font-size: 0.7rem;
      font-weight: 600;
      color: var(--navy-mid);
    }}

    .comment-stats {{
      font-size: 0.65rem;
      color: var(--muted);
      letter-spacing: 0.04em;
    }}

    .hot-badge {{
      font-size: 0.58rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--gold);
      border: 1px solid var(--gold);
      padding: 0.1rem 0.45rem;
    }}

    .comment-text {{
      font-size: 0.88rem;
      color: var(--ink-soft);
      line-height: 1.65;
    }}

    /* ── REPLIES ── */
    .replies {{
      margin-top: 0.6rem;
      padding-left: 1.2rem;
      border-left: 2px solid var(--border-strong);
    }}

    .reply {{
      padding: 0.5rem 0;
      border-bottom: 1px solid var(--border);
    }}

    .reply:last-child {{ border-bottom: none; }}

    .reply.hidden {{ display: none; }}

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

    /* ── NO RESULTS ── */
    .no-results {{
      text-align: center;
      padding: 4rem 2rem;
      color: var(--muted);
      font-size: 0.85rem;
      display: none;
    }}

    /* ── BACK TO TOP ── */
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

    .channel-section.hidden {{ display: none; }}
    .video-block.hidden {{ display: none; }}
  </style>
</head>
<body>

  <div class="topbar">
    <span class="topbar-brand">Market <span>Pulse</span></span>
    <nav class="topbar-nav">
      <a href="index.html">Intelligence Report</a>
      <a href="comments.html" class="active">All Comments</a>
      <a href="companies.html">Companies &amp; Tech</a>
    </nav>
  </div>

  <header>
    <div class="header-left">
      <p class="report-label">Raw Comment Data</p>
      <h1 class="masthead"><span>All</span> Comments</h1>
      <p class="tagline">Every comment and reply collected — search, filter, and explore the raw signal</p>
    </div>
    <div class="header-stats">
      <div class="stat-chip"><strong>{video_count:,}</strong> videos</div>
      <div class="stat-chip"><strong>{total_comments:,}</strong> comments &amp; replies</div>
      <div class="stat-chip"><strong>71</strong> channels · <strong>2</strong> tiers</div>
    </div>
  </header>

  <div class="dateline">
    <span class="date">{display_date}</span>
    <span class="divider-pipe"></span>
    <span class="meta">Tier 1 — {len(tier1_channels)} consumer channels</span>
    <span class="divider-pipe"></span>
    <span class="meta">Tier 2 — {len(tier2_channels)} institutional channels</span>
    <span class="divider-pipe"></span>
    <span class="meta">★ High engagement = 2+ replies</span>
  </div>

  <div class="controls">
    <div class="search-wrap">
      <span class="search-icon">🔍</span>
      <input type="text" id="searchInput" placeholder="Search comments..." autocomplete="off" />
    </div>
    <div class="filter-group">
      <button class="filter-btn active" data-filter="all">All</button>
      <button class="filter-btn" data-filter="tier1">Tier 1</button>
      <button class="filter-btn" data-filter="tier2">Tier 2</button>
    </div>
    <button class="hot-only-btn" id="hotOnlyBtn">★ High Engagement Only</button>
    <span class="results-count" id="resultsCount">{total_comments:,} comments</span>
  </div>

  <div class="page-wrap">
    <div class="tier-divider">Tier 1 — Consumer Signal Channels</div>
    {'<div class="no-tier1-msg" style="display:none;color:var(--muted);font-size:0.82rem;padding:1rem 0;">No Tier 1 results</div>' if tier1_channels else ''}

{chr(10).join(render_channel_section(ch, vids, "tier1") for ch, vids in sorted(tier1_channels.items()))}

    <div class="tier-divider" style="margin-top:2.5rem;">Tier 2 — Institutional Media</div>

{chr(10).join(render_channel_section(ch, vids, "tier2") for ch, vids in sorted(tier2_channels.items()))}

    <div class="no-results" id="noResults">No comments match your search.</div>
  </div>

  <footer>
    <strong>Market Pulse</strong> &nbsp;·&nbsp; Built by Krishna &nbsp;·&nbsp; {today_str}
  </footer>

  <button class="back-top" id="backTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">↑</button>

  <script>
    let currentFilter = 'all';
    let hotOnly = false;
    let searchTerm = '';

    const allComments = document.querySelectorAll('.comment');
    const allReplies = document.querySelectorAll('.reply');
    const allVideoBlocks = document.querySelectorAll('.video-block');
    const allChannelSections = document.querySelectorAll('.channel-section');
    const resultsCount = document.getElementById('resultsCount');
    const noResults = document.getElementById('noResults');

    function applyFilters() {{
      let visible = 0;

      allComments.forEach(c => {{
        const tier = c.dataset.tier;
        const text = c.dataset.text || '';
        const isHot = c.classList.contains('hot');

        const tierOk = currentFilter === 'all' || tier === currentFilter;
        const hotOk = !hotOnly || isHot;
        const searchOk = !searchTerm || text.includes(searchTerm);

        if (tierOk && hotOk && searchOk) {{
          c.classList.remove('hidden');
          visible++;
        }} else {{
          c.classList.add('hidden');
        }}
      }});

      // Also filter replies when searching
      allReplies.forEach(r => {{
        const text = r.dataset.text || '';
        const parentComment = r.closest('.comment');
        if (parentComment && parentComment.classList.contains('hidden')) {{
          r.classList.add('hidden');
        }} else if (searchTerm && !text.includes(searchTerm) && parentComment && !parentComment.dataset.text.includes(searchTerm)) {{
          // keep reply visible if parent is visible
          r.classList.remove('hidden');
        }} else {{
          r.classList.remove('hidden');
        }}
      }});

      // Hide video blocks with no visible comments
      allVideoBlocks.forEach(vb => {{
        const tierOk = currentFilter === 'all' || vb.dataset.tier === currentFilter;
        if (!tierOk) {{
          vb.classList.add('hidden');
          return;
        }}
        const anyVisible = Array.from(vb.querySelectorAll('.comment')).some(c => !c.classList.contains('hidden'));
        vb.classList.toggle('hidden', !anyVisible);
      }});

      // Hide channel sections with no visible blocks
      allChannelSections.forEach(cs => {{
        const tierOk = currentFilter === 'all' || cs.dataset.tier === currentFilter;
        if (!tierOk) {{
          cs.classList.add('hidden');
          return;
        }}
        const anyVisible = Array.from(cs.querySelectorAll('.video-block')).some(vb => !vb.classList.contains('hidden'));
        cs.classList.toggle('hidden', !anyVisible);
      }});

      resultsCount.textContent = visible.toLocaleString() + ' comments';
      noResults.style.display = visible === 0 ? 'block' : 'none';
    }}

    // Search
    document.getElementById('searchInput').addEventListener('input', e => {{
      searchTerm = e.target.value.trim().toLowerCase();
      applyFilters();
    }});

    // Tier filters
    document.querySelectorAll('.filter-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.dataset.filter;
        applyFilters();
      }});
    }});

    // Hot only toggle
    document.getElementById('hotOnlyBtn').addEventListener('click', () => {{
      hotOnly = !hotOnly;
      document.getElementById('hotOnlyBtn').classList.toggle('active', hotOnly);
      applyFilters();
    }});

    // Back to top
    const btn = document.getElementById('backTop');
    window.addEventListener('scroll', () => {{
      btn.classList.toggle('visible', window.scrollY > 400);
    }});
  </script>
</body>
</html>"""

    return html


def main():
    today_str, data, total_comments = load_data()

    if not data:
        print("No data found. Run ingest_youtube.py first.")
        return

    os.makedirs("website", exist_ok=True)
    html = build_comments_html(today_str, data, total_comments)

    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    abs_path = os.path.abspath(OUTPUT_PATH)
    print(f"Generated: {abs_path}")
    print(f"  Videos: {len(data)} | Comments: {total_comments:,}")
    webbrowser.open(f"file://{abs_path}")


if __name__ == "__main__":
    main()
