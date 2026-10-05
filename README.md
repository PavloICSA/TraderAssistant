# TraderAssistant — Multi-Timeframe Stock Screener

A Python desktop application that automatically scans a watchlist of stocks, crypto, forex, and commodities for high-probability trading setups. It combines candlestick pattern recognition with technical indicator signals across two timeframes — **Daily** (trend context) and **1-hour** (entry trigger) — scores each ticker by confluence, and presents ranked **LONG** and **SHORT** opportunities in a native desktop window.

No browser required. Run one command and the dashboard opens.

---

## Features

- **8 candlestick patterns** — Hammer, Shooting Star, Bullish/Bearish Engulfing, Morning Star, Evening Star, Bullish/Bearish Doji (context-aware)
- **3 technical indicators** — MACD (12, 26, 9), Bollinger Bands (20-period, 2σ), RSI (14-period)
- **Multi-timeframe confluence scoring** — each signal evaluated independently on Daily and 1h; aligned signals on both timeframes earn a bonus point
- **Volume confirmation** — high-volume signals (+1) and low-volume discounts (−1)
- **50 SMA macro filter** — counter-trend setups penalised (−1) to avoid catching falling knives
- **Clickable candlestick charts** — click any result row to inspect the chart, toggle Daily/1h
- **Universal symbol support** — stocks, ETFs, indices (^VIX), crypto (SOL, BTC-USD), forex (EURUSD, EUR/USD), futures (GC, CL), commodity ETFs
- **Watchlist editor** — add/remove tickers from the UI, no code editing required (up to 200 tickers)
- **Concurrent data fetching** — up to 10 parallel yfinance requests for fast scans on large watchlists
- **Graceful error handling** — failed tickers shown in a warning strip, valid tickers always scanned

---

## Requirements

- Python 3.10+
- macOS, Windows, or Linux (pywebview uses the OS native webview engine)
- Internet connection (for Yahoo Finance data)

---

## Installation

```bash
# Clone the repository
git clone https://github.com/PavloICSA/TraderAssistant.git
cd TraderAssistant

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Copy the example watchlist config
cp config.example.json config.json
```

---

## Usage

```bash
python main.py
```

A native desktop window opens immediately. Click **Run Fresh Scan** to fetch live data and populate the LONG and SHORT tables.

> **macOS note:** Port 5000 is reserved by macOS AirPlay Receiver. This app uses port **5174** to avoid that conflict.

---

## Watchlist

The default watchlist is defined in `config.json` (gitignored — use `config.example.json` as a template):

```json
{
  "tickers": ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]
}
```

You can edit the watchlist directly in the app via the **⚙ Watchlist** button. Supported formats:

| Asset class | Examples |
|---|---|
| US Stocks / ETFs | `AAPL`, `SPY`, `QQQ` |
| Market Indices | `^VIX`, `^GSPC`, `^DJI` |
| Crypto | `BTC`, `SOL`, `ETH`, `ADA`, `BTC-USD` |
| Forex | `EURUSD`, `EUR/USD`, `USDJPY` |
| Metals futures | `GC` (Gold), `SI` (Silver), `HG` (Copper) |
| Energy futures | `CL` (Crude Oil), `NG` (Natural Gas) |
| Grain futures | `ZW` (Wheat), `ZC` (Corn) |

---

## Scoring

Each confirmed signal contributes **+1** (bullish) or **−1** (bearish). Both Daily and 1h timeframes are evaluated independently.

| Signal | Bullish | Bearish |
|---|---|---|
| Candlestick pattern | +1 | −1 |
| MACD crossover | +1 | −1 |
| Bollinger Band touch | +1 (lower) | −1 (upper) |
| RSI threshold | +1 (< 30) | −1 (> 70) |
| Multi-TF alignment bonus | +1 per pair | −1 per pair |
| Volume confirmation | +1 (> 1.5× avg) | −1 (< 0.5× avg) |
| 50 SMA counter-trend | −1 penalty | −1 penalty |

Tickers with a net score of 0 are excluded from both tables.

---

## Stack

| Component | Library |
|---|---|
| Desktop window | `pywebview` 6.2.1 |
| Backend API | `Flask` 3.1.3 |
| Market data | `yfinance` 1.7.0 |
| Technical indicators | `ta` 0.11.0 |
| Data processing | `pandas` 2.3.3 |
| Candlestick charts | `lightweight-charts` 4.2.0 (bundled) |
| Frontend | Vanilla HTML / CSS / JS |

---

## Project Structure

```
TraderAssistant/
├── main.py                   # Entry point: Flask thread + pywebview window
├── app.py                    # Flask HTTP API
├── config.example.json       # Default watchlist template
├── requirements.txt
├── screener/
│   ├── data_fetcher.py       # yfinance OHLCV fetching (daily + 1h)
│   ├── pattern_detector.py   # 8 candlestick patterns
│   ├── indicator_detector.py # MACD, Bollinger Bands, RSI
│   └── scorer.py             # Confluence scoring + ranking
├── ui/
│   ├── index.html            # Single-page dashboard
│   └── vendor/
│       └── lightweight-charts.js
└── devpost/                  # Planning docs (scope, PRD, spec, checklist)
```

---

## Disclaimer

This tool is for **personal research only**. It does not provide financial advice, execute trades, or guarantee any investment outcome. All signals are mechanical detections based on historical price data. Use at your own discretion.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
