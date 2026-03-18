"""One-time script to deduplicate entities and reformat what_saying into bullets."""
import os
import json
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
import anthropic

load_dotenv()

REPORTS_DIR = "reports"
MODEL = "claude-sonnet-4-20250514"


def deduplicate_entities(entities):
    """Merge entities that are name variants of the same thing."""
    entities = sorted(entities, key=lambda x: len(x.get("name", "")), reverse=True)
    canonical = {}

    for entity in entities:
        name = entity.get("name", "").strip()
        name_lower = name.lower()

        matched_key = None
        for key in canonical:
            if name_lower in key or key in name_lower:
                matched_key = key
                break

        if matched_key:
            ex = canonical[matched_key]
            ex["mention_count"] = ex.get("mention_count", 0) + entity.get("mention_count", 0)
            seen_q = set(ex.get("key_quotes", []))
            for q in entity.get("key_quotes", []):
                if q not in seen_q and len(ex.get("key_quotes", [])) < 5:
                    ex.setdefault("key_quotes", []).append(q)
                    seen_q.add(q)
        else:
            canonical[name_lower] = dict(entity)

    return sorted(canonical.values(), key=lambda x: x.get("mention_count", 0), reverse=True)


def reformat_to_bullets(client, entities):
    """Send what_saying paragraphs to Claude and get back bullet-point arrays."""
    # Only reformat entities that have string what_saying (not already bullets)
    to_reformat = [
        {"name": e["name"], "what_saying": e["what_saying"]}
        for e in entities
        if isinstance(e.get("what_saying"), str) and e.get("what_saying")
    ]

    if not to_reformat:
        print("  All entities already have bullet format.")
        return entities

    print(f"  Reformatting {len(to_reformat)} entities to bullet format...")

    # Batch into chunks of 30 to stay within token limits
    chunk_size = 30
    reformatted_map = {}

    chunks = [to_reformat[i:i+chunk_size] for i in range(0, len(to_reformat), chunk_size)]
    for i, chunk in enumerate(chunks):
        print(f"  Reformat pass {i+1}/{len(chunks)}...")
        prompt = f"""For each entity below, reformat the "what_saying" text into 4-5 bullet points covering:
1. Main reason for discussion
2. Key viewpoints (support vs criticism)
3. Economic impact (if relevant)
4. Geopolitical implications (if relevant)
Keep each bullet concise. Avoid repetition.

Return ONLY valid JSON — an array of objects with "name" and "bullets" (array of strings).

Entities:
{json.dumps(chunk, indent=2)}"""

        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=4000,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = response.content[0].text.strip()
                if "```" in raw:
                    parts = raw.split("```")
                    for part in parts:
                        if part.startswith("json"):
                            part = part[4:]
                        part = part.strip()
                        if part.startswith("["):
                            raw = part
                            break
                start = raw.find("[")
                end = raw.rfind("]") + 1
                if start != -1 and end > start:
                    raw = raw[start:end]
                result = json.loads(raw)
                for item in result:
                    reformatted_map[item["name"].lower()] = item.get("bullets", [])
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  Error: {e}, retrying in 10s...")
                    time.sleep(10)
                else:
                    print(f"  Failed chunk {i+1}: {e}")

        if i < len(chunks) - 1:
            print("  Waiting 30s...")
            time.sleep(30)

    # Apply reformatted bullets back to entities
    for entity in entities:
        key = entity.get("name", "").lower()
        if key in reformatted_map and reformatted_map[key]:
            entity["what_saying"] = reformatted_map[key]

    return entities


def main():
    today_str = datetime.now(timezone.utc).date().isoformat()
    path = os.path.join(REPORTS_DIR, f"{today_str}_companies.json")

    if not os.path.exists(path):
        # Try most recent
        files = sorted([f for f in os.listdir(REPORTS_DIR) if f.endswith("_companies.json")], reverse=True)
        if not files:
            print("No companies report found.")
            return
        path = os.path.join(REPORTS_DIR, files[0])

    print(f"Loading: {path}")
    with open(path) as f:
        report = json.load(f)

    entities = report["entities"]
    print(f"  {len(entities)} entities loaded")

    # Step 1: Deduplicate
    before = len(entities)
    entities = deduplicate_entities(entities)
    print(f"  Deduplication: {before} → {len(entities)} entities")

    # Step 2: Reformat what_saying to bullets
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)
    entities = reformat_to_bullets(client, entities)

    # Save back
    report["entities"] = entities
    report["entity_count"] = len(entities)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"  Saved: {path} ({len(entities)} entities)")
    print("=== Done ===")


if __name__ == "__main__":
    main()
