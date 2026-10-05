"""
Entry point for the Multi-Timeframe Stock Screener.

Starts the Flask server on a background daemon thread, then opens a native
desktop window via pywebview pointing at http://localhost:5174.
pywebview.start() must run on the main thread (macOS requirement).

Port 5174 is used to avoid conflict with macOS AirPlay Receiver on port 5000.
"""

import threading
import time
import webview
from app import app

HOST = "127.0.0.1"
PORT = 5174  # avoid macOS AirPlay (5000) and common dev server ports


def _start_flask() -> None:
    """Run Flask on a background daemon thread."""
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


def main() -> None:
    # Start Flask in the background
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()

    # Give Flask a moment to bind the port before the webview tries to load it
    time.sleep(0.8)

    # Open the native desktop window — must be called on the main thread
    window = webview.create_window(
        title="Multi-Timeframe Stock Screener",
        url=f"http://{HOST}:{PORT}/",
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
    )

    # start() blocks until the window is closed
    webview.start(debug=False)


if __name__ == "__main__":
    main()
