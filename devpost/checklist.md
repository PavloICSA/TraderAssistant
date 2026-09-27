---
doc: checklist
status: approved
---

# Build Checklist

Build mode: learn

## Slices

- [x] **1. Scaffold + native window opens with static dashboard**
  Becomes usable: Run `python main.py` → a native desktop window opens showing the static HTML dashboard shell (header, two empty tables, footer). No scan logic yet — just proof the pywebview + Flask threading pattern works on this machine.
  Why now: The pywebview + Flask thread combination is the highest-risk unknown in the stack. Proving it works first means every later slice has a confirmed foundation. Bootstrap and scaffold are baked in here, not a separate step.
  PRD ref: `prd.md > The Core Journey` (steps 1–2)
  Spec ref: `spec.md > main.py — Entry Point`, `spec.md > Flask App (app.py)`, `spec.md > File Structure`, `spec.md > Where It Runs and How Someone Tries It`
  Build: Create full project file structure (`main.py`, `app.py`, `screener/__init__.py`, `ui/index.html`, `config.json`, `config.example.json`, `requirements.txt`). Implement Flask serving `ui/index.html` on `GET /`. Implement `main.py` starting Flask on a daemon thread then calling `webview.create_window()` + `webview.start()`. Build the complete static HTML/CSS dashboard shell per the Look and Feel spec: header (title, disabled Run button, status bar, settings icon), two empty tables with correct columns and empty-state message, footer with scoring explanation. No JS scan logic yet.
  Verify (mechanical): `python main.py` starts without errors; native desktop window opens; static dashboard is visible with correct layout, colors, and typography.
  Learner check: Run `python main.py`. Does the window open? Does it look like what you had in mind — dark background, two table sections, the header and footer? Note anything that doesn't match.
  Commit: `Scaffold project and open native dashboard window`

- [x] **2. Watchlist API — load and edit from the UI**
  Becomes usable: The status bar populates with the current watchlist on load. The settings panel opens, shows current tickers, lets you add/remove, and saves — config.json updates and the status bar reflects the change immediately.
  Why now: The watchlist is the input to every scan. Getting it working and persisted before scan logic means scan slices can use the real watchlist from the start. It also exercises the full Flask API + JS fetch round-trip cleanly on a simple endpoint before the heavy scan logic.
  PRD ref: `prd.md > Watchlist Management`, `prd.md > States and Boundaries`
  Spec ref: `spec.md > GET /api/watchlist`, `spec.md > PUT /api/watchlist`, `spec.md > config.json — Watchlist Persistence`, `spec.md > ui/index.html — Frontend Dashboard`
  Build: Implement `GET /api/watchlist` and `PUT /api/watchlist` in `app.py` (read/write `config.json`). In `index.html` JS: `loadWatchlist()` calls `GET /api/watchlist` on page load and populates status bar; modal open/close; add/remove ticker UI; `saveWatchlist()` calls `PUT /api/watchlist` and updates status bar on success.
  Verify (mechanical): Page load populates status bar with default tickers. Open settings modal, add a ticker (e.g., AMZN), save — status bar updates. Inspect `config.json` to confirm the new ticker is written. Remove a ticker, save — `config.json` updates again.
  Learner check: Open the app, click the settings icon, add a ticker, save. Does the status bar update? Open `config.json` in a text editor — is your new ticker there?
  Commit: `Add watchlist API and UI editor with persistence`

