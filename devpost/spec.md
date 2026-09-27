---
doc: spec
status: approved
---

# Multi-Timeframe Stock Screener — Technical Spec

## How This Works, In Plain Language

The app is a Python desktop program with two parts running at the same time.

**The backend** is a small Flask web server running on your laptop (localhost:5000). It knows how to fetch stock data, detect candlestick patterns and indicator signals, and score each ticker. It exposes a simple HTTP API that the frontend calls.

**The frontend** is a single HTML page with CSS and vanilla JavaScript, loaded inside a pywebview native desktop window — no browser opens, no browser needed. The page makes standard `fetch()` calls to the Flask server on localhost, exactly like a normal web page talking to a web server, except both are on your machine.

When you click "Run Fresh Scan", the JavaScript calls `POST /api/scan`. Flask fetches OHLCV data from Yahoo Finance via `yfinance`, runs the pattern and indicator detection via `pandas-ta`, scores each ticker, and returns a JSON response. The JavaScript updates the tables in place.

The watchlist is stored in a `config.json` file on disk. Flask reads it at scan time and exposes endpoints to read and update it. pywebview wraps both the Flask server and the HTML window into a single `python main.py` command.

That's the whole system: one Python process, one HTML file, one config file, one data library.

---

## The Core Journey Through the System

PRD ref: `prd.md > The Core Journey`

1. **User runs `python main.py`**
   → Flask server starts on localhost:5000
   → pywebview opens a native desktop window, loads `ui/index.html`
   → `index.html` fetches `GET /api/watchlist` to populate the status bar

2. **First load — no scan yet**
   → Tables show empty state: "No data yet — run a scan to get started."
   → Status bar shows current watchlist tickers, no timestamp

3. **User clicks "Run Fresh Scan"**
   → JS disables the button, shows "Scanning markets..." + spinner
   → JS calls `POST /api/scan`

4. **Flask `/api/scan` handler executes the pipeline:**
   a. Reads watchlist from `config.json`
   b. For each ticker: fetches daily OHLCV and 1h OHLCV via `yfinance`
   c. Runs pattern detection on both timeframes (candlestick patterns via `pandas-ta` or manual OHLCV logic)
   d. Runs indicator detection on both timeframes (MACD, Bollinger Bands via `pandas-ta`)
   e. Scores each ticker: sum of all +1 / −1 signals across both timeframes
   f. For ties: sorts by 1h volume descending, then absolute 1h % change descending, then alphabetical
   g. Returns JSON: `{ "long": [...], "short": [...], "timestamp": "..." }`

5. **JS receives response**
   → Splits results into LONG (score > 0) and SHORT (score < 0); score = 0 excluded
   → Renders ranked rows: Ticker | Score | Triggered Signals
   → Updates timestamp in status bar
   → Re-enables button

6. **Scan failure**
   → Flask returns HTTP 500 with `{ "error": "..." }`
   → JS shows error banner, retains previous table data, re-enables button

7. **User opens watchlist editor**
   → JS calls `GET /api/watchlist`, renders current tickers in a modal panel
   → User adds/removes tickers, clicks Save
   → JS calls `PUT /api/watchlist` with new list
   → Flask writes updated list to `config.json`
   → JS closes modal, updates status bar

---

## Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.10+ | Native fit for yfinance/pandas-ta; learner's background |
| Desktop window | `pywebview` 4.x | Native OS window, no browser; wraps HTML/CSS/JS frontend |
| Backend server | `Flask` 3.x | Lightweight local HTTP server; simple routing, no async overhead |
| Data fetching | `yfinance` 0.2.x | Free Yahoo Finance OHLCV; supports daily and 1h natively |
| Technical analysis | `ta` 0.11.0 | pandas-ta unavailable on PyPI for Python 3.10+; `ta` covers MACD, Bollinger Bands, and RSI with a clean pandas API |
| Data manipulation | `pandas` 2.x | DataFrame operations for resampling, slicing, signal logic |
| Frontend | Vanilla HTML/CSS/JS | No build step, no framework; full visual control |
| Config persistence | JSON file (`config.json`) | Simple, human-readable, no database needed for a watchlist |

