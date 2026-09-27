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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


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
    """Return the current watchlist tickers."""
    try:
        config = _read_config()
        return jsonify({"tickers": config.get("tickers", [])})
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

        _write_config({"tickers": tickers})
        return jsonify({"tickers": tickers})
    except Exception as e:
        return jsonify({"error": f"Failed to update watchlist: {str(e)}"}), 500


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
            daily_data  = fetch_daily(tickers)
            hourly_data = fetch_1h(tickers)
        except DataFetchError as e:
            return jsonify({"error": f"Unable to fetch data from Yahoo Finance. {e}"}), 500

        # --- Detect patterns and indicators on both timeframes ---
        pattern_sigs   = {}
        indicator_sigs = {}

        for ticker in tickers:
            pattern_sigs[ticker] = (
                detect_patterns(daily_data.get(ticker),  "daily") +
                detect_patterns(hourly_data.get(ticker), "1h")
            )
            indicator_sigs[ticker] = (
                detect_indicators(daily_data.get(ticker),  "daily") +
                detect_indicators(hourly_data.get(ticker), "1h")
            )

        # --- Score and rank ---
        ranked = score_tickers(pattern_sigs, indicator_sigs, hourly_data)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return jsonify({
            "long":      ranked["long"],
            "short":     ranked["short"],
            "timestamp": timestamp,
        })

    except Exception as e:
        return jsonify({"error": f"Scan failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Dev entry point (not used when started via main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(port=5000, debug=True)
