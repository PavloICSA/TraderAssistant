---
doc: prd
status: approved
---

# Multi-Timeframe Stock Screener — Product Requirements

A single-page browser dashboard that fetches stock data, detects candlestick patterns and indicator signals across two timeframes, scores each ticker, and presents ranked LONG and SHORT opportunities with plain-text reasoning — for a technically-minded trader who wants a fast morning scan without manually checking each chart.
Source: `scope.md > The Unique Kernel`, `scope.md > Who It's For`.

---

## The Core Journey

1. User runs a single command in the terminal to start the app.
2. A native desktop window opens (embedded webview — no external browser required) showing the dashboard.
3. On first load, tables are empty — no previous scan data exists yet.
4. User clicks **"Run Fresh Scan"**.
5. Button disables and shows loading state ("Scanning markets..." + spinner).
6. Backend fetches OHLCV data for all watchlist tickers across daily and 1h timeframes, detects patterns and signals, scores each ticker.
7. On success: tables populate with ranked results, button returns to active state, timestamp updates.
8. On failure: error banner appears, last successful scan results (if any) remain visible, button returns to active state.
9. User reads the LONG and SHORT ranked tables, uses the reasoning column to decide which setups to act on.
10. User can open the watchlist settings, add or remove tickers, save — the status indicator updates to reflect the new list, and the next scan uses the updated watchlist.

Source: `scope.md > The Core Loop`, `scope.md > What "Working" Looks Like`.

---

## Screens and Layout

Single page. Three vertical zones:

### Header
- Title: **"Multi-Timeframe Stock Screener"**
- **"Run Fresh Scan"** button — primary action, prominent
- Status indicator (subdued): last scan timestamp + current watchlist tickers (e.g., "Last scan: 09:42 AM · Watchlist: AAPL, MSFT, NVDA, TSLA, SPY")
- **Settings / Watchlist** access — a button or icon that opens the watchlist editor (modal or inline panel)

### Main Content Area
Two tables, displayed as two columns on wide screens, stacked vertically on narrow screens:

**Strong Long Opportunities (left / top)**
- Ranked by descending score (highest positive score first)
- Columns: Ticker | Score | Triggered Signals / Reasoning
- Example row: `NVDA | +3 | Hammer (1h), MACD bullish crossover (daily), Bullish Engulfing (daily)`

**Strong Short Opportunities (right / bottom)**
- Ranked by descending absolute score (most negative first, e.g., −3 before −1)
- Columns: Ticker | Score | Triggered Signals / Reasoning
- Example row: `TSLA | −2 | Upper BB breakout (daily), Evening Star (1h)`

Tickers with a net score of 0 (no signals fired) are omitted from both tables.

### Footer
Brief explanatory note:
> "Scoring: +1 per bullish confirmation (candlestick pattern, MACD bullish crossover, lower BB touch, RSI < 30), −1 per bearish confirmation (bearish pattern, MACD bearish crossover, upper BB touch, RSI > 70). Each signal scored independently on Daily (trend) and 1h (entry trigger) timeframes."

---

## Look and Feel

- **Tone:** Clean, data-dense, professional. Bloomberg-terminal clarity without the noise.
- **Color scheme:** Dark or neutral background. Use color purposefully: green accents for LONG signals, red for SHORT, muted neutrals for chrome.
- **Typography:** Tight, readable monospace or semi-monospace for ticker symbols and scores; clean sans-serif for labels and body text.
- **Density:** Tables should be compact — fit as many rows as possible without scrolling on a standard laptop screen.
- **No decorative elements** that don't carry information.
- Framework: pywebview — native desktop window rendering HTML/CSS/JS, wired to Python backend. No external browser. No build step.

---

## Features and Behavior

### Scan Trigger

- As a trader, I want to trigger a fresh scan on demand so I always get up-to-date signal data.
  - [ ] Clicking "Run Fresh Scan" initiates the backend scan
  - [ ] Button text changes to "Scanning markets..." and a spinner appears during the scan
  - [ ] Button is disabled while scan is in progress (no double-click)
  - [ ] On scan completion, button returns to normal active state
  - [ ] Status indicator timestamp updates to reflect the completed scan time

### Results Display

- As a trader, I want to see ranked LONG and SHORT opportunities so I can quickly identify the strongest setups.
  - [ ] LONG table shows all tickers with net score > 0, ranked by descending score (highest first)
  - [ ] SHORT table shows all tickers with net score < 0, ranked by descending absolute score (most negative first, e.g., −3 before −1)
  - [ ] Tickers with score = 0 are excluded from both tables
  - [ ] Each row shows: Ticker, Score, and all triggered signals as plain-text reasons
  - [ ] Signals include the timeframe they fired on (e.g., "Hammer (1h)")
  - [ ] Tables are sorted correctly after every scan

### Watchlist Management

- As a trader, I want to manage my watchlist from the UI so I can change it without editing code.
  - [ ] A settings control in the header opens a watchlist editor (modal or inline panel)
  - [ ] Editor shows the current list of tickers
  - [ ] User can add a ticker by typing a symbol and confirming
  - [ ] User can remove an existing ticker
  - [ ] Saving the watchlist closes the editor and immediately updates the status indicator
  - [ ] The next scan uses the updated watchlist
  - [ ] Watchlist persists between sessions (survives app restart)

### Error Handling

- As a trader, I want clear feedback when something goes wrong so I'm not left with a blank or broken screen.
  - [ ] A scan failure shows a friendly error banner near the top (e.g., "⚠️ Scan failed: Unable to fetch data from Yahoo Finance. Please check your connection and try again.")
  - [ ] Error banner is dismissible or auto-dismisses after a reasonable interval
  - [ ] Last successful scan results remain visible when a scan fails
  - [ ] If no previous scan exists and the first scan fails, tables show an empty state with a clear message (e.g., "No data yet — run a scan to get started.")

