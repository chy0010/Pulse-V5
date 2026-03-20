"""
fetch_stock_prices.py
Fetches daily OHLCV price data for all tickers found in today's entity report.
Uses yfinance (free, no API key). Stores results in stock_prices SQLite table.

Usage:
    python fetch_stock_prices.py             # uses latest report
    python fetch_stock_prices.py 2026-03-19  # specific date
"""

import os
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

import yfinance as yf
from ticker_map import GEO_TICKERS, COMPANY_TICKER

DB_PATH = "marketpulse_v5.db"
REPORTS_DIR = "reports"

# Market indices always fetched every run
MARKET_INDICES = ["^GSPC", "^DJI", "^IXIC", "^RUT", "BTC-USD"]


def load_report(target_date=None):
    if target_date:
        path = os.path.join(REPORTS_DIR, f"{target_date}_companies.json")
    else:
        files = sorted(
            [f for f in os.listdir(REPORTS_DIR) if f.endswith("_companies.json")],
            reverse=True,
        )
        if not files:
            print("No reports found. Run analyze_companies.py first.")
            sys.exit(1)
        path = os.path.join(REPORTS_DIR, files[0])
    with open(path) as f:
        return json.load(f)


def collect_tickers(report):
    """Pull every unique ticker from the report (direct + affected + investor)."""
    tickers = set()
    for e in report["entities"]:
        if e.get("ticker"):
            tickers.add(e["ticker"])
        for t in e.get("affected_tickers", []):
            tickers.add(t)
        for t in e.get("investor_tickers", []):
            tickers.add(t)
    # Remove obviously non-US tickers for now (keep simple)
    tickers = {t for t in tickers if t and "." not in t or t.endswith(".NS")}
    return sorted(tickers)


def fetch_price(ticker, date_str):
    """
    Fetch OHLCV for a single ticker on a given date.
    Returns dict or None if data unavailable.
    """
    try:
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = start + timedelta(days=2)  # yfinance end is exclusive
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return None

        row = df.iloc[0]
        open_ = float(row["Open"].iloc[0]) if hasattr(row["Open"], "iloc") else float(row["Open"])
        close = float(row["Close"].iloc[0]) if hasattr(row["Close"], "iloc") else float(row["Close"])
        high = float(row["High"].iloc[0]) if hasattr(row["High"], "iloc") else float(row["High"])
        low = float(row["Low"].iloc[0]) if hasattr(row["Low"], "iloc") else float(row["Low"])
        volume = int(row["Volume"].iloc[0]) if hasattr(row["Volume"], "iloc") else int(row["Volume"])
        pct = round((close - open_) / open_ * 100, 4) if open_ else None

        return {
            "ticker": ticker,
            "date": date_str,
            "open": round(open_, 4),
            "close": round(close, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "volume": volume,
            "percent_change": pct,
        }
    except Exception as e:
        print(f"  [{ticker}] Error: {e}")
        return None


def save_prices(conn, prices):
    saved = 0
    for p in prices:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO stock_prices
                    (ticker, date, open, close, high, low, volume, percent_change)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p["ticker"], p["date"], p["open"], p["close"],
                p["high"], p["low"], p["volume"], p["percent_change"],
            ))
            saved += 1
        except Exception as e:
            print(f"  DB error for {p['ticker']}: {e}")
    conn.commit()
    return saved


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).date().isoformat()
    print(f"=== MarketPulse — Stock Price Fetch ({date_str}) ===")

    report = load_report(date_str)
    tickers = collect_tickers(report)
    # Always include market indices
    all_tickers = sorted(set(tickers) | set(MARKET_INDICES))
    print(f"  Tickers to fetch: {len(all_tickers)} ({len(MARKET_INDICES)} indices + {len(tickers)} entity tickers)")

    conn = sqlite3.connect(DB_PATH)
    prices = []
    for ticker in all_tickers:
        print(f"  Fetching {ticker}...", end=" ", flush=True)
        p = fetch_price(ticker, date_str)
        if p:
            prices.append(p)
            print(f"${p['close']} ({p['percent_change']:+.2f}%)")
        else:
            print("no data")

    saved = save_prices(conn, prices)
    conn.close()
    print(f"\n=== Done — {saved}/{len(tickers)} prices saved ===")


if __name__ == "__main__":
    main()
