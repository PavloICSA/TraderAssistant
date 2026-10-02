"""
Confluence scorer — aggregates pattern and indicator signals into a net score
per ticker, then applies three scoring extensions before ranking.

Base scoring:
  +1 per bullish signal (bullish pattern, MACD bullish crossover,
                         lower BB touch, RSI oversold)
  -1 per bearish signal (bearish pattern, MACD bearish crossover,
                         upper BB touch, RSI overbought)

Extension 1 — MTF Alignment Bonus:
  When the same indicator type fires on BOTH Daily and 1h simultaneously,
  award an additional +1 bonus per aligned pair and append a
  "⚡ Multi-TF Alignment: <type>" badge to the signal list.
  Net effect: aligned pair scores +3 (or -3) instead of +2 (or -2).

Extension 2 — Volume Confirmation:
  Compare 1h volume of the last candle to the 20-period 1h volume SMA.
  > 1.5× average AND ticker has net bullish/bearish signals → +1 bonus
  < 0.5× average AND ticker has net bullish/bearish signals → -1 penalty
  Applied once per ticker; direction follows the existing net score sign.

Extension 3 — 50 SMA Macro Filter:
  Compute 50-period SMA on the daily close.
  LONG setup where close < SMA50 → -1 counter-trend penalty
  SHORT setup where close > SMA50 → -1 counter-trend penalty
  Applied once per ticker as a guardrail, not a disqualifier.

Tickers with score = 0 after all adjustments are excluded from both lists.

Tie-breaking (descending):
  1. Absolute score magnitude
  2. 1h volume (last complete candle)
  3. Absolute 1h % price change (last complete candle)
  4. Alphabetical by ticker symbol

Public API:
  score_tickers(pattern_signals, indicator_signals, hourly_data, daily_data)
      -> {"long": [...], "short": [...]}

  Each result entry:
      {"ticker": str, "score": int, "signals": [str, ...]}
"""

import pandas as pd


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Extension 2 — volume confirmation
VOL_HIGH_MULTIPLIER = 1.5   # > 1.5× 20-period avg  →  +1
VOL_LOW_MULTIPLIER  = 0.5   # < 0.5× 20-period avg  →  -1
VOL_MA_PERIOD       = 20

# Extension 3 — macro trend filter
SMA_PERIOD = 50


# ---------------------------------------------------------------------------
# Signal classification
# ---------------------------------------------------------------------------

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

