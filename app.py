"""
Flask application — local HTTP API server for the Multi-Timeframe Stock Screener.
Serves the static UI and exposes /api/watchlist and /api/scan endpoints.
"""

import json
import os
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

from screener.data_fetcher       import fetch_daily, fetch_1h, DataFetchError
from screener.pattern_detector   import detect_patterns
from screener.indicator_detector import detect_indicators
from screener.scorer             import score_tickers

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder="ui", static_url_path="")

import logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Maximum number of tickers allowed in the watchlist
MAX_WATCHLIST = 200


# ---------------------------------------------------------------------------
# Helper: config I/O
# ---------------------------------------------------------------------------

def _read_config() -> dict:
    """Read config.json and return its contents as a dict."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_config(data: dict) -> None:
    """Write a dict to config.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the single-page dashboard UI."""
    return send_from_directory("ui", "index.html")


@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    """Return the current watchlist tickers and the maximum allowed count."""
    try:
        config = _read_config()
        return jsonify({
            "tickers": config.get("tickers", []),
            "max": MAX_WATCHLIST,
        })
    except Exception as e:
        return jsonify({"error": f"Failed to read watchlist: {str(e)}"}), 500


@app.route("/api/watchlist", methods=["PUT"])
def put_watchlist():
    """Update the watchlist tickers."""
    try:
        data = request.get_json(force=True)
        tickers = data.get("tickers", [])

        # Basic validation: must be a non-empty list of strings
        if not isinstance(tickers, list):
            return jsonify({"error": "tickers must be a list"}), 400
        tickers = [str(t).strip().upper() for t in tickers if str(t).strip()]
        if not tickers:
            return jsonify({"error": "Watchlist must contain at least one ticker"}), 400
        if len(tickers) > MAX_WATCHLIST:
            return jsonify({"error": f"Watchlist exceeds the maximum of {MAX_WATCHLIST} tickers. Please remove some before saving."}), 400

        _write_config({"tickers": tickers})
        return jsonify({"tickers": tickers})
    except Exception as e:
        return jsonify({"error": f"Failed to update watchlist: {str(e)}"}), 500


@app.route("/api/debug/fetch/<ticker>", methods=["GET"])
def debug_fetch(ticker):
    """Debug endpoint: test raw yfinance fetch for a ticker. Remove before shipping."""
    import traceback
    ticker = ticker.upper()
    results = {}
    try:
        data, failed = fetch_daily([ticker])
        results["daily_rows"] = len(data.get(ticker, [])) if ticker in data else 0
        results["daily_failed"] = failed.get(ticker, None)
    except Exception as e:
        results["daily_error"] = str(e)
        results["daily_tb"] = traceback.format_exc()
    try:
        data2, failed2 = fetch_1h([ticker])
        results["1h_rows"] = len(data2.get(ticker, [])) if ticker in data2 else 0
        results["1h_failed"] = failed2.get(ticker, None)
    except Exception as e:
        results["1h_error"] = str(e)
    return jsonify(results)


@app.route("/api/chart/<ticker>/<timeframe>", methods=["GET"])
def get_chart(ticker, timeframe):
    """
    Return OHLCV data for a ticker and timeframe as JSON for candlestick rendering.

    Timeframe: "daily" or "1h"
    Response: { "ticker": str, "timeframe": str, "candles": [{time, open, high, low, close, volume}] }
    """
    try:
        ticker = ticker.upper()
        if timeframe not in ("daily", "1h"):
            return jsonify({"error": "Invalid timeframe. Use 'daily' or '1h'."}), 400

        # Try up to 3 times — yfinance can transiently fail under thread contention
        data = {}
        last_error = None
        for attempt in range(3):
            try:
                if timeframe == "daily":
                    data, failed = fetch_daily([ticker])
                else:
                    data, failed = fetch_1h([ticker])

                if ticker in data:
                    break  # success

                # Fetch returned but ticker missing — check failed dict for reason
                last_error = failed.get(ticker, f"No data returned for {ticker}.")
                app.logger.warning(f"Chart attempt {attempt+1} failed for {ticker}/{timeframe}: {last_error}")

            except DataFetchError as e:
                last_error = str(e)
                app.logger.warning(f"Chart attempt {attempt+1} DataFetchError for {ticker}/{timeframe}: {e}")

            if attempt < 2:
                import time
                time.sleep(0.5)  # brief pause before retry

        if ticker not in data:
            app.logger.error(f"Chart fetch exhausted retries for {ticker}/{timeframe}: {last_error}")
            return jsonify({"error": f"Unable to load chart data for {ticker}. {last_error or ''}".strip()}), 404

        df = data[ticker]

        candles = []
        for ts, row in df.iterrows():
            # lightweight-charts expects UNIX timestamp (seconds) for time
            if hasattr(ts, 'timestamp'):
                t = int(ts.timestamp())
            else:
                t = int(ts.value // 1_000_000_000)
            candles.append({
                "time":   t,
                "open":   round(float(row["Open"]),  4),
                "high":   round(float(row["High"]),  4),
                "low":    round(float(row["Low"]),   4),
                "close":  round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            })

        return jsonify({
            "ticker":    ticker,
            "timeframe": timeframe,
            "candles":   candles,
        })

    except Exception as e:
        app.logger.error(f"Chart endpoint error for {ticker}/{timeframe}: {e}")
        return jsonify({"error": f"Chart error: {e}"}), 500


@app.route("/api/scan", methods=["POST"])
def post_scan():
    """
    Run the full screener pipeline:
      1. Read watchlist from config.json
      2. Fetch daily + 1h OHLCV via yfinance
      3. Detect candlestick patterns on both timeframes
      4. Detect indicator signals on both timeframes
      5. Score and rank tickers
      6. Return JSON with long/short lists and timestamp

    Implements: prd.md > Scan Trigger, prd.md > Results Display
    Spec ref:   spec.md > POST /api/scan, spec.md > screener/scorer.py
    """
    try:
        config  = _read_config()
        tickers = config.get("tickers", [])

        if not tickers:
            return jsonify({"error": "Watchlist is empty — add tickers to get started."}), 400

        # --- Fetch data ---
        try:
            daily_data,  daily_failed  = fetch_daily(tickers)
            hourly_data, hourly_failed = fetch_1h(tickers)
        except DataFetchError as e:
            return jsonify({"error": f"Unable to fetch data from Yahoo Finance. {e}"}), 500

        # Collect tickers that failed on either timeframe, deduplicated
        fetch_warnings: dict[str, str] = {}
        for ticker, reason in {**daily_failed, **hourly_failed}.items():
            # Produce a concise, user-friendly reason
            if "invalid" in reason.lower() or "no data" in reason.lower():
                msg = "No data found — ticker may be invalid or delisted."
            elif "unavailable" in reason.lower() or "yahoo" in reason.lower():
                msg = "Yahoo Finance returned no data. Check your connection or try again."
            else:
                msg = "Data unavailable — skipped."
            fetch_warnings[ticker] = msg

        # Only analyse tickers that succeeded on both timeframes
        analysable = [t for t in tickers if t in daily_data and t in hourly_data]

        # --- Detect patterns and indicators on both timeframes ---
        pattern_sigs   = {}
        indicator_sigs = {}

        for ticker in analysable:
            pattern_sigs[ticker] = (
                detect_patterns(daily_data.get(ticker),  "daily") +
                detect_patterns(hourly_data.get(ticker), "1h")
            )
            indicator_sigs[ticker] = (
                detect_indicators(daily_data.get(ticker),  "daily") +
                detect_indicators(hourly_data.get(ticker), "1h")
            )

        # --- Score and rank ---
        ranked = score_tickers(pattern_sigs, indicator_sigs, hourly_data, daily_data)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Build warnings list for the UI: [{ticker, reason}]
        warnings = [
            {"ticker": t, "reason": r}
            for t, r in sorted(fetch_warnings.items())
        ]

        return jsonify({
            "long":      ranked["long"],
            "short":     ranked["short"],
            "timestamp": timestamp,
            "warnings":  warnings,
        })

    except Exception as e:
        return jsonify({"error": f"Scan failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Dev entry point (not used when started via main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(port=5000, debug=True)