**Documentation links:**
- pywebview: https://pywebview.flowrl.com/
- Flask: https://flask.palletsprojects.com/
- yfinance: https://github.com/ranaroussi/yfinance
- ta: https://github.com/bukosabino/ta
- pandas: https://pandas.pydata.org/docs/

**Tradeoff accepted:** Flask + pywebview run in the same Python process using threading (Flask on a background thread, pywebview on the main thread). This is the standard pattern for pywebview + Flask and is well-documented, but means the app is single-user local only — which is exactly the PoC requirement.

**Verify early in build:**
- `pandas-ta` candlestick pattern function availability and exact API signatures (some patterns may need manual OHLCV implementation as fallback)
- pywebview version compatibility with the host OS (macOS, Windows, Linux each use a different webview engine)
- yfinance 1h data availability: maximum lookback is 730 days; verify data freshness for the most recent candle

---

## Where It Runs and How Someone Tries It

**Runtime:** Local Python process on macOS (or any platform with Python 3.10+).

**Requirements:**
```
python >= 3.10
pip install pywebview flask yfinance pandas-ta pandas
```

**Start command:**
```bash
python main.py
```

A native desktop window opens immediately. No browser, no separate server start step.

**Demo recording:** Run `python main.py`, click "Run Fresh Scan", let the tables populate, show the LONG and SHORT ranked rows with reasoning. The config watchlist edit flow is a secondary demo beat.

**Submission:** Public GitHub repository + short demo video. Local-only; no deployment required or planned.

---

## Look and Feel

Carries forward from `prd.md > Look and Feel` and `scope.md > Inspiration & Identity`.