# Signal type labels used to detect MTF alignment pairs
# Each entry: (keyword_in_signal_string, display_label)
_INDICATOR_TYPES = [
    ("macd bullish",       "MACD bullish crossover"),
    ("macd bearish",       "MACD bearish crossover"),
    ("lower bb",           "Lower BB touch"),
    ("upper bb",           "Upper BB touch"),
    ("rsi oversold",       "RSI oversold"),
    ("rsi overbought",     "RSI overbought"),
    ("hammer",             "Hammer"),
    ("bullish engulfing",  "Bullish Engulfing"),
    ("morning star",       "Morning Star"),
    ("bullish doji",       "Bullish Doji"),
    ("shooting star",      "Shooting Star"),
    ("bearish engulfing",  "Bearish Engulfing"),
    ("evening star",       "Evening Star"),
    ("bearish doji",       "Bearish Doji"),
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
# Extension 1 — MTF Alignment Bonus
# ---------------------------------------------------------------------------

def _mtf_alignment_bonus(signals: list[str]) -> tuple[int, list[str]]:
    """
    Detect signal types that fired on both Daily and 1h.
    Returns (bonus_points, badge_strings).
    bonus_points: +1 per aligned pair (direction already in base score)
    badge_strings: ["⚡ Multi-TF Alignment: RSI oversold", ...]
    """
    bonus  = 0
    badges = []

    for keyword, label in _INDICATOR_TYPES:
        daily_fired = any(keyword in s.lower() and "(daily" in s.lower() for s in signals)
        hourly_fired = any(keyword in s.lower() and "(1h" in s.lower() for s in signals)

        if daily_fired and hourly_fired:
            bonus += 1
            badges.append(f"⚡ Multi-TF Alignment: {label}")

    return bonus, badges


# ---------------------------------------------------------------------------
# Extension 2 — Volume Confirmation
# ---------------------------------------------------------------------------

def _volume_confirmation(df_1h: pd.DataFrame | None, net_sign: int) -> tuple[int, list[str]]:
    """
    Compare last 1h candle volume to 20-period 1h volume SMA.
    Returns (adjustment, [signal_string]).
    net_sign: +1 for bullish ticker, -1 for bearish ticker.
    """
    if df_1h is None or len(df_1h) < VOL_MA_PERIOD + 1:
        return 0, []

    vol_now = float(df_1h["Volume"].iloc[-1])
    vol_avg = float(df_1h["Volume"].iloc[-(VOL_MA_PERIOD + 1):-1].mean())

    if vol_avg == 0:
        return 0, []

    ratio = vol_now / vol_avg

    if ratio > VOL_HIGH_MULTIPLIER:
        # High volume confirms the signal direction
        adj = net_sign  # +1 for longs, -1 for shorts (deepens the move)
        label = f"Volume confirmation ({ratio:.1f}× avg)"
        return adj, [label]
    elif ratio < VOL_LOW_MULTIPLIER:
        # Low volume discounts the signal
        adj = -net_sign  # penalises in the signal's direction
        label = f"Low volume discount ({ratio:.1f}× avg)"
        return adj, [label]

    return 0, []


# ---------------------------------------------------------------------------
# Extension 3 — 50 SMA Macro Filter
# ---------------------------------------------------------------------------

def _sma50_filter(df_daily: pd.DataFrame | None, net_sign: int) -> tuple[int, list[str]]:
    """
    Apply a -1 counter-trend penalty if the ticker is trading against its
    50-period daily SMA.
    Returns (adjustment, [signal_string]).
    net_sign: +1 for bullish ticker, -1 for bearish ticker.
    """
    if df_daily is None or len(df_daily) < SMA_PERIOD:
        return 0, []

    close   = float(df_daily["Close"].iloc[-1])
    sma50   = float(df_daily["Close"].rolling(SMA_PERIOD).mean().iloc[-1])

    if pd.isna(sma50):
        return 0, []

    # LONG signal below SMA50 = counter-trend bounce (risky)
    if net_sign > 0 and close < sma50:
        pct_below = (sma50 - close) / sma50 * 100
        return -1, [f"Counter-trend: below 50 SMA ({pct_below:.1f}% below)"]

    # SHORT signal above SMA50 = counter-trend fade (risky)
    if net_sign < 0 and close > sma50:
        pct_above = (close - sma50) / sma50 * 100
        return -1, [f"Counter-trend: above 50 SMA ({pct_above:.1f}% above)"]

    return 0, []


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
    daily_data:        dict[str, pd.DataFrame] | None = None,
) -> dict[str, list[dict]]:
    """
    Aggregate signals into scored, sorted LONG and SHORT lists,
    including MTF alignment bonus, volume confirmation, and SMA50 filter.

    Args:
        pattern_signals:   {ticker: [signal_str, ...]} from pattern_detector
        indicator_signals: {ticker: [signal_str, ...]} from indicator_detector
        hourly_data:       {ticker: DataFrame}         from data_fetcher.fetch_1h
        daily_data:        {ticker: DataFrame}         from data_fetcher.fetch_daily
                           (optional; SMA50 filter disabled if not provided)

    Returns:
        {
            "long":  [{"ticker": str, "score": int, "signals": [str]}, ...],
            "short": [{"ticker": str, "score": int, "signals": [str]}, ...],
        }
    """
    all_tickers = set(pattern_signals) | set(indicator_signals)
    results = []

    for ticker in all_tickers:
        signals = (
            pattern_signals.get(ticker, []) +
            indicator_signals.get(ticker, [])
        )

        # --- Base score ---
        base_score = sum(_classify(s) for s in signals)
        if base_score == 0:
            continue  # no base signal — extensions don't apply

        net_sign = 1 if base_score > 0 else -1

        # --- Extension 1: MTF Alignment Bonus ---
        mtf_bonus, mtf_badges = _mtf_alignment_bonus(signals)
        # Bonus always deepens in the direction of base score
        mtf_adj = mtf_bonus * net_sign

        # --- Extension 2: Volume Confirmation ---
        vol_adj, vol_signals = _volume_confirmation(
            hourly_data.get(ticker), net_sign
        )

        # --- Extension 3: SMA50 Macro Filter ---
        sma_adj, sma_signals = _sma50_filter(
            (daily_data or {}).get(ticker), net_sign
        )

        # --- Final score ---
        final_score = base_score + mtf_adj + vol_adj + sma_adj

        # Combine all signals: base + badges + vol + sma
        all_signals = signals + mtf_badges + vol_signals + sma_signals

        # Re-check: if all adjustments cancelled the base score, exclude
        if final_score == 0:
            continue

        results.append({
            "ticker":  ticker,
            "score":   final_score,
            "signals": all_signals,
            "_vol":    _1h_volume(hourly_data.get(ticker)),
            "_pct":    _1h_abs_pct_change(hourly_data.get(ticker)),
        })

    # Sort: descending absolute score → descending volume →
    #       descending % change → ascending ticker (alphabetical)
    results.sort(key=lambda r: (-abs(r["score"]), -r["_vol"], -r["_pct"], r["ticker"]))

    long_list  = [
        {"ticker": r["ticker"], "score": r["score"], "signals": r["signals"]}
        for r in results if r["score"] > 0
    ]
    short_list = [
        {"ticker": r["ticker"], "score": r["score"], "signals": r["signals"]}
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

    from screener.data_fetcher       import fetch_daily, fetch_1h
    from screener.pattern_detector   import detect_patterns
    from screener.indicator_detector import detect_indicators

    config_path = os.path.join(base, "..", "config.json")
    with open(config_path, encoding="utf-8") as f:
        tickers = json.load(f)["tickers"]

    print(f"Running extended scoring pipeline for: {tickers}\n")

    daily_data,  _ = fetch_daily(tickers)
    hourly_data, _ = fetch_1h(tickers)

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

    ranked = score_tickers(
        pattern_sigs, indicator_sigs,
        hourly_data, daily_data
    )

    print("=== LONG opportunities (ranked) ===")
    if ranked["long"]:
        for r in ranked["long"]:
            print(f"  {r['ticker']:6}  score=+{r['score']}")
            for s in r["signals"]:
                prefix = "    ⚡" if "Multi-TF" in s else "     "
                prefix = "    📊" if "Volume" in s else prefix
                prefix = "    ⚠" if "Counter-trend" in s else prefix
                print(f"{prefix} {s}")
    else:
        print("  No bullish setups detected.")

    print()
    print("=== SHORT opportunities (ranked) ===")
    if ranked["short"]:
        for r in ranked["short"]:
            print(f"  {r['ticker']:6}  score={r['score']}")
            for s in r["signals"]:
                prefix = "    ⚡" if "Multi-TF" in s else "     "
                prefix = "    📊" if "Volume" in s else prefix
                prefix = "    ⚠" if "Counter-trend" in s else prefix
                print(f"{prefix} {s}")
    else:
        print("  No bearish setups detected.")
