import os
import json
import sqlite3
import time
from datetime import date, datetime, timezone

from dotenv import load_dotenv
import anthropic

load_dotenv()

DB_PATH = "marketpulse_v5.db"
REPORTS_DIR = "reports"
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 16000        # must exceed thinking_budget + output tokens
THINKING_BUDGET = 10000  # tokens Claude can use to reason before writing

SYSTEM_PROMPT = """You are a consumer intelligence analyst. You are given today's YouTube video titles and their most-engaged comments from two types of channels:

- Tier 1 (PRIMARY SIGNAL): Independent creators, podcasters, business educators. Their audiences are real consumers sharing genuine opinions about products, spending, brands, and market trends. This is the core data. Weight it heavily.
- Tier 2 (SECONDARY/COMPARISON ONLY): Institutional financial media (CNBC, Bloomberg, WSJ, etc.). Represents what Wall Street already knows and is publicly discussing. Use this only to identify gaps — topics Tier 1 consumers are talking about that Tier 2 has NOT covered yet are the highest-value signals.

Your job is to surface what REAL CONSUMERS are saying, not to summarize financial news. Tier 1 comments are your primary evidence. Tier 2 is context.

Comments marked ★ HIGH ENGAGEMENT have more than 2 replies — these sparked real conversation and carry extra weight. Prioritize them when identifying signals.

Analyze all the data and produce a daily intelligence report with exactly these five sections:

1. Topics People Are Talking About — Driven by Tier 1 consumer comments. List the key topics real people are discussing. Group related topics. Ignore anything that is just institutional media talking to itself.

2. Why They Are Talking About These Topics — For each topic, what triggered the conversation among consumers. Be specific. Cite actual comments as evidence.

3. Links Between Topics — Find connections between seemingly unrelated topics in the Tier 1 data. These cross-topic connections are the most valuable insights and the hardest to find elsewhere. Flag any topic that Tier 1 consumers are discussing but Tier 2 media has not covered yet — that gap is the edge.

4. Brands That Might Get Affected — Based on what consumers are actually saying, list brands that could be positively OR negatively affected. Both sides. For each brand, quote the consumer signal behind it. Include ticker symbols for public companies.

5. Daily Summary — Concise executive summary focused on consumer behavior signals. What are real people doing, buying, avoiding, switching to? What surprised you in the Tier 1 data? What should someone watching markets pay attention to tomorrow?

Be direct. Be specific. No fluff. Ground every insight in actual comments."""