- **Background:** Dark neutral (`#0f1117` or similar near-black)
- **Surface/card color:** Slightly lighter (`#1a1d27`)
- **LONG accent:** Muted green (`#22c55e` or `#16a34a`)
- **SHORT accent:** Muted red (`#ef4444` or `#dc2626`)
- **Neutral chrome:** Slate grays (`#64748b`, `#94a3b8`)
- **Typography:** System monospace (`'Courier New', monospace`) for ticker symbols and scores; clean system sans-serif (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`) for labels, buttons, and body text
- **Density:** Compact table rows (padding: 8px 12px), no wasted whitespace
- **Buttons:** Flat, high-contrast; loading state uses CSS animation for the spinner — no image assets
- **Tables:** No zebra striping; thin row separators (`1px solid #2d3144`); column headers in uppercase small caps
- **No decorative elements** that don't carry data

---

## Components

### `main.py` — Entry Point
Starts the Flask server on a background thread, then calls `webview.create_window()` to open the native desktop window pointing at `http://localhost:5000`. Blocks on `webview.start()`.
PRD ref: `prd.md > The Core Journey` (step 1)

### Flask App (`app.py`) — HTTP API Server

#### `GET /` — Serve the UI
Returns `ui/index.html`. Flask serves the `ui/` directory as static files.

#### `GET /api/watchlist`
Reads `config.json`, returns `{ "tickers": ["AAPL", "MSFT", ...] }`.
PRD ref: `prd.md > Watchlist Management`

#### `PUT /api/watchlist`
Accepts `{ "tickers": [...] }`, validates (non-empty list, string symbols), writes to `config.json`, returns updated list.
PRD ref: `prd.md > Watchlist Management`

#### `POST /api/scan`
Orchestrates the full scan pipeline. Calls `DataFetcher`, `PatternDetector`, `IndicatorDetector`, `Scorer` in sequence. Returns:
```json
{
  "long":  [{ "ticker": "NVDA", "score": 3, "signals": ["Hammer (1h)", "MACD bullish crossover (daily)"] }],
  "short": [{ "ticker": "TSLA", "score": -2, "signals": ["Upper BB breakout (daily)", "Evening Star (1h)"] }],
  "timestamp": "2026-09-24 09:42:31"
}
```
On error, returns HTTP 500: `{ "error": "Scan failed: <reason>" }`.
PRD ref: `prd.md > Scan Trigger`, `prd.md > Results Display`

### `screener/data_fetcher.py` — Data Fetcher
Fetches OHLCV data for a list of tickers using `yfinance`.
- `fetch_daily(tickers)` → dict of `{ticker: pd.DataFrame}` with columns `[Open, High, Low, Close, Volume]`, 90-day lookback
- `fetch_1h(tickers)` → same shape, 30-day lookback (yfinance 1h limit)
- Raises `DataFetchError` on network failure or empty response
PRD ref: `prd.md > Scan Trigger`

### `screener/pattern_detector.py` — Candlestick Pattern Detector
Detects the 8 patterns defined in the PRD on a single OHLCV DataFrame. Returns a list of fired signal strings.

**Patterns and detection approach:**

| Pattern | Candles | Method |
|---|---|---|
| Hammer | 1 | `pandas-ta` `cdl_pattern(name="hammer")` or manual: small body, long lower wick ≥ 2× body, upper wick < body |
| Shooting Star | 1 | `pandas-ta` `cdl_pattern(name="shootingstar")` or manual: small body, long upper wick ≥ 2× body, lower wick < body |
| Bullish Engulfing | 2 | Manual: candle[−1] bearish, candle[0] bullish, candle[0] body engulfs candle[−1] body |
| Bearish Engulfing | 2 | Manual: candle[−1] bullish, candle[0] bearish, candle[0] body engulfs candle[−1] body |
| Morning Star | 3 | Manual: candle[−2] bearish large body, candle[−1] small body (doji-like), candle[0] bullish large body closing > midpoint of candle[−2] |
| Evening Star | 3 | Manual: candle[−2] bullish large body, candle[−1] small body (doji-like), candle[0] bearish large body closing < midpoint of candle[−2] |
| Bullish Doji | 1 | Doji body ≤ 5% of candle range AND preceding 5 candles show lower lows (downtrend) |
| Bearish Doji | 1 | Doji body ≤ 5% of candle range AND preceding 5 candles show higher highs (uptrend) |

All patterns are detected on the **last complete candle** of the DataFrame (index `−1` for most recent, `−2` as the prior candle, etc.).
PRD ref: `prd.md > Candlestick Patterns in Scope`

### `screener/indicator_detector.py` — Indicator Signal Detector
Detects MACD crossover, Bollinger Band, and RSI signals using `pandas-ta`.

**MACD (12, 26, 9):**
- Compute via `df.ta.macd(fast=12, slow=26, signal=9)`
- **Bullish crossover:** `macd_line[−1] > signal_line[−1]` AND `macd_line[−2] <= signal_line[−2]`
- **Bearish crossover:** `macd_line[−1] < signal_line[−1]` AND `macd_line[−2] >= signal_line[−2]`

**Bollinger Bands (20, 2σ):**
- Compute via `df.ta.bbands(length=20, std=2)`
- **Lower band touch/cross (bullish):** `close[−1] <= lower_band[−1]`
- **Upper band touch/cross (bearish):** `close[−1] >= upper_band[−1]`

**RSI (14):**
- Compute via `df.ta.rsi(length=14)`
- **Oversold — bullish:** `rsi[−1] < 30`
- **Overbought — bearish:** `rsi[−1] > 70`

All three signals evaluated independently on both daily and 1h DataFrames (each timeframe fires its own signal independently).
PRD ref: `prd.md > Indicator Signals in Scope`

### `screener/scorer.py` — Confluence Scorer
Takes the lists of fired signals per ticker per timeframe, sums +1 (bullish) and −1 (bearish) contributions, returns a scored result dict per ticker with all signal strings and the net score.

**Scoring matrix — Long confluence (+1 per active confirmation):**
| Signal | Timeframe(s) |
|---|---|
| Bullish candlestick pattern (Hammer, Morning Star, Bullish Engulfing, Bullish Doji) | Daily or 1h |
| MACD bullish crossover | Daily or 1h |
| Price at or below lower Bollinger Band | Daily or 1h |
| RSI < 30 (oversold / turning back up) | Daily or 1h |

**Scoring matrix — Short confluence (−1 per active confirmation):**
| Signal | Timeframe(s) |
|---|---|
| Bearish candlestick pattern (Shooting Star, Evening Star, Bearish Engulfing, Bearish Doji) | Daily or 1h |
| MACD bearish crossover | Daily or 1h |
| Price at or above upper Bollinger Band | Daily or 1h |
| RSI > 70 (overbought / turning back down) | Daily or 1h |

Each signal on each timeframe is an independent +1 or −1. Maximum possible score per ticker: +8 (all 4 bullish signals on both timeframes); minimum: −8.

**Tie-breaking sort key** (applied in `app.py` before returning results):
1. Descending by `|score|` (magnitude)
2. Descending by 1h volume of the last complete candle
3. Descending by absolute 1h % price change of the last complete candle: `abs((close[−1] − close[−2]) / close[−2])`
4. Alphabetical by ticker symbol

PRD ref: `prd.md > Results Display`, `prd.md > Product Decisions`

### `ui/index.html` — Frontend Dashboard
Single HTML file. Inline `<style>` block for all CSS. Inline `<script>` block for all JavaScript. No external dependencies except a Google Fonts import (optional, falls back to system fonts if offline).

**Structure:**
```
<header>   — title, Run Fresh Scan button, status indicator, settings icon
<main>     — two-column grid: #long-table, #short-table
<footer>   — scoring explanation note
<div#modal> — watchlist editor modal (hidden by default)
<div#error-banner> — error toast (hidden by default)
```

**JS responsibilities:**
- `runScan()` — POST /api/scan, handle loading/success/error states
- `renderTable(tableId, results)` — populate table rows from JSON
- `loadWatchlist()` — GET /api/watchlist, populate status bar and modal
- `saveWatchlist()` — PUT /api/watchlist, update status bar on success
- `showError(msg)` / `hideError()` — error banner lifecycle

PRD ref: `prd.md > Screens and Layout`, `prd.md > Scan Trigger`, `prd.md > Results Display`, `prd.md > Watchlist Management`, `prd.md > Error Handling`

### `config.json` — Watchlist Persistence
```json
{
  "tickers": ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]
}
```
Written and read by Flask. Not committed (add to `.gitignore` with a `config.example.json` alongside it).
PRD ref: `prd.md > Watchlist Management`, `prd.md > States and Boundaries`

---

## Data Model

No database. All state lives in two places:

| Data | Lives in | Persists? | Updated by |
|---|---|---|---|
| Watchlist tickers | `config.json` | Yes — survives restart | `PUT /api/watchlist` |
| Scan results | In-memory (JS DOM) | No — cleared on window close | `POST /api/scan` response |
| Last scan timestamp | In-memory (JS DOM) | No | `POST /api/scan` response |
| OHLCV data | In-memory (Python dicts during scan) | No | Fetched fresh each scan |

**On restart:** watchlist loads from `config.json` via `GET /api/watchlist` on page load. Tables are empty until a scan is run.

PRD ref: `prd.md > States and Boundaries` (persistence rules)

---

## File Structure

```
AdvancedSearchTool/
├── main.py                  # Entry point: starts Flask thread + pywebview window
├── app.py                   # Flask app: API routes (/api/scan, /api/watchlist)
├── config.json              # Watchlist persistence (gitignored)
├── config.example.json      # Example watchlist for repo
├── requirements.txt         # Python dependencies
├── screener/
│   ├── __init__.py
│   ├── data_fetcher.py      # yfinance OHLCV fetching (daily + 1h)
│   ├── pattern_detector.py  # Candlestick pattern detection (8 patterns)
│   ├── indicator_detector.py# MACD + Bollinger Band signal detection
│   └── scorer.py            # Confluence scoring + tie-breaking sort
├── ui/
│   └── index.html           # Single-page frontend (HTML + CSS + JS inline)
├── devpost/                 # Devpost learning workspace
│   ├── learner-profile.md
│   ├── scope.md
│   ├── prd.md
│   └── spec.md
├── .gitignore               # Includes config.json, devpost/learner-profile.md
└── README.md                # Setup and run instructions
```

---

## External Services and Dependencies

### yfinance (Yahoo Finance)
- **Call:** `yf.download(ticker, period="90d", interval="1d")` for daily; `yf.download(ticker, period="30d", interval="1h")` for 1h
- **Response shape:** pandas DataFrame with columns `[Open, High, Low, Close, Volume, Dividends, Stock Splits]`
- **Auth:** None required
- **Rate limits:** Unofficial API; no published hard limit but aggressive polling may trigger temporary blocks. One scan of 5 tickers is well within safe use.
- **Cost:** Free
- **1h data limit:** Maximum lookback ~730 days but freshness degrades; use 30-day window for reliability
- **Docs:** https://github.com/ranaroussi/yfinance

### pandas-ta
- **Usage:** `df.ta.macd(fast=12, slow=26, signal=9)`, `df.ta.bbands(length=20, std=2)`, `df.ta.cdl_pattern(name=...)`
- **Auth:** None
- **Cost:** Free, open source
- **Docs:** https://github.com/twopirllc/pandas-ta
- **⚠️ Verify early:** `cdl_pattern()` coverage — not all TA-Lib patterns are available in pandas-ta. If a pattern is missing, implement manually using raw OHLCV math (see pattern table in Components section above).

---

## Important Failure Modes

- **yfinance network failure or rate limit** → `DataFetchError` raised in `data_fetcher.py`, caught in `/api/scan`, returns HTTP 500 with friendly message. JS shows error banner, retains last table data. PRD ref: `prd.md > Error Handling`

- **Ticker not found / empty DataFrame** → `data_fetcher.py` checks for empty DataFrame after download; skips the ticker and includes a warning in the scan response. UI shows results for valid tickers only; no crash.

- **pandas-ta pattern function unavailable** → Caught at import time or first call; falls back to manual OHLCV implementation. Logged to console. No user-visible error.

- **Empty watchlist** → `/api/scan` detects empty ticker list before fetching, returns HTTP 400 with message "Watchlist is empty — add tickers to get started." JS shows error banner. PRD ref: `prd.md > States and Boundaries`

---

## What Was Simplified and Why

- **No database** — watchlist stored in `config.json` instead of SQLite. A flat JSON file is sufficient for a list of 5–20 ticker strings and survives restarts without any schema or migration overhead.
- **Scan results not persisted** — results live in the JS DOM only. A morning-scan tool has no need for historical result storage at PoC stage; the user runs a fresh scan each session.
- **No async/streaming** — Flask runs synchronously; the scan blocks the API endpoint until complete. For 5 tickers this takes 3–8 seconds, which is acceptable and simpler than async task queues.
- **Single HTML file** — all CSS and JS inline in `index.html`. No bundler, no build step, no node_modules. Keeps the frontend trivially portable and the repo clean.
- **pandas-ta manual fallback** — rather than adding `TA-Lib` (which requires a C library binary install), manual OHLCV math is used as fallback for any patterns pandas-ta doesn't cover. Keeps the install to pure Python packages.

---

## Decisions and Open Issues

**Learner decisions:**
- **Local HTTP API over JS↔Python bridge** — standard fetch() calls, easier to debug independently; tradeoff is Flask running on a background thread alongside pywebview main thread (standard pattern, well-documented).
- **pywebview over browser-based UI** — native desktop window, no external browser dependency; tradeoff is OS-specific webview engine (WebKit on macOS, WebView2 on Windows, GTK WebKit on Linux).
- **Flask over FastAPI** — simpler, synchronous, no async overhead for a local PoC; tradeoff is no built-in async if scan performance becomes a concern later.
- **Vanilla HTML/CSS/JS** — full visual control, no build step; tradeoff is more manual DOM manipulation vs. a reactive framework.
- **pandas-ta manual fallback over TA-Lib** — avoids binary dependency install; tradeoff is reimplementing a small number of patterns manually.

**Genuine uncertainty explored:**
The learner's first time with pywebview. The key question was: how does Python talk to the HTML frontend? Two patterns exist — JS↔Python bridge (direct method calls) vs. local HTTP API (standard fetch). Chosen: local HTTP API, because it maps directly to web-dev intuition (JS calls an endpoint, gets JSON back), is independently testable via curl or a browser, and keeps the backend a normal Flask app. The bridge pattern will be noted in the README for reference. Evidence: decision recorded above and in `prd.md > Product Decisions`.

**Open issues:**
- **pandas-ta `cdl_pattern()` coverage** — verify which of the 8 patterns are available in the installed version before building `pattern_detector.py`. Manual implementations are specced above as fallback; this is not a blocker but determines how much manual code is needed.
- **pywebview threading on macOS** — pywebview requires `webview.start()` on the main thread; Flask must run on a daemon thread. Verify this works cleanly with `threading.Thread(target=app.run, daemon=True)` on the target OS early in the build.