---

## States and Boundaries

- **First load (no prior scan):** Tables are empty. A neutral empty-state message is shown in each table: "No data yet — run a scan to get started." Status indicator shows no timestamp.
- **Scan in progress:** Button disabled, spinner visible, existing results remain in tables until new results arrive.
- **Scan success:** Tables refresh with new results. Timestamp updates. Button re-enables.
- **Scan failure:** Error banner appears. Tables retain last successful results (or empty state if none). Button re-enables.
- **Score = 0:** Ticker does not appear in either table. It is silently excluded (not an error).
- **Watchlist empty:** If the user removes all tickers, the scan should show an appropriate message rather than crashing (e.g., "Watchlist is empty — add tickers to get started.").
- **Persistence:** Watchlist persists between app restarts. Scan results do not persist — each session starts with empty tables until a scan is run.

---

## Product Decisions

- **Native desktop window via embedded webview (pywebview)** — no external browser required; HTML/CSS renders inside a native app window for full visual quality without browser dependency. Python backend wired to the UI via a local API.
- **Both tables sorted descending by score magnitude** — LONG highest score first, SHORT most-negative first (highest absolute value first). Both surfaces answer the same question: "what's the strongest setup right now?"
- **Tie-breaking:** primary — higher 1h volume or stronger absolute % price change; secondary — alphabetical by ticker symbol.
- **Doji context rule** — bullish after downtrend (recent lower lows), bearish after uptrend (recent higher highs), evaluated on the same timeframe as the candle.
- **MACD parameters:** 12, 26, 9 (standard) — confirmed.
- **Bollinger Band parameters:** 20-period SMA, 2σ (standard) — confirmed.
- **On-demand scan only** — user triggers the scan manually; no auto-refresh or scheduled polling. Keeps the PoC simple and avoids rate-limit edge cases.
- **Two timeframes: daily + 1h** — daily for trend direction, 1h for entry trigger. 4h dropped (not a native yfinance interval).
- **Point-based scoring** — +1 per bullish signal, −1 per bearish signal, summed across all timeframes. Simple, transparent, auditable from the reasoning column.
- **Scan results do not persist** — the tool is a morning-scan instrument, not a historical log. Each run is fresh.
- **Watchlist persists** — stored in a local config file, editable from the UI. Default: AAPL, MSFT, NVDA, TSLA, SPY.
- **Tickers with score = 0 excluded** — no signal means no opinion; showing them would add noise.

---

## Candlestick Patterns in Scope

Bullish (contribute +1 each to LONG score):
- Hammer (1-candle)
- Bullish Engulfing (2-candle)
- Morning Star (3-candle)
- Bullish Doji — Doji appearing after a clear downward trend (recent lower lows on the same timeframe); classified as bullish reversal signal

Bearish (contribute −1 each to SHORT score):
- Shooting Star (1-candle)
- Bearish Engulfing (2-candle)
- Evening Star (3-candle)
- Bearish Doji — Doji appearing after a clear upward trend (recent higher highs on the same timeframe); classified as bearish reversal signal

Doji trend context is evaluated on the same timeframe the candle appears on (daily or 1h).

Source: `scope.md > The POC Boundary`.

## Indicator Signals in Scope

**Bullish (contribute +1 each to LONG score):**
- MACD bullish crossover — MACD line crosses above signal line from below (12, 26, 9)
- Bollinger Band lower-band touch/cross — close at or below lower band (20-period SMA, 2σ)
- RSI oversold — RSI(14) < 30

**Bearish (contribute −1 each to SHORT score):**
- MACD bearish crossover — MACD line crosses below signal line from above (12, 26, 9)
- Bollinger Band upper-band touch/cross — close at or above upper band (20-period SMA, 2σ)
- RSI overbought — RSI(14) > 70

All signals evaluated independently on both daily and 1h timeframes (each timeframe fires its own +1 / −1).

---

## What We're Building

- Single-page pywebview desktop app (native window, HTML/CSS/JS frontend, Python backend)
- On-demand scan triggered from the UI
- yfinance data fetch for daily and 1h OHLCV across the watchlist
- Candlestick pattern detection: Hammer, Engulfing (bull/bear), Morning Star, Evening Star, Doji (bull/bear context)
- Indicator signal detection: MACD bullish crossover, Bollinger Band upper-band breakout
- Point-based confluence scorer producing a net score per ticker
- Ranked LONG and SHORT results tables with ticker, score, and plain-text signal reasoning
- Watchlist editor in the UI (add/remove tickers, persisted to local config)
- Loading state, error banner, and empty state handling

---

## Deferred From the POC

- **4-hour timeframe** — not a native yfinance interval; excluded by design
- **Weekly timeframe** — adds macro context but not needed to prove the core idea
- **Real-time / auto-refresh** — scheduled polling adds infrastructure complexity
- **Charting / candlestick visualizations** — meaningful but out of PoC scope
- **Backtesting** — requires historical labeling and a results framework
- **Alerts and notifications** — deferred; on-demand scan is sufficient
- **Multi-user / authentication** — single local user only
- **Deployment to remote server** — local-only for PoC

---

## Non-Goals

- This is not a trading execution tool — no buy/sell orders, no brokerage integration.
- This is not a backtesting platform — no historical performance evaluation.
- This is not a real-time streaming terminal — data is fetched on demand.
- This does not provide financial advice — signals are mechanical and for personal research only.

---

## Open Questions

- **UI delivery library:** pywebview — confirmed. Specific integration pattern (JS↔Python bridge vs. local HTTP API) to be decided in `4-spec`.

_All other open questions from the initial draft have been resolved above._
