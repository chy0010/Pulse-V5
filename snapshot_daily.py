"""
snapshot_daily.py
Reads today's entity report + stock prices and writes to:
  - daily_snapshots  (one row per entity-ticker pair)
  - ticker_daily     (one aggregated row per ticker)

Run after fetch_stock_prices.py in the daily pipeline:
  python snapshot_daily.py              # uses latest report
  python snapshot_daily.py 2026-03-19  # specific date
"""

import os
import json
import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = "marketpulse_v5.db"
REPORTS_DIR = "reports"


def load_report(date_str):
    path = os.path.join(REPORTS_DIR, f"{date_str}_companies.json")
    if not os.path.exists(path):
        print(f"  Report not found: {path}")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_prices(conn, date_str):
    """Return {ticker: {close, percent_change, volume}} for the given date."""
    rows = conn.execute(
        "SELECT ticker, close, percent_change, volume FROM stock_prices WHERE date = ?",
        (date_str,)
    ).fetchall()
    return {r[0]: {"close": r[1], "percent_change": r[2], "volume": r[3]} for r in rows}


SENTIMENT_SCORE = {"bullish": 1.0, "mixed": 0.5, "neutral": 0.5, "bearish": 0.0}


def build_snapshot_rows(entities, prices, date_str):
    """
    Expand each entity into one row per ticker it is linked to.
    Returns list of dicts ready for daily_snapshots.
    """
    rows = []
    for e in entities:
        name = e.get("name", "")
        etype = e.get("type", "other")
        mentions = e.get("mention_count", 0)
        sentiment_label = e.get("sentiment", "neutral")
        sentiment_score = SENTIMENT_SCORE.get(sentiment_label, 0.5)

        base = {
            "date": date_str,
            "entity_name": name,
            "entity_type": etype,
            "mention_count": mentions,
            "sentiment_label": sentiment_label,
            "sentiment_score": sentiment_score,
        }

        # Direct ticker
        if e.get("ticker"):
            t = e["ticker"]
            p = prices.get(t, {})
            rows.append({**base, "ticker": t, "close_price": p.get("close"),
                         "percent_change": p.get("percent_change"), "affected_relationship": "direct"})

        # Affected tickers (geo/political → market sectors)
        for t in e.get("affected_tickers", []):
            p = prices.get(t, {})
            rows.append({**base, "ticker": t, "close_price": p.get("close"),
                         "percent_change": p.get("percent_change"), "affected_relationship": "indirect"})

        # Investor tickers (private company → public backer)
        for t in e.get("investor_tickers", []):
            p = prices.get(t, {})
            rows.append({**base, "ticker": t, "close_price": p.get("close"),
                         "percent_change": p.get("percent_change"), "affected_relationship": "investor"})

    return rows


def build_ticker_daily_rows(snapshot_rows, prices, date_str):
    """
    Aggregate snapshot rows into one row per ticker for ticker_daily.
    Weighted sentiment = sum(sentiment_score * mention_count) / sum(mention_count)
    """
    from collections import defaultdict

    buckets = defaultdict(lambda: {"total_mentions": 0, "weighted_sum": 0.0})
    for row in snapshot_rows:
        t = row["ticker"]
        m = row["mention_count"] or 0
        s = row.get("sentiment_score", 0.5)
        buckets[t]["total_mentions"] += m
        buckets[t]["weighted_sum"] += s * m

    result = []
    for ticker, agg in buckets.items():
        p = prices.get(ticker, {})
        total = agg["total_mentions"]
        weighted_sentiment = round(agg["weighted_sum"] / total, 4) if total else None
        result.append({
            "date": date_str,
            "ticker": ticker,
            "total_mentions": total,
            "weighted_sentiment_score": weighted_sentiment,
            "close_price": p.get("close"),
            "percent_change": p.get("percent_change"),
            "volume": p.get("volume"),
        })

    return result


def save_snapshots(conn, rows):
    saved = 0
    for r in rows:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO daily_snapshots
                    (date, entity_name, entity_type, ticker, close_price, percent_change,
                     sentiment_score, sentiment_label, mention_count, affected_relationship)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["date"], r["entity_name"], r["entity_type"], r["ticker"],
                r["close_price"], r["percent_change"],
                r.get("sentiment_score"), r.get("sentiment_label"),
                r["mention_count"], r["affected_relationship"],
            ))
            saved += 1
        except Exception as e:
            print(f"  Snapshot insert error ({r['entity_name']} / {r['ticker']}): {e}")
    conn.commit()
    return saved


def save_ticker_daily(conn, rows):
    saved = 0
    for r in rows:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO ticker_daily
                    (date, ticker, total_mentions, weighted_sentiment_score,
                     close_price, percent_change, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                r["date"], r["ticker"], r["total_mentions"],
                r.get("weighted_sentiment_score"),
                r["close_price"], r["percent_change"], r["volume"],
            ))
            saved += 1
        except Exception as e:
            print(f"  ticker_daily insert error ({r['ticker']}): {e}")
    conn.commit()
    return saved


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).date().isoformat()
    print(f"=== MarketPulse — Daily Snapshot ({date_str}) ===")

    report = load_report(date_str)
    entities = report.get("entities", [])

    conn = sqlite3.connect(DB_PATH)
    prices = load_prices(conn, date_str)
    print(f"  Entities: {len(entities)} | Price records: {len(prices)}")

    snapshot_rows = build_snapshot_rows(entities, prices, date_str)
    ticker_daily_rows = build_ticker_daily_rows(snapshot_rows, prices, date_str)

    snap_saved = save_snapshots(conn, snapshot_rows)
    tick_saved = save_ticker_daily(conn, ticker_daily_rows)
    conn.close()

    print(f"  daily_snapshots: {snap_saved} rows saved")
    print(f"  ticker_daily:    {tick_saved} rows saved")

    # Quick summary: top 5 tickers by mentions
    print("\n  Top tickers by mentions today:")
    top = sorted(ticker_daily_rows, key=lambda x: x["total_mentions"], reverse=True)[:5]
    for r in top:
        pct = f"{r['percent_change']:+.2f}%" if r["percent_change"] is not None else "n/a"
        print(f"    {r['ticker']:8} mentions={r['total_mentions']:3}  price={pct}")

    print(f"\n=== Done ===")


if __name__ == "__main__":
    main()