- [ ] **3. Data fetcher — real OHLCV from yfinance**
  Becomes usable: A standalone script (or Flask endpoint used for testing) fetches real daily and 1h OHLCV data for the watchlist tickers and prints the shape of each DataFrame. Proves yfinance returns the expected data format before any analysis logic is built on top of it.
  Why now: The entire analysis pipeline depends on yfinance returning the right DataFrame shape. Verifying this in isolation means pattern/indicator logic won't be debugging a data-fetch problem at the same time. This is the second risky external dependency after pywebview.
  PRD ref: `prd.md > Scan Trigger`
  Spec ref: `spec.md > screener/data_fetcher.py — Data Fetcher`, `spec.md > External Services and Dependencies`
  Build: Implement `screener/data_fetcher.py` with `fetch_daily(tickers)` and `fetch_1h(tickers)` using `yfinance`. Raise `DataFetchError` on empty DataFrame or network failure. Add a `__main__` block for manual testing: fetches default watchlist, prints ticker, timeframe, shape, and first/last row for each.
  Verify (mechanical): `python screener/data_fetcher.py` — all 5 default tickers return non-empty DataFrames for both daily and 1h. Columns include Open, High, Low, Close, Volume. No errors.
  Learner check: Run `python screener/data_fetcher.py`. Do you see real price data for AAPL, MSFT, etc.? Note if any ticker fails or returns unexpected data.
  Commit: `Add yfinance data fetcher with daily and 1h OHLCV fetch`

- [ ] **4. Pattern detector — candlestick pattern detection**
  Becomes usable: Given an OHLCV DataFrame, `pattern_detector.py` detects all 8 candlestick patterns and returns a list of fired signal strings with timeframe labels.
  Why now: Pattern detection is the core analytical kernel. Getting it working and verified on real data (from slice 3) before wiring it into the scan pipeline means the scan slice can trust its inputs.
  PRD ref: `prd.md > Candlestick Patterns in Scope`
  Spec ref: `spec.md > screener/pattern_detector.py — Candlestick Pattern Detector`
  Build: Implement `screener/pattern_detector.py` with `detect_patterns(df, timeframe_label)` → list of signal strings. Implement all 8 patterns per the spec table (pandas-ta where available, manual OHLCV math as fallback). Add a `__main__` block: fetches real data for one ticker, runs detection on both timeframes, prints results.
  Verify (mechanical): `python screener/pattern_detector.py` — runs without errors on real data. At least one pattern fires on at least one ticker/timeframe across the watchlist (expected given market activity). Manual review: inspect a fired Hammer signal — confirm the candle's lower wick is ≥ 2× the body.
  Learner check: Run the script. Do any patterns fire? Pick one result and look at the raw candle data — does the signal make sense given what you see in Open/High/Low/Close?
  Commit: `Add candlestick pattern detector (8 patterns, dual timeframe)`

- [ ] **5. Indicator detector — MACD, Bollinger Bands, RSI**
  Becomes usable: Given an OHLCV DataFrame, `indicator_detector.py` detects all 6 indicator signals (MACD crossover bull/bear, BB lower/upper touch, RSI oversold/overbought) and returns fired signal strings with timeframe labels.
  Why now: Completes the analysis layer. Pattern + indicator detectors together are everything the scorer needs; building them separately keeps each verifiable in isolation.
  PRD ref: `prd.md > Indicator Signals in Scope`
  Spec ref: `spec.md > screener/indicator_detector.py — Indicator Signal Detector`
  Build: Implement `screener/indicator_detector.py` with `detect_indicators(df, timeframe_label)` → list of signal strings. Implement MACD(12,26,9) crossover, BB(20,2) lower/upper touch, RSI(14) < 30 / > 70 using `pandas-ta`. Add a `__main__` block: fetches real data for one ticker, runs detection on both timeframes, prints results.
  Verify (mechanical): `python screener/indicator_detector.py` — runs without errors. pandas-ta correctly computes MACD, BB, and RSI columns (inspect column names). At least one indicator signal fires across the watchlist on either timeframe.
  Learner check: Run the script. Do any indicator signals fire? Check the RSI value for a ticker — does the oversold/overbought classification look right given the number?
  Commit: `Add indicator detector (MACD, Bollinger Bands, RSI)`

