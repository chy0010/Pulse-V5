# MarketPulse

> Daily consumer intelligence pipeline — 71 YouTube channels → Claude AI → stock market signals

MarketPulse ingests 2,500+ YouTube comments every morning across 71 curated channels, uses Claude Sonnet to extract named entities and market signals, maps them to stock tickers, and detects sentiment-vs-price divergences — all automated and running daily.

---

## What It Does

Most market sentiment tools read financial news. MarketPulse reads **real consumers** — the people who buy the products, use the services, and form opinions before prices move.

Each morning the pipeline:

1. Collects top comments from 71 YouTube channels (creators, educators, financial media)
2. Asks Claude to extract every named entity people are discussing and why
3. Fetches live stock prices for all mentioned tickers via yfinance
4. Flags **sentiment-vs-price divergences** — e.g. YouTube is bullish on NVDA but price dropped 3%
5. Saves everything to SQLite and generates an HTML dashboard

---

## Architecture

```
YouTube Data API v3
       ↓
ingest_youtube.py        — 71 channels, 48h lookback, replies on high-engagement comments
       ↓
analyze_daily.py         — Claude Sonnet → 5-section narrative intelligence report
analyze_companies.py     — Claude Sonnet → structured entity extraction (tool use)
       ↓
fetch_stock_prices.py    — yfinance → OHLCV for all mentioned tickers + market indices
       ↓
snapshot_daily.py        — joins entity sentiment + prices into daily_snapshots + ticker_daily
aggregate_tickers.py     — rolls up ticker frequency and card appearances
detect_divergences.py    — flags sentiment/price divergences → divergence_log
       ↓
website/                 — static HTML dashboard (index.html + companies.html)
```

**Automated daily at 9 AM ET via GitHub Actions.**

---

## Channel Strategy

| Tier | Channels | Comments/Video | Purpose |
|------|----------|---------------|---------|
| Tier 1 | 57 consumer/creator channels | 40 | Primary signal — real consumer opinions |
| Tier 2 | 14 institutional media (CNBC, Bloomberg, WSJ) | 20 | Secondary context — what Wall Street already knows |

The edge: topics Tier 1 consumers discuss that Tier 2 hasn't covered yet.

---

## Divergence Alerts

The core signal — when YouTube sentiment disagrees with price action:

- **Bullish divergence**: sentiment > 65% positive AND price down >2% → potential opportunity
- **Bearish divergence**: sentiment < 35% positive AND price up >2% → possible overreaction

---

## AI Stack

| Component | Model | Technique |
|-----------|-------|-----------|
| Entity extraction | Claude Sonnet | Tool use (structured output — no JSON parsing) |
| Narrative report | Claude Sonnet | Extended thinking + prompt caching |
| Ticker resolution | Static map + LLM fallback | 200+ company → ticker mappings |
| Geo/political mapping | Static map | Trump → [LMT, RTX, XOM], Fed → [JPM, BAC, GS], etc. |

---

## Database Schema

```
videos          — video metadata per channel
comments        — top comments + replies (fetched for 3+ reply threshold)
stock_prices    — daily OHLCV per ticker
daily_snapshots — entity × ticker × sentiment × price (one row per pair)
ticker_daily    — aggregated weighted sentiment score per ticker per day
ticker_frequency — how many entity cards mention each ticker
divergence_log  — flagged sentiment/price divergences
```

---

## Setup

```bash
git clone https://github.com/chy0010/Pulse-V5.git
cd Pulse-V5
pip install -r requirements.txt
cp .env.example .env   # add your API keys
python setup_db.py
```

**Required API keys** (add to `.env`):
```
YOUTUBE_API_KEY=...
ANTHROPIC_API_KEY=...
```

**Run the pipeline:**
```bash
python ingest_youtube.py
python analyze_daily.py
python analyze_companies.py
python fetch_stock_prices.py
python snapshot_daily.py
python aggregate_tickers.py
python detect_divergences.py
```

**View the dashboard:**
```bash
python view_web.py        # intelligence report
python view_companies.py  # entities & companies
```

---

## Sample Output (March 22, 2026)

**Top entities by mention volume:**
- Iran conflict → LMT (+6 cards), XOM (+6 cards), CVX (+6 cards), RTX (+5 cards)
- NVIDIA AI in gaming → NVDA (+3 cards)
- China trade tensions → TSM, AMD, QCOM, AAPL

**Pipeline stats:** 161 videos · 2,568 comments · 72 entities extracted

---

## Tech Stack

`Python` · `SQLite` · `Claude Sonnet (Anthropic)` · `YouTube Data API v3` · `yfinance` · `GitHub Actions`

---

Built by [Krishna](https://github.com/chy0010)
