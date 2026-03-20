"""
aggregate_tickers.py
Aggregates daily_snapshots into ticker_frequency — one row per (date, ticker)
showing how many entity cards mentioned that ticker and which ones.

Run after snapshot_daily.py in the daily pipeline:
    python aggregate_tickers.py              # today
    python aggregate_tickers.py 2026-03-19  # specific date
    python aggregate_tickers.py --all       # backfill all dates in daily_snapshots
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from collections import defaultdict

DB_PATH = "marketpulse_v5.db"


def aggregate_for_date(conn, date_str):
    rows = conn.execute("""
        SELECT ticker, entity_name, entity_type, close_price, percent_change
        FROM daily_snapshots
        WHERE date = ?
    """, (date_str,)).fetchall()

    if not rows:
        print(f"  No snapshot data for {date_str}")
        return []

    buckets = defaultdict(lambda: {
        "entity_cards": [], "entity_types": set(),
        "close_price": None, "percent_change": None,
    })

    for ticker, entity_name, entity_type, close_price, pct in rows:
        b = buckets[ticker]
        if entity_name not in b["entity_cards"]:
            b["entity_cards"].append(entity_name)
        if entity_type:
            b["entity_types"].add(entity_type)
        if close_price is not None:
            b["close_price"] = close_price
        if pct is not None:
            b["percent_change"] = pct

    results = []
    for ticker, b in buckets.items():
        results.append({
            "date": date_str,
            "ticker": ticker,
            "appearance_count": len(b["entity_cards"]),
            "entity_cards": json.dumps(b["entity_cards"]),
            "entity_types": json.dumps(sorted(b["entity_types"])),
            "close_price": b["close_price"],
            "percent_change": b["percent_change"],
        })

    return sorted(results, key=lambda x: x["appearance_count"], reverse=True)


def save(conn, rows):
    saved = 0
    for r in rows:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO ticker_frequency
                    (date, ticker, appearance_count, entity_cards, entity_types,
                     close_price, percent_change)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                r["date"], r["ticker"], r["appearance_count"],
                r["entity_cards"], r["entity_types"],
                r["close_price"], r["percent_change"],
            ))
            saved += 1
        except Exception as e:
            print(f"  Error ({r['ticker']}): {e}")
    conn.commit()
    return saved


def get_all_dates(conn):
    rows = conn.execute(
        "SELECT DISTINCT date FROM daily_snapshots ORDER BY date"
    ).fetchall()
    return [r[0] for r in rows]


def main():
    args = sys.argv[1:]
    conn = sqlite3.connect(DB_PATH)

    if args and args[0] == "--all":
        dates = get_all_dates(conn)
        print(f"=== Backfilling {len(dates)} dates ===")
        for d in dates:
            rows = aggregate_for_date(conn, d)
            saved = save(conn, rows)
            print(f"  {d}: {saved} tickers")
    else:
        date_str = args[0] if args else datetime.now(timezone.utc).date().isoformat()
        print(f"=== MarketPulse — Ticker Frequency ({date_str}) ===")
        rows = aggregate_for_date(conn, date_str)
        saved = save(conn, rows)
        print(f"  Saved {saved} ticker rows")
        print("\n  Top tickers by card appearances:")
        for r in rows[:10]:
            cards = json.loads(r["entity_cards"])
            pct = f"{r['percent_change']:+.2f}%" if r["percent_change"] is not None else "n/a"
            print(f"    {r['ticker']:8} {r['appearance_count']} cards  {pct}  "
                  f"via: {', '.join(cards[:3])}")

    conn.close()
    print("=== Done ===")


if __name__ == "__main__":
    main()
