import os
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
import anthropic
from ticker_map import resolve_ticker, get_affected_tickers, get_investor_tickers

load_dotenv()

DB_PATH = "marketpulse_v5.db"
REPORTS_DIR = "reports"
MODEL = "claude-sonnet-4-20250514"

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
MAX_TOKENS = 8000
MAX_COMMENT_CHARS = 300
MAX_COMMENTS_PER_VIDEO = 40
MAX_REPLIES_PER_COMMENT = 8

SYSTEM_PROMPT = """You are an exhaustive entity extraction analyst. You scan YouTube comments and pull out EVERY named entity people discuss — companies, technologies, products, people, events, platforms, GPU architectures, AI models, frameworks, startups, executives, policies, anything.

DO NOT FILTER. If 2+ people mention something, include it. Include obscure and highly specific references — GPU architectures (like Vera Rubin, Blackwell, GB200), AI models (like Claude, Grok, Gemini), specific chip names, startup names, executive names, policy names, platform features, announced products, anything.

Use the FULL name for people — "Donald Trump" not "Trump", "Elon Musk" not "Musk". Never create duplicate entries for the same person or entity under different name variants.

For EACH entity, provide:
- WHY now: what triggered this conversation (product launch, news, controversy, event)
- WHAT people are saying: formatted as 4-5 bullet points covering (1) Main reason for discussion, (2) Key viewpoints — support vs criticism, (3) Economic impact if any, (4) Geopolitical implications if any. Keep bullets concise, no repetition.
- Sentiment: positive / negative / mixed / neutral
- Comments with ★ HIGH ENGAGEMENT triggered real conversation — prioritize these

Return ONLY valid JSON, absolutely no text outside the JSON object. Structure:

{
  "entities": [
    {
      "name": "Full Entity Name",
      "type": "company|technology|product|person|event|platform|gpu|ai_model|policy|other",
      "ticker": "TICKER or null",
      "parent": "Parent company if applicable, else null",
      "mention_count": 0,
      "why_talking": "What specifically triggered this discussion right now",
      "what_saying": ["Bullet point 1", "Bullet point 2", "Bullet point 3", "Bullet point 4"],
      "key_quotes": ["verbatim quote from comment", "another verbatim quote", "third verbatim quote"],
      "sentiment": "bullish|bearish|mixed|neutral"
    }
  ]
}

Sort by mention_count descending. Be exhaustive — missing entities is a failure."""


def get_today_data(conn, today_str):
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


def build_prompt(videos, max_comments=40):
    """Build a dense prompt from a list of videos."""
    lines = []
    for v in videos:
        lines.append(f"\n[{v['source_tier'].upper()} | {v['channel_name']} | {v['video_title']}]")
        for c in v["comments"][:max_comments]:
            cid, text, author, likes, reply_count, _, _ = c
            text = text[:MAX_COMMENT_CHARS] + ("…" if len(text) > MAX_COMMENT_CHARS else "")
            eng = " ★ HIGH ENGAGEMENT" if reply_count > 2 else ""
            lines.append(f"  [{likes}♥ {reply_count}↩{eng}] {text}")
            for reply in v["replies_map"].get(cid, [])[:MAX_REPLIES_PER_COMMENT]:
                _, rtext, _, rlikes, _, _, _ = reply
                rtext = rtext[:MAX_COMMENT_CHARS] + ("…" if len(rtext) > MAX_COMMENT_CHARS else "")
                lines.append(f"    > [{rlikes}♥] {rtext}")
        lines.append("")
    return "\n".join(lines)


