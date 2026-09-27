---
doc: scope
status: approved
---

# AdvancedSearchTool — Multi-Timeframe Stock Screener

A Python-based stock screener that detects candlestick patterns and indicator signals across two timeframes, scores each ticker, and surfaces the best long and short opportunities in a lightweight dashboard UI.

## The Unique Kernel
Most screeners show you one signal at a time. This one layers pattern recognition (candlestick formations) with indicator confluence (MACD, Bollinger Bands) across two timeframes — daily for trend direction and 1-hour for entry trigger — then collapses that into a single scored ranking so you can see the strongest setups at a glance, with the reasoning right alongside the score.

## Who It's For
A technically-minded trader (the builder) who already understands candlestick patterns and indicator signals but currently has to manually check each ticker one by one. They want a fast morning scan that tells them which setups are worth acting on today, with enough evidence to trust the call.

## The Core Loop
Run the screener → dashboard loads in the browser → two ranked tables appear (LONG and SHORT) → each row shows ticker, triggered signals as plain-text reasons, and a confluence score → scan the top entries, decide which to trade.

## Inspiration & Identity
Clean, data-dense financial tooling. Think Bloomberg terminal clarity without the noise — a dark or neutral dashboard with tight typography, clear hierarchy, and no decoration that doesn't carry information. Every element on screen should answer a question a trader would actually ask.

## Why This Matters to the Learner
Personal trading decision support — replacing a slow, manual multi-tab chart review with a single tool that does the pattern and indicator work. Also a hands-on introduction to `yfinance` and `pandas-ta` in a real multi-file Python project, and a live demonstration of how a tight spec drives clean agent-built code.

## What "Working" Looks Like
Run a single command. A browser window (or local web app) opens showing two ranked tables — **LONG** and **SHORT** — populated with tickers from the watchlist. Each row reads something like:

> `NVDA — Hammer (1h), MACD crossover bullish (daily) — Score: +3`

The "oh, that's it" moment: the top LONG entry has two or three reasons listed and the score makes sense relative to the others. The screener caught something you'd have had to check manually.

## The POC Boundary
**In:**
- Fixed watchlist: AAPL, MSFT, NVDA, TSLA, SPY (configurable in a single config file)
- Two native yfinance timeframes: daily and 1-hour
- Candlestick patterns: Hammer, Engulfing (bullish/bearish), Morning Star, Evening Star, Doji
- Indicator signals: MACD bullish crossover (+1 long), Bollinger Band upper-band breakout (+1 short)
- Point-based confluence scoring: bullish signals → LONG score, bearish signals → SHORT score
- Lightweight dashboard UI: two ranked tables (LONG / SHORT) with ticker, reasons, score
- Single command to fetch, scan, score, and display

**Out for PoC:**
- 4-hour timeframe (not a native yfinance interval)
- Real-time streaming or auto-refresh
- User authentication or multi-user support
- Backtesting or historical performance tracking
- Charting or candlestick visualizations
- Alerts or notifications
- Deployment to a remote server

## Later
- Add weekly timeframe for macro trend context
- Interactive chart overlays showing detected patterns on the candles
- Configurable scoring weights per signal type
- Watchlist editor in the UI
- Auto-refresh on a schedule
- Export to CSV or JSON

## Explicitly Cut
- **4-hour timeframe** — not a native yfinance interval; resampling adds complexity without meaningful PoC value. Daily + 1h covers trend + trigger cleanly.
- **CLI-only output** — raw terminal tables don't serve the "clear evidence" goal. Dashboard UI is in scope.
- **Backtesting** — requires historical labeling and a results framework; too much scope for a PoC, valuable later.
- **Real-time streaming** — polling or websocket feeds add infrastructure complexity; a fresh scan on demand is sufficient to prove the concept.
