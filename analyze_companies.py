import os
import json
import sqlite3
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
import anthropic

load_dotenv()

DB_PATH = "marketpulse_v5.db"
REPORTS_DIR = "reports"
MODEL = "claude-sonnet-4-20250514"
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
      "sentiment": "positive|negative|mixed|neutral",
      "why_talking": "What specifically triggered this discussion right now",
      "what_saying": ["Bullet point 1", "Bullet point 2", "Bullet point 3", "Bullet point 4"],
      "key_quotes": ["verbatim quote from comment", "another verbatim quote", "third verbatim quote"]
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
                # Extend what_saying if different content
                if entity.get("what_saying") and entity["what_saying"] not in ex.get("what_saying", ""):
                    ex["what_saying"] = (ex.get("what_saying", "") + " " + entity["what_saying"]).strip()
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


def run_extraction(client, data):
    """Run entity extraction, splitting into passes if data is large."""
    prompt = build_prompt(data)
    CHAR_LIMIT = 80_000  # ~20k tokens

    if len(prompt) <= CHAR_LIMIT:
        print("  Single-pass extraction...")
        raw = call_llm(client, prompt)
        parsed = json.loads(extract_json(raw))
        return parsed.get("entities", [])

    # Split into chunks of ~30 videos each
    chunk_size = 30
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
    print(f"  Large dataset — {len(chunks)} passes needed...")

    all_entities = []
    for i, chunk in enumerate(chunks):
        print(f"  Pass {i+1}/{len(chunks)}...")
        chunk_prompt = build_prompt(chunk)
        raw = call_llm(client, chunk_prompt)
        try:
            parsed = json.loads(extract_json(raw))
            all_entities.append(parsed.get("entities", []))
        except json.JSONDecodeError as e:
            print(f"  JSON parse error on pass {i+1}: {e} — skipping chunk")

        if i < len(chunks) - 1:
            print(f"  Waiting 65s before next pass...")
            time.sleep(65)

    print(f"  Merging {len(all_entities)} passes...")
    merged = merge_entities(all_entities)
    before = len(merged)
    merged = deduplicate_entities(merged)
    print(f"  Deduplication: {before} → {len(merged)} entities")
    return merged


def save_report(today_str, entities):
    os.makedirs(REPORTS_DIR, exist_ok=True)
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

    today_str = datetime.now(timezone.utc).date().isoformat()
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