def call_llm(client, prompt, retries=3):
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            if attempt < retries - 1:
                wait = 65 * (attempt + 1)
                print(f"  Rate limited — waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


def extract_json(raw):
    raw = raw.strip()
    # Strip markdown code fences if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            if part.startswith("json"):
                part = part[4:]
            part = part.strip()
            if part.startswith("{"):
                raw = part
                break
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        return raw[start:end]
    return raw


def merge_entities(lists):
    """Merge multiple entity lists by name, summing counts and combining quotes."""
    merged = {}
    for entities in lists:
        for entity in entities:
            key = entity["name"].lower().strip()
            if key in merged:
                ex = merged[key]
                ex["mention_count"] = ex.get("mention_count", 0) + entity.get("mention_count", 0)
                # Merge quotes (up to 5 unique)
                seen = set(ex.get("key_quotes", []))
                for q in entity.get("key_quotes", []):
                    if q not in seen and len(ex["key_quotes"]) < 5:
                        ex["key_quotes"].append(q)
                        seen.add(q)
                # Extend what_saying if different content (handle both list and str)
                new_what = entity.get("what_saying")
                if new_what:
                    ex_what = ex.get("what_saying", [])
                    if isinstance(ex_what, list) and isinstance(new_what, list):
                        seen_bullets = set(ex_what)
                        for b in new_what:
                            if b not in seen_bullets:
                                ex_what.append(b)
                                seen_bullets.add(b)
                        ex["what_saying"] = ex_what
                    elif isinstance(ex_what, str) and isinstance(new_what, str):
                        if new_what not in ex_what:
                            ex["what_saying"] = (ex_what + " " + new_what).strip()
                    else:
                        # Normalize both to list
                        combined = (ex_what if isinstance(ex_what, list) else [ex_what]) + \
                                   (new_what if isinstance(new_what, list) else [new_what])
                        ex["what_saying"] = list(dict.fromkeys(combined))
            else:
                merged[key] = dict(entity)
                if "key_quotes" not in merged[key]:
                    merged[key]["key_quotes"] = []

    return sorted(merged.values(), key=lambda x: x.get("mention_count", 0), reverse=True)


def deduplicate_entities(entities):
    """Merge entities that are name variants of the same thing (e.g. Trump / Donald Trump)."""
    # Sort longest name first so we keep the more specific/full name as canonical
    entities = sorted(entities, key=lambda x: len(x.get("name", "")), reverse=True)
    canonical = {}  # canonical_name_lower -> entity dict

    for entity in entities:
        name = entity.get("name", "").strip()
        name_lower = name.lower()

        # Check if this entity is a substring match of an already-seen entity (or vice versa)
        matched_key = None
        for key in canonical:
            if name_lower in key or key in name_lower:
                matched_key = key
                break

        if matched_key:
            ex = canonical[matched_key]
            ex["mention_count"] = ex.get("mention_count", 0) + entity.get("mention_count", 0)
            # Merge quotes
            seen_q = set(ex.get("key_quotes", []))
            for q in entity.get("key_quotes", []):
                if q not in seen_q and len(ex.get("key_quotes", [])) < 5:
                    ex.setdefault("key_quotes", []).append(q)
                    seen_q.add(q)
        else:
            canonical[name_lower] = dict(entity)

    return sorted(canonical.values(), key=lambda x: x.get("mention_count", 0), reverse=True)


def run_extraction_for_tier(client, data, tier_label):
    """Run entity extraction for a single tier's data, return list of entities."""
    CHAR_LIMIT = 80_000  # ~20k tokens
    prompt = build_prompt(data)

    if len(prompt) <= CHAR_LIMIT:
        print(f"  [{tier_label}] Single-pass extraction...")
        raw = call_llm(client, prompt)
        try:
            parsed = json.loads(extract_json(raw))
            return parsed.get("entities", [])
        except json.JSONDecodeError as e:
            print(f"  [{tier_label}] JSON parse error: {e}")
            return []

    chunk_size = 30
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
    print(f"  [{tier_label}] Large dataset — {len(chunks)} passes needed...")

    all_entities = []
    for i, chunk in enumerate(chunks):
        print(f"  [{tier_label}] Pass {i+1}/{len(chunks)}...")
        chunk_prompt = build_prompt(chunk)
        raw = call_llm(client, chunk_prompt)
        try:
            parsed = json.loads(extract_json(raw))
            all_entities.append(parsed.get("entities", []))
        except json.JSONDecodeError as e:
            print(f"  [{tier_label}] JSON parse error on pass {i+1}: {e} — skipping chunk")

        if i < len(chunks) - 1:
            print(f"  Waiting 65s before next pass...")
            time.sleep(65)

    return merge_entities(all_entities)


def run_extraction(client, data):
    """Run entity extraction by tier so each entity is tagged with its source tier."""
    tier1 = [v for v in data if v["source_tier"] == "tier1"]
    tier2 = [v for v in data if v["source_tier"] == "tier2"]

    print(f"  Tier 1: {len(tier1)} videos | Tier 2: {len(tier2)} videos")

    # Extract Tier 1
    t1_entities = run_extraction_for_tier(client, tier1, "Tier 1") if tier1 else []
    for e in t1_entities:
        e["tier1_mentions"] = True
        e.setdefault("tier2_mentions", False)

    # Wait between tiers to avoid rate limits
    if tier1 and tier2:
        print("  Waiting 65s before Tier 2...")
        time.sleep(65)

    # Extract Tier 2
    t2_entities = run_extraction_for_tier(client, tier2, "Tier 2") if tier2 else []
    for e in t2_entities:
        e["tier2_mentions"] = True
        e.setdefault("tier1_mentions", False)

    # Merge across tiers — preserve tier flags during merge
    print(f"  Merging Tier 1 ({len(t1_entities)}) + Tier 2 ({len(t2_entities)}) entities...")
    merged = {}
    for entity in t1_entities + t2_entities:
        key = entity["name"].lower().strip()
        if key in merged:
            ex = merged[key]
            ex["mention_count"] = ex.get("mention_count", 0) + entity.get("mention_count", 0)
            if entity.get("tier1_mentions"):
                ex["tier1_mentions"] = True
            if entity.get("tier2_mentions"):
                ex["tier2_mentions"] = True
            seen_q = set(ex.get("key_quotes", []))
            for q in entity.get("key_quotes", []):
                if q not in seen_q and len(ex.get("key_quotes", [])) < 5:
                    ex.setdefault("key_quotes", []).append(q)
                    seen_q.add(q)
        else:
            merged[key] = dict(entity)
            merged[key].setdefault("key_quotes", [])

    result = sorted(merged.values(), key=lambda x: x.get("mention_count", 0), reverse=True)
    print(f"  Total unique entities: {len(result)}")
    return result


def enrich_tickers(entities):
    """Resolve tickers and add affected_tickers / investor_tickers fields."""
    ticker_resolved = 0
    for e in entities:
        name = e.get("name", "")
        etype = e.get("type", "")
        llm_ticker = e.get("ticker")

        # Resolve best ticker
        resolved = resolve_ticker(name, llm_ticker)
        e["ticker"] = resolved
        if resolved:
            ticker_resolved += 1

        # For geo/political entities, add affected tickers
        if etype in ("person", "event", "policy", "other") or not resolved:
            affected = get_affected_tickers(name)
            if affected:
                e["affected_tickers"] = affected

        # For private AI/tech companies with no ticker, add investor tickers
        if not resolved:
            investors = get_investor_tickers(name)
            if investors:
                e["investor_tickers"] = investors

    print(f"  Ticker resolution: {ticker_resolved}/{len(entities)} entities have tickers")
    return entities


def save_report(today_str, entities):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    before = len(entities)
    entities = [e for e in entities if e.get("name", "").lower().strip() not in CHANNEL_HOSTS]
    if before != len(entities):
        print(f"  Filtered out {before - len(entities)} channel host(s)")
    entities = enrich_tickers(entities)
    path = os.path.join(REPORTS_DIR, f"{today_str}_companies.json")
    payload = {
        "date": today_str,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "entity_count": len(entities),
        "entities": entities,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  Saved: {path} ({len(entities)} entities)")
    return path


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    today_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).date().isoformat()
    print(f"=== MarketPulse — Entity Extraction ({today_str}) ===")

    conn = sqlite3.connect(DB_PATH)
    data = get_today_data(conn, today_str)
    conn.close()

    if not data:
        print("No data found. Run ingest_youtube.py first.")
        return

    total = sum(len(v["comments"]) + sum(len(r) for r in v["replies_map"].values()) for v in data)
    print(f"  Videos: {len(data)} | Comments: {total:,}")

    client = anthropic.Anthropic(api_key=api_key)
    entities = run_extraction(client, data)

    save_report(today_str, entities)
    print(f"=== Done — {len(entities)} entities extracted ===")


if __name__ == "__main__":
    main()
