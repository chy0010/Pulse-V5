"""
MarketPulse Analyst Agent
A Claude-powered agent with tools to query the MarketPulse database and answer
questions about entity sentiment, stock signals, and divergence alerts.

Usage:
    python agent.py
    python agent.py "What drove NVDA sentiment this week?"
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "marketpulse_v5.db"
MODEL = "claude-sonnet-4-20250514"

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_top_entities",
        "description": (
            "Get the most-mentioned entities for a given date, sorted by mention count. "
            "Returns entity name, type, sentiment, ticker, and mention count."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format. Use today's date if not specified.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of entities to return. Default 10.",
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["bullish", "bearish", "mixed", "neutral", "all"],
                    "description": "Filter by sentiment. Default 'all'.",
                },
            },
            "required": ["date"],
        },
    },
    {
        "name": "get_ticker_history",
        "description": (
            "Get sentiment and price history for a specific ticker over the last N days. "
            "Shows weighted sentiment score and price change per day."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol e.g. NVDA, TSLA, XOM",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to retrieve. Default 7.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_divergence_alerts",
        "description": (
            "Get sentiment-vs-price divergence alerts. "
            "Bullish divergence = YouTube positive but price dropped. "
            "Bearish divergence = YouTube negative but price rose."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days back to look. Default 30.",
                },
                "divergence_type": {
                    "type": "string",
                    "enum": ["bullish", "bearish", "all"],
                    "description": "Filter by divergence type. Default 'all'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_entity_details",
        "description": (
            "Get full details for a specific entity on a given date — "
            "why people are talking about it, what they're saying, key quotes, and which tickers it affects."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity e.g. 'NVIDIA', 'Donald Trump', 'Iran'",
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format. Use most recent date if not specified.",
                },
            },
            "required": ["entity_name"],
        },
    },
    {
        "name": "search_entities",
        "description": (
            "Search for entities by name across all dates. "
            "Useful for finding when a topic first appeared or tracking it over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term — partial match on entity name",
                },
                "days": {
                    "type": "integer",
                    "description": "How many days back to search. Default 30.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_top_tickers",
        "description": (
            "Get the most-mentioned tickers for a given date with their price change and sentiment score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of tickers to return. Default 10.",
                },
            },
            "required": ["date"],
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

def get_top_entities(date: str, limit: int = 10, sentiment: str = "all") -> dict:
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT entity_name, entity_type, sentiment_label, ticker, mention_count
        FROM daily_snapshots
        WHERE date = ? AND affected_relationship = 'direct'
    """
    params = [date]
    if sentiment != "all":
        query += " AND sentiment_label = ?"
        params.append(sentiment)
    query += " ORDER BY mention_count DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return {"error": f"No entity data found for {date}. Available dates may differ."}

    return {
        "date": date,
        "entities": [
            {
                "name": r[0], "type": r[1], "sentiment": r[2],
                "ticker": r[3], "mentions": r[4],
            }
            for r in rows
        ],
    }


def get_ticker_history(ticker: str, days: int = 7) -> dict:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT date, total_mentions, weighted_sentiment_score, close_price, percent_change
        FROM ticker_daily
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT ?
    """, (ticker.upper(), days)).fetchall()
    conn.close()

    if not rows:
        return {"error": f"No history found for ticker {ticker}."}

    return {
        "ticker": ticker.upper(),
        "history": [
            {
                "date": r[0], "mentions": r[1],
                "sentiment_score": r[2], "close_price": r[3], "percent_change": r[4],
            }
            for r in rows
        ],
    }


def get_divergence_alerts(days: int = 30, divergence_type: str = "all") -> dict:
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT date, ticker, divergence_type, sentiment_score, price_change, total_mentions, note FROM divergence_log WHERE 1=1"
    params = []
    if divergence_type != "all":
        query += " AND divergence_type = ?"
        params.append(divergence_type)
    query += " ORDER BY date DESC LIMIT ?"
    params.append(days)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return {"message": "No divergence alerts found for the specified period."}

    return {
        "alerts": [
            {
                "date": r[0], "ticker": r[1], "type": r[2],
                "sentiment_score": r[3], "price_change": r[4],
                "mentions": r[5], "note": r[6],
            }
            for r in rows
        ],
    }


def get_entity_details(entity_name: str, date: str = None) -> dict:
    conn = sqlite3.connect(DB_PATH)

    if not date:
        row = conn.execute(
            "SELECT MAX(date) FROM daily_snapshots WHERE LOWER(entity_name) LIKE ?",
            (f"%{entity_name.lower()}%",)
        ).fetchone()
        date = row[0] if row and row[0] else datetime.now(timezone.utc).date().isoformat()

    # Load from _companies.json report for full details
    import os
    report_path = os.path.join("reports", f"{date}_companies.json")
    if os.path.exists(report_path):
        with open(report_path) as f:
            report = json.load(f)
        for e in report.get("entities", []):
            if entity_name.lower() in e.get("name", "").lower():
                conn.close()
                return {
                    "date": date,
                    "name": e.get("name"),
                    "type": e.get("type"),
                    "sentiment": e.get("sentiment"),
                    "ticker": e.get("ticker"),
                    "mention_count": e.get("mention_count"),
                    "why_talking": e.get("why_talking"),
                    "what_saying": e.get("what_saying"),
                    "key_quotes": e.get("key_quotes", [])[:3],
                    "affected_tickers": e.get("affected_tickers", []),
                }

    conn.close()
    return {"error": f"No details found for '{entity_name}' on {date}."}


def search_entities(query: str, days: int = 30) -> dict:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT DISTINCT entity_name, entity_type, date, sentiment_label, mention_count
        FROM daily_snapshots
        WHERE LOWER(entity_name) LIKE ?
        ORDER BY date DESC, mention_count DESC
        LIMIT 20
    """, (f"%{query.lower()}%",)).fetchall()
    conn.close()

    if not rows:
        return {"message": f"No entities found matching '{query}'."}

    return {
        "query": query,
        "results": [
            {"name": r[0], "type": r[1], "date": r[2], "sentiment": r[3], "mentions": r[4]}
            for r in rows
        ],
    }