- [ ] **6. Scorer + full scan pipeline wired to the UI**
  Becomes usable: Click "Run Fresh Scan" → the app fetches real data, detects patterns and indicators on both timeframes, scores each ticker, and populates the LONG and SHORT tables with real results, reasoning, and scores. The full end-to-end product works.
  Why now: This is the unique kernel — the confluence scorer turning multi-signal analysis into a ranked actionable table. Everything before this was preparation; this is the moment the product exists.
  PRD ref: `prd.md > Results Display`, `prd.md > Scan Trigger`, `prd.md > States and Boundaries`
  Spec ref: `spec.md > screener/scorer.py — Confluence Scorer`, `spec.md > POST /api/scan`, `spec.md > ui/index.html — Frontend Dashboard`
  Build: Implement `screener/scorer.py` with full scoring matrix and tie-breaking sort. Implement `POST /api/scan` in `app.py` — orchestrates `DataFetcher` → `PatternDetector` → `IndicatorDetector` → `Scorer`, returns JSON. In `index.html` JS: implement `runScan()` — POST /api/scan, handle loading state (disable button, show spinner), render LONG and SHORT tables from response, update timestamp. Handle score=0 exclusion, signal list rendering, table sort.
  Verify (mechanical): Click "Run Fresh Scan" — button disables, spinner appears, tables populate with real data. LONG table shows only tickers with score > 0, sorted descending. SHORT table shows only tickers with score < 0, sorted by absolute value descending. Each row has Ticker, Score, and at least one signal string. Timestamp updates.
  Learner check: Run a scan. Do the tables look right? Pick a LONG result — do the signals listed (e.g., "Hammer (1h), RSI oversold (daily)") make sense as a reason to go long? Try running a second scan — does the UI refresh cleanly?
  Commit: `Wire full scan pipeline to dashboard UI`

- [ ] **7. Error handling and edge states**
  Becomes usable: The app handles all failure modes gracefully: scan failure shows error banner and retains last results; empty watchlist shows a clear message; first-load empty state is correct; error banner is dismissible.
  Why now: The product isn't shippable until it fails gracefully. Doing this as the last functional slice means the happy path is fully verified first — errors layer on top cleanly.
  PRD ref: `prd.md > Error Handling`, `prd.md > States and Boundaries`
  Spec ref: `spec.md > Important Failure Modes`, `spec.md > POST /api/scan`
  Build: In `app.py`: handle `DataFetchError` and empty watchlist in `/api/scan` — return HTTP 500/400 with friendly message. Handle per-ticker empty DataFrame (skip ticker, log warning). In `index.html` JS: implement `showError(msg)` / `hideError()` — error banner with dismiss button; retain last table data on scan failure; show empty-watchlist message; correct first-load empty state in both tables.
  Verify (mechanical): Temporarily set an invalid ticker (e.g., "INVALID") in `config.json`, run scan — app shows error banner, doesn't crash, retains previous results. Clear watchlist to empty array, run scan — app shows "Watchlist is empty" message. Restore valid watchlist.
  Learner check: Try the invalid ticker test yourself. Does the error banner appear? Do the previous results stay visible? Does the banner dismiss when you click it?
  Commit: `Add error handling, empty states, and scan failure recovery`

---

## Hands-on Checkpoints

- [x] Early feedback after slice 1 — native window opens and dashboard looks right (shapes remaining build decisions about layout/styling)
- [ ] Final kick-the-tires exploration and feedback completed

## Final Review

- [ ] Final review complete — feedback resolved and learner confirms ready to ship

## Code Tour and App Map

- [ ] Learning activity complete — guided route, focused alternative, prior practice connected, or brief recap
- [ ] Optional edit and transfer reflection addressed — offered/declined/already covered/not applicable as appropriate
- [ ] `devpost/app-map.html` generated from finished code, checked, and shown, including a project-grounded practice to reuse

Activity and evidence: [what actually happened; real document/test/code references; unfinished work if interrupted]
Route and stops: [actual paths and symbols; guided stops completed, or reference-only route]
Edit outcome: [tried/kept/reverted/declined/not applicable; verification if changed]
Reflection: [offered/answered/declined/already covered — personal answer belongs only in the ignored profile]
Activity mode: [live app and editor, explicit static fallback, focused alternative, prior practice, or recap]

## Revisions

- `pandas-ta` unavailable on PyPI for Python 3.10+ — replaced with `ta==0.11.0`, which covers MACD, Bollinger Bands, and RSI via a clean pandas API. Candlestick pattern detection uses manual OHLCV math throughout (already the specced fallback). No functional impact.