def get_today_data(conn, today_str):
    """Fetch all videos and comments ingested today, organized for LLM."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT video_id, channel_handle, channel_name, video_title, source_tier
        FROM videos
        WHERE DATE(created_at) = ?
        ORDER BY source_tier, channel_handle
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

    return result


# Per-tier comment limits — all data is stored in DB, we just control what goes to Claude
MAX_COMMENTS_TIER1_PER_VIDEO = 25   # Tier 1 is the primary signal — 70% of total comments
MAX_COMMENTS_TIER2_PER_VIDEO = 15   # Tier 2 gets more comments but fewer videos — 30% of total
MAX_REPLIES_PER_COMMENT = 5         # replies shown per parent comment
MAX_COMMENT_CHARS = 280             # truncate long comments
MAX_VIDEOS_TIER1_PER_CHANNEL = 10
MAX_VIDEOS_TIER2_PER_CHANNEL = 5    # more videos per Tier 2 channel to use the data we fetched


def _cap_videos_per_channel(videos, max_per_channel):
    """Return at most max_per_channel videos per channel handle."""
    seen = {}
    result = []
    for v in videos:
        handle = v["channel_handle"]
        if seen.get(handle, 0) < max_per_channel:
            result.append(v)
            seen[handle] = seen.get(handle, 0) + 1
    return result


def build_prompt(data):
    """Format data into the LLM prompt string."""
    lines = ["# Today's YouTube Data\n"]

    tier1 = _cap_videos_per_channel(
        [v for v in data if v["source_tier"] == "tier1"],
        MAX_VIDEOS_TIER1_PER_CHANNEL,
    )
    tier2 = _cap_videos_per_channel(
        [v for v in data if v["source_tier"] == "tier2"],
        MAX_VIDEOS_TIER2_PER_CHANNEL,
    )

    for tier_label, videos, max_comments in [
        ("TIER 1 — Consumer Signal Channels (PRIMARY)", tier1, MAX_COMMENTS_TIER1_PER_VIDEO),
        ("TIER 2 — Institutional Media (SECONDARY CONTEXT)", tier2, MAX_COMMENTS_TIER2_PER_VIDEO),
    ]:
        lines.append(f"\n## {tier_label}\n")
        for video in videos:
            lines.append(f"### [{video['channel_name']} / {video['channel_handle']}]")
            lines.append(f"Video: {video['video_title']}\n")

            for c in video["comments"][:max_comments]:
                cid, text, author, likes, replies_count, _, _ = c
                text = text[:MAX_COMMENT_CHARS] + ("…" if len(text) > MAX_COMMENT_CHARS else "")
                engagement = " ★ HIGH ENGAGEMENT" if replies_count > 2 else ""
                lines.append(f"  [{likes} likes, {replies_count} replies{engagement}] {text}")

                for reply in video["replies_map"].get(cid, [])[:MAX_REPLIES_PER_COMMENT]:
                    _, rtext, rauthor, rlikes, _, _, _ = reply
                    rtext = rtext[:MAX_COMMENT_CHARS] + ("…" if len(rtext) > MAX_COMMENT_CHARS else "")
                    lines.append(f"    > [{rlikes} likes] {rtext}")

            lines.append("")

    return "\n".join(lines)


def call_llm(client, prompt, retries=3):
    """Send prompt to Claude with extended thinking + prompt caching. Retries on rate limit."""
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={
                    "type": "enabled",
                    "budget_tokens": THINKING_BUDGET,  # reasoning space before writing
                },
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # cache across chunked calls
                }],
                messages=[{"role": "user", "content": prompt}],
            )
            # Response has thinking blocks + text block — return only the text
            for block in response.content:
                if block.type == "text":
                    return block.text
            return ""
        except anthropic.RateLimitError:
            if attempt < retries - 1:
                wait = 65 * (attempt + 1)
                print(f"  Rate limited — waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise


def split_and_analyze(client, data):
    """If data is large, analyze tier1 and tier2 separately then synthesize."""
    tier1 = [v for v in data if v["source_tier"] == "tier1"]
    tier2 = [v for v in data if v["source_tier"] == "tier2"]

    prompt1 = build_prompt(tier1)
    prompt2 = build_prompt(tier2)

    combined_char_limit = 80_000  # ~20k tokens

    if len(prompt1) + len(prompt2) <= combined_char_limit:
        return call_llm(client, build_prompt(data))

    print("  Data too large for one call — analyzing in two passes...")

    analysis1 = call_llm(client, prompt1 + "\n\nThis is Tier 1 only. Summarize key themes and comments as an intermediate step.")
    print("  Tier 1 done — waiting 65s before Tier 2...")
    time.sleep(65)
    analysis2 = call_llm(client, prompt2 + "\n\nThis is Tier 2 only. Summarize key themes and comments as an intermediate step.")

    synthesis_prompt = f"""Below are two partial analyses. Synthesize them into the final five-section intelligence report.

## Tier 1 Analysis (Consumer Channels):
{analysis1}

## Tier 2 Analysis (Institutional Media):
{analysis2}

Now produce the final unified report with all five sections."""

    return call_llm(client, synthesis_prompt)


def save_reports(today_str, data, analysis):
    os.makedirs(REPORTS_DIR, exist_ok=True)

    json_path = os.path.join(REPORTS_DIR, f"{today_str}.json")
    md_path = os.path.join(REPORTS_DIR, f"{today_str}.md")

    json_payload = {
        "date": today_str,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "video_count": len(data),
        "comment_count": sum(len(v["comments"]) + sum(len(r) for r in v["replies_map"].values()) for v in data),
        "analysis": analysis,
    }

    with open(json_path, "w") as f:
        json.dump(json_payload, f, indent=2)

    with open(md_path, "w") as f:
        f.write(f"# MarketPulse Daily Intelligence Report\n")
        f.write(f"**Date:** {today_str}\n\n")
        f.write(f"**Videos analyzed:** {json_payload['video_count']} | ")
        f.write(f"**Comments analyzed:** {json_payload['comment_count']}\n\n")
        f.write("---\n\n")
        f.write(analysis)

    print(f"  Saved: {json_path}")
    print(f"  Saved: {md_path}")
    return json_path, md_path


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    today_str = datetime.now(timezone.utc).date().isoformat()
    print(f"=== MarketPulse v5 — Daily Analysis ({today_str}) ===")

    conn = sqlite3.connect(DB_PATH)
    data = get_today_data(conn, today_str)
    conn.close()

    if not data:
        print("No data ingested today. Run ingest_youtube.py first.")
        return

    total_comments = sum(
        len(v["comments"]) + sum(len(r) for r in v["replies_map"].values())
        for v in data
    )
    print(f"  Videos: {len(data)} | Comments: {total_comments}")

    client = anthropic.Anthropic(api_key=api_key)

    print("  Sending to Claude...")
    analysis = split_and_analyze(client, data)

    save_reports(today_str, data, analysis)
    print("=== Done ===")


if __name__ == "__main__":
    main()