def get_top_tickers(date: str, limit: int = 10) -> dict:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT ticker, total_mentions, weighted_sentiment_score, close_price, percent_change
        FROM ticker_daily
        WHERE date = ?
        ORDER BY total_mentions DESC
        LIMIT ?
    """, (date, limit)).fetchall()
    conn.close()

    if not rows:
        return {"error": f"No ticker data found for {date}."}

    return {
        "date": date,
        "tickers": [
            {
                "ticker": r[0], "mentions": r[1], "sentiment_score": r[2],
                "close_price": r[3], "percent_change": r[4],
            }
            for r in rows
        ],
    }


# ── Tool dispatcher ───────────────────────────────────────────────────────────

TOOL_MAP = {
    "get_top_entities": get_top_entities,
    "get_ticker_history": get_ticker_history,
    "get_divergence_alerts": get_divergence_alerts,
    "get_entity_details": get_entity_details,
    "search_entities": search_entities,
    "get_top_tickers": get_top_tickers,
}


def run_tool(name: str, inputs: dict) -> str:
    fn = TOOL_MAP.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    result = fn(**inputs)
    return json.dumps(result, indent=2)


# ── Agent loop ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the MarketPulse Analyst — an AI agent with access to a real-time consumer intelligence database.

The database contains daily YouTube comment analysis across 71 channels:
- Entity extraction: companies, people, events, technologies mentioned in comments
- Stock prices: daily OHLCV for all mentioned tickers
- Sentiment scores: weighted bullish/bearish sentiment per ticker per day
- Divergence alerts: when YouTube sentiment disagrees with price action

Today's date: {today}

Use your tools to answer questions accurately. Always ground your answers in actual data from the tools.
Be specific — cite numbers, dates, and quotes when available. If data is missing for a date, say so clearly."""


def run_agent(question: str, verbose: bool = True) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    today = datetime.now(timezone.utc).date().isoformat()

    messages = [{"role": "user", "content": question}]
    system = SYSTEM_PROMPT.format(today=today)

    if verbose:
        print(f"\n🤖 Agent thinking...\n")

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Collect any text while processing
        for block in response.content:
            if block.type == "text" and block.text.strip() and verbose:
                print(block.text)

        # Done — no more tool calls
        if response.stop_reason == "end_turn":
            for block in response.content:
                if block.type == "text":
                    return block.text
            return ""

        # Process tool calls
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            break

        # Add assistant message with tool calls
        messages.append({"role": "assistant", "content": response.content})

        # Execute tools and collect results
        tool_results = []
        for tool_call in tool_calls:
            if verbose:
                print(f"  → Calling {tool_call.name}({json.dumps(tool_call.input)})")
            result = run_tool(tool_call.name, tool_call.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    return ""


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    # Single question mode
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        answer = run_agent(question)
        print(f"\n{answer}")
        return

    # Interactive mode
    print("=" * 60)
    print("  MarketPulse Analyst Agent")
    print("  Ask anything about your market data.")
    print("  Type 'exit' to quit.")
    print("=" * 60)

    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "q"):
            print("Goodbye.")
            break

        answer = run_agent(question)
        print(f"\nAgent: {answer}")


if __name__ == "__main__":
    main()

