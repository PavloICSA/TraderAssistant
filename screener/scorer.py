"""
Confluence scorer — aggregates pattern and indicator signals into a net score
per ticker, then sorts results into LONG and SHORT ranked lists.

Scoring:
  +1 per bullish signal (bullish pattern, MACD bullish crossover,
                         lower BB touch, RSI oversold)
  -1 per bearish signal (bearish pattern, MACD bearish crossover,
                         upper BB touch, RSI overbought)

Tickers with score = 0 are excluded from both lists.

Tie-breaking (descending):
  1. Absolute score magnitude
  2. 1h volume (last complete candle)
  3. Absolute 1h % price change (last complete candle)
  4. Alphabetical by ticker symbol

Public API:
  score_tickers(pattern_signals, indicator_signals, hourly_data)
      -> {"long": [...], "short": [...]}

  Each result entry:
      {"ticker": str, "score": int, "signals": [str, ...]}
"""

import pandas as pd


# ---------------------------------------------------------------------------
# Signal classification
# ---------------------------------------------------------------------------

# These substrings identify a signal as bullish (+1) or bearish (-1).
_BULLISH_KEYWORDS = [
    "hammer",
    "bullish engulfing",
    "morning star",
    "bullish doji",
    "macd bullish",
    "lower bb",
    "rsi oversold",
]

_BEARISH_KEYWORDS = [
    "shooting star",
    "bearish engulfing",
    "evening star",
    "bearish doji",
    "macd bearish",
    "upper bb",
    "rsi overbought",
]


def _classify(signal: str) -> int:
    """Return +1, -1, or 0 for a signal string."""
    s = signal.lower()
    if any(kw in s for kw in _BULLISH_KEYWORDS):
        return +1
    if any(kw in s for kw in _BEARISH_KEYWORDS):
        return -1
    return 0


# ---------------------------------------------------------------------------
# Tie-breaking helpers
# ---------------------------------------------------------------------------

def _1h_volume(df_1h: pd.DataFrame | None) -> float:
    if df_1h is None or df_1h.empty:
        return 0.0
    return float(df_1h["Volume"].iloc[-1])


def _1h_abs_pct_change(df_1h: pd.DataFrame | None) -> float:
    if df_1h is None or len(df_1h) < 2:
        return 0.0
    c_now  = float(df_1h["Close"].iloc[-1])
    c_prev = float(df_1h["Close"].iloc[-2])
    if c_prev == 0:
        return 0.0
    return abs((c_now - c_prev) / c_prev)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_tickers(
    pattern_signals:   dict[str, list[str]],
    indicator_signals: dict[str, list[str]],
    hourly_data:       dict[str, pd.DataFrame],
) -> dict[str, list[dict]]:
    """
    Aggregate signals into scored, sorted LONG and SHORT lists.

    Args:
        pattern_signals:   {ticker: [signal_str, ...]} from pattern_detector
        indicator_signals: {ticker: [signal_str, ...]} from indicator_detector
        hourly_data:       {ticker: DataFrame}         from data_fetcher.fetch_1h

    Returns:
        {
            "long":  [{"ticker": str, "score": int, "signals": [str]}, ...],
            "short": [{"ticker": str, "score": int, "signals": [str]}, ...],
        }
        Both lists are sorted descending by absolute score magnitude,
        then by the tie-breaker order defined in the spec.
    """
    all_tickers = set(pattern_signals) | set(indicator_signals)
    results = []

    for ticker in all_tickers:
        signals = (
            pattern_signals.get(ticker, []) +
            indicator_signals.get(ticker, [])
        )
        score = sum(_classify(s) for s in signals)

        if score == 0:
            continue  # exclude neutral tickers per PRD

        results.append({
            "ticker":  ticker,
            "score":   score,
            "signals": signals,
            # tie-breaker keys (not included in API response)
            "_vol":    _1h_volume(hourly_data.get(ticker)),
            "_pct":    _1h_abs_pct_change(hourly_data.get(ticker)),
        })

    # Sort: descending absolute score → descending volume → descending % change
    # → ascending ticker (alphabetical)
    results.sort(key=lambda r: (-abs(r["score"]), -r["_vol"], -r["_pct"], r["ticker"]))

    # Split into LONG and SHORT, strip tie-breaker keys from output
    long_list  = [
        {"ticker": r["ticker"], "score": r["score"],  "signals": r["signals"]}
        for r in results if r["score"] > 0
    ]
    short_list = [
        {"ticker": r["ticker"], "score": r["score"],  "signals": r["signals"]}
        for r in results if r["score"] < 0
    ]

    return {"long": long_list, "short": short_list}


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, os, sys

    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(base, ".."))

    from screener.data_fetcher    import fetch_daily, fetch_1h
    from screener.pattern_detector   import detect_patterns
    from screener.indicator_detector import detect_indicators

    config_path = os.path.join(base, "..", "config.json")
    with open(config_path, encoding="utf-8") as f:
        tickers = json.load(f)["tickers"]

    print(f"Running full scoring pipeline for: {tickers}\n")

    daily_data  = fetch_daily(tickers)
    hourly_data = fetch_1h(tickers)

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

    ranked = score_tickers(pattern_sigs, indicator_sigs, hourly_data)

    print("=== LONG opportunities (ranked) ===")
    if ranked["long"]:
        for r in ranked["long"]:
            print(f"  {r['ticker']:6}  score=+{r['score']}  signals: {', '.join(r['signals'])}")
    else:
        print("  No bullish setups detected.")

    print()
    print("=== SHORT opportunities (ranked) ===")
    if ranked["short"]:
        for r in ranked["short"]:
            print(f"  {r['ticker']:6}  score={r['score']}  signals: {', '.join(r['signals'])}")
    else:
        print("  No bearish setups detected.")
