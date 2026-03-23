"""
detect_divergences.py
Reads ticker_daily and daily_snapshots for a given date and flags
sentiment-vs-price divergences. Writes results to divergence_log.

Bullish Divergence: weighted_sentiment_score > 0.7 AND percent_change < -2%
Bearish Divergence: weighted_sentiment_score < 0.3 AND percent_change > +2%

Usage:
    python detect_divergences.py              # today
    python detect_divergences.py 2026-03-19
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = "marketpulse_v5.db"

BULLISH_SENTIMENT_THRESHOLD = 0.65   # sentiment above this = strongly bullish
BEARISH_SENTIMENT_THRESHOLD = 0.35   # sentiment below this = strongly bearish
PRICE_MOVE_THRESHOLD = 2.0           # % price move that counts as significant
MIN_MENTIONS = 3                     # ignore tickers with too few mentions


def get_ticker_daily(conn, date_str):
    rows = conn.execute("""
        SELECT ticker, total_mentions, weighted_sentiment_score, close_price, percent_change
        FROM ticker_daily
        WHERE date = ?
    """, (date_str,)).fetchall()
    return [
        {
            "ticker": r[0],
            "total_mentions": r[1],
            "weighted_sentiment_score": r[2],
            "close_price": r[3],
            "percent_change": r[4],
        }
        for r in rows
    ]


def get_driving_entities(conn, date_str, ticker):
    """Return entity names that reference this ticker today, sorted by mentions."""
    rows = conn.execute("""
        SELECT entity_name, mention_count, sentiment_label
        FROM daily_snapshots
        WHERE date = ? AND ticker = ?
        ORDER BY mention_count DESC
        LIMIT 5
    """, (date_str, ticker)).fetchall()
    return [{"name": r[0], "mentions": r[1], "sentiment": r[2]} for r in rows]


def detect(conn, date_str):
    ticker_rows = get_ticker_daily(conn, date_str)
    alerts = []

    for row in ticker_rows:
        ticker = row["ticker"]
        sentiment = row["weighted_sentiment_score"]
        pct = row["percent_change"]
        mentions = row["total_mentions"]

        if pct is None or sentiment is None:
            continue
        if mentions < MIN_MENTIONS:
            continue

        divergence_type = None
        if sentiment >= BULLISH_SENTIMENT_THRESHOLD and pct <= -PRICE_MOVE_THRESHOLD:
            divergence_type = "bullish"
        elif sentiment <= BEARISH_SENTIMENT_THRESHOLD and pct >= PRICE_MOVE_THRESHOLD:
            divergence_type = "bearish"

        if not divergence_type:
            continue

        entities = get_driving_entities(conn, date_str, ticker)
        entity_names = [e["name"] for e in entities]

        if divergence_type == "bullish":
            note = (
                f"YouTube sentiment is Bullish ({sentiment:.0%}) "
                f"but price dropped {pct:.2f}% — potential opportunity."
            )
        else:
            note = (
                f"YouTube sentiment is Bearish ({sentiment:.0%}) "
                f"but price rose {pct:.2f}% — possible overreaction."
            )

        alerts.append({
            "date": date_str,
            "ticker": ticker,
            "divergence_type": divergence_type,
            "sentiment_score": round(sentiment, 4),
            "price_change": round(pct, 4),
            "total_mentions": mentions,
            "driving_entities": json.dumps(entity_names),
            "note": note,
        })

    return alerts


def save_alerts(conn, alerts):
    saved = 0
    for a in alerts:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO divergence_log
                    (date, ticker, divergence_type, sentiment_score, price_change,
                     total_mentions, driving_entities, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                a["date"], a["ticker"], a["divergence_type"], a["sentiment_score"],
                a["price_change"], a["total_mentions"], a["driving_entities"], a["note"],
            ))
            saved += 1
        except Exception as e:
            print(f"  Insert error ({a['ticker']}): {e}")
    conn.commit()
    return saved


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).date().isoformat()
    print(f"=== MarketPulse — Divergence Detection ({date_str}) ===")

    conn = sqlite3.connect(DB_PATH)
    alerts = detect(conn, date_str)
    saved = save_alerts(conn, alerts)
    conn.close()

    if not alerts:
        print("  No divergences detected today.")
    else:
        print(f"  {saved} divergence(s) logged:\n")
        for a in alerts:
            tag = "🟢 BULLISH DIV" if a["divergence_type"] == "bullish" else "🔴 BEARISH DIV"
            print(f"  {tag}  {a['ticker']:8}  sentiment={a['sentiment_score']:.2f}  "
                  f"price={a['price_change']:+.2f}%  mentions={a['total_mentions']}")
            print(f"    → {a['note']}")
            print(f"    → Driven by: {json.loads(a['driving_entities'])}")
            print()

    print("=== Done ===")


if __name__ == "__main__":
    main()
