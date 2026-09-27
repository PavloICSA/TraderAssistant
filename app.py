"""
Flask application — local HTTP API server for the Multi-Timeframe Stock Screener.
Serves the static UI and exposes /api/watchlist and /api/scan endpoints.
"""

import json
import os
from flask import Flask, jsonify, request, send_from_directory

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
    Run the full screener pipeline.
    Placeholder for slice 1 — returns empty results.
    Implemented in slice 6.
    """
    return jsonify({
        "long": [],
        "short": [],
        "timestamp": ""
    })


# ---------------------------------------------------------------------------
# Dev entry point (not used when started via main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(port=5000, debug=True)
