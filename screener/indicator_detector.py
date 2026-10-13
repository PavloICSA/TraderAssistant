"""
Indicator signal detector — detects MACD, Bollinger Band, RSI, and OLS
trend-reversal signals on an OHLCV DataFrame using the `ta` library.

Bullish signals (contribute +1 to LONG score):
  - MACD bullish crossover  (MACD line crosses above signal line from below)
  - Lower BB mean-reversion (body closed below lower band, next 1-2 candles close back inside)
  - RSI oversold  (RSI < 30)
  - OLS trend reversal UP   (daily downtrend R²≥0.5, price crosses back above regression line)

Bearish signals (contribute -1 to SHORT score):
  - MACD bearish crossover  (MACD line crosses below signal line from above)
  - Upper BB mean-reversion (body closed above upper band, next 1-2 candles close back inside)
  - RSI overbought  (RSI > 70)
  - OLS trend reversal DOWN (daily uptrend R²≥0.5, price crosses back below regression line)

All signals are evaluated on the last complete candle (index -1), using
candle -2 as the prior candle for crossover detection.

Public API:
  detect_indicators(df, timeframe_label) -> list[str]
    Returns a list of fired signal strings, e.g.
    ["MACD bullish crossover (1h)", "OLS trend reversal DOWN (daily)"]
"""

import numpy as np
import pandas as pd
import ta
from screener.pattern_detector import _candle_label


# ---------------------------------------------------------------------------
# Parameters (match PRD / spec)
# ---------------------------------------------------------------------------

MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

BB_PERIOD = 20
BB_STD    = 2.0

RSI_PERIOD    = 14
RSI_OVERSOLD  = 30
RSI_OVERBOUGHT = 70

# Minimum rows needed: MACD slow period + signal period as a safe buffer
MIN_ROWS = MACD_SLOW + MACD_SIGNAL + 5

# OLS trend-reversal parameters
OLS_LOOKBACK  = 20     # number of daily candles for regression window
OLS_MIN_R2    = 0.5    # minimum R² to consider the trend reliable enough to act on


# ---------------------------------------------------------------------------
# Individual signal detectors
# ---------------------------------------------------------------------------

def _macd_signals(df: pd.DataFrame, label: str) -> list[str]:
    """
    Detect MACD bullish and bearish crossovers on the last two candles.
    Crossover: line crosses over/under signal between candle[-2] and candle[-1].
    """
    if len(df) < MIN_ROWS:
        return []

    try:
        macd_obj  = ta.trend.MACD(
            close=df["Close"],
            window_slow=MACD_SLOW,
            window_fast=MACD_FAST,
            window_sign=MACD_SIGNAL,
        )
        macd_line = macd_obj.macd()
        sig_line  = macd_obj.macd_signal()
    except Exception:
        return []

    if macd_line.isna().iloc[-1] or macd_line.isna().iloc[-2]:
        return []
    if sig_line.isna().iloc[-1] or sig_line.isna().iloc[-2]:
        return []

    m1, s1 = macd_line.iloc[-1], sig_line.iloc[-1]   # current
    m2, s2 = macd_line.iloc[-2], sig_line.iloc[-2]   # prior

    signals = []
    if m2 <= s2 and m1 > s1:
        signals.append(f"MACD bullish crossover ({label})")
    if m2 >= s2 and m1 < s1:
        signals.append(f"MACD bearish crossover ({label})")
    return signals


def _bb_signals(df: pd.DataFrame, label: str) -> list[str]:
    """
    Detect Bollinger Band mean-reversion signals.

    Rule (2-candle confirmation window):
      LONG  — a candle body closed BELOW the lower band in the last 2 candles
              (the breach), AND the most recent candle closed back ABOVE the
              lower band (confirmation that the market rejected the move down).

      SHORT — a candle body closed ABOVE the upper band in the last 2 candles
              (the breach), AND the most recent candle closed back BELOW the
              upper band (confirmation that the market rejected the move up).

    This filters out continued breakouts and only signals when price has
    returned inside the bands, confirming a genuine mean-reversion setup.
    """
    # Need enough rows for BB calculation (BB_PERIOD) plus the 3-candle
    # inspection window — positions [-1], [-2], [-3] are within the series.
    if len(df) < BB_PERIOD + 2:
        return []

    try:
        bb = ta.volatility.BollingerBands(
            close=df["Close"],
            window=BB_PERIOD,
            window_dev=BB_STD,
        )
        upper = bb.bollinger_hband()
        lower = bb.bollinger_lband()
    except Exception:
        return []

    # Need all values in our window to be non-NaN
    if any(upper.iloc[i] != upper.iloc[i] or lower.iloc[i] != lower.iloc[i]
           for i in [-1, -2, -3]):
        return []

    # Candle positions:
    #   [-1] = most recent complete candle  → confirmation candle
    #   [-2] = one candle back              \  breach window
    #   [-3] = two candles back             /  (2-candle window)

    close_now   = float(df["Close"].iloc[-1])
    upper_now   = float(upper.iloc[-1])
    lower_now   = float(lower.iloc[-1])

    # Check if a breach occurred in the 2-candle window before the current candle
    breach_below = any(
        float(df["Close"].iloc[i]) < float(lower.iloc[i])
        for i in [-2, -3]
    )
    breach_above = any(
        float(df["Close"].iloc[i]) > float(upper.iloc[i])
        for i in [-2, -3]
    )

    signals = []

    # LONG: breach below lower band → confirmed by close back inside (above lower)
    if breach_below and close_now > lower_now:
        signals.append(f"Lower BB mean-reversion ({label})")

    # SHORT: breach above upper band → confirmed by close back inside (below upper)
    if breach_above and close_now < upper_now:
        signals.append(f"Upper BB mean-reversion ({label})")

    return signals


def _rsi_signals(df: pd.DataFrame, label: str) -> list[str]:
    """
    Detect RSI oversold (< 30, bullish) and overbought (> 70, bearish)
    on the last candle.
    """
    if len(df) < RSI_PERIOD + 2:
        return []

    try:
        rsi_series = ta.momentum.RSIIndicator(
            close=df["Close"],
            window=RSI_PERIOD,
        ).rsi()
    except Exception:
        return []

    if rsi_series.isna().iloc[-1]:
        return []

    rsi_val = rsi_series.iloc[-1]
    signals = []

    if rsi_val < RSI_OVERSOLD:
        signals.append(f"RSI oversold <{RSI_OVERSOLD} ({label})  [RSI={rsi_val:.1f}]")
    if rsi_val > RSI_OVERBOUGHT:
        signals.append(f"RSI overbought >{RSI_OVERBOUGHT} ({label})  [RSI={rsi_val:.1f}]")
    return signals


def _ols_trend_reversal(df: pd.DataFrame, label: str) -> list[str]:
    """
    Detect OLS linear regression trend reversals (daily timeframe only).

    Algorithm:
      1. Fit OLS regression through the last OLS_LOOKBACK closes.
      2. Compute R² — if below OLS_MIN_R2 the trend is too choppy to act on.
      3. Determine trend direction from the slope (positive = uptrend, negative = downtrend).
      4. Compute the regression line value at each candle position.
      5. A VIOLATION occurs when:
           - Uptrend:   price was ABOVE regression line on candle[-2]
                        AND closes BELOW it on candle[-1]  → bearish reversal signal
           - Downtrend: price was BELOW regression line on candle[-2]
                        AND closes ABOVE it on candle[-1]  → bullish reversal signal

    Only fires on daily timeframe (caller must pass label containing 'daily').
    """
    # Only applies to daily timeframe
    if "daily" not in label.lower():
        return []

    if df is None or len(df) < OLS_LOOKBACK + 1:
        return []

    # Extract the lookback window (include one extra candle for the prior position)
    window = df["Close"].iloc[-(OLS_LOOKBACK + 1):].values.astype(float)
    n = len(window)   # = OLS_LOOKBACK + 1

    # --- OLS fit ---
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    y_mean = window.mean()

    ss_xy = np.sum((x - x_mean) * (window - y_mean))
    ss_xx = np.sum((x - x_mean) ** 2)

    if ss_xx == 0:
        return []   # all prices identical — no trend

    slope     = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    # --- R² ---
    y_pred  = slope * x + intercept
    ss_res  = np.sum((window - y_pred) ** 2)
    ss_tot  = np.sum((window - y_mean) ** 2)

    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    if r2 < OLS_MIN_R2:
        return []   # trend too noisy — skip

    # Regression line values at the last two positions
    reg_prev = y_pred[-2]   # regression value at candle[-2]
    reg_now  = y_pred[-1]   # regression value at candle[-1] (most recent)

    close_prev = float(window[-2])
    close_now  = float(window[-1])

    slope_pct = slope / y_mean * 100   # slope as % of mean price — for display

    signals = []

    # Uptrend violation → bearish reversal signal
    if slope > 0 and close_prev > reg_prev and close_now < reg_now:
        signals.append(
            f"OLS trend reversal DOWN ({label})  "
            f"[slope={slope_pct:+.2f}%/bar, R²={r2:.2f}]"
        )

    # Downtrend violation → bullish reversal signal
    if slope < 0 and close_prev < reg_prev and close_now > reg_now:
        signals.append(
            f"OLS trend reversal UP ({label})  "
            f"[slope={slope_pct:+.2f}%/bar, R²={r2:.2f}]"
        )

    return signals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_indicators(df: pd.DataFrame, timeframe_label: str) -> list[str]:
    """
    Detect all indicator signals on the last complete candle of df.

    Args:
        df:               OHLCV DataFrame (columns: Open, High, Low, Close, Volume)
        timeframe_label:  e.g. "daily" or "1h" — appended to signal strings

    Returns:
        List of fired signal strings.
    """
    if df is None or len(df) < MIN_ROWS:
        return []

    label = _candle_label(df, timeframe_label)
    signals: list[str] = []
    signals.extend(_macd_signals(df, label))
    signals.extend(_bb_signals(df, label))
    signals.extend(_rsi_signals(df, label))
    signals.extend(_ols_trend_reversal(df, label))
    return signals


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, os, sys

    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(base, ".."))

    from screener.data_fetcher import fetch_daily, fetch_1h

    config_path = os.path.join(base, "..", "config.json")
    with open(config_path, encoding="utf-8") as f:
        tickers = json.load(f)["tickers"]

    print(f"Detecting indicator signals for: {tickers}\n")

    daily_data  = fetch_daily(tickers)
    hourly_data = fetch_1h(tickers)

    any_fired = False
    for ticker in tickers:
        d_signals = detect_indicators(daily_data.get(ticker),  "daily") if ticker in daily_data  else []
        h_signals = detect_indicators(hourly_data.get(ticker), "1h")    if ticker in hourly_data else []
        all_signals = d_signals + h_signals

        # Also print raw indicator values for transparency
        df_d = daily_data.get(ticker)
        df_h = hourly_data.get(ticker)

        rsi_d = rsi_h = macd_d = macd_h = None
        if df_d is not None and len(df_d) >= 20:
            import ta as _ta
            rsi_d  = _ta.momentum.RSIIndicator(df_d["Close"], 14).rsi().iloc[-1]
            m      = _ta.trend.MACD(df_d["Close"], 26, 12, 9)
            macd_d = m.macd().iloc[-1] - m.macd_signal().iloc[-1]
        if df_h is not None and len(df_h) >= 20:
            import ta as _ta
            rsi_h  = _ta.momentum.RSIIndicator(df_h["Close"], 14).rsi().iloc[-1]
            m      = _ta.trend.MACD(df_h["Close"], 26, 12, 9)
            macd_h = m.macd().iloc[-1] - m.macd_signal().iloc[-1]

        vals  = []
        if rsi_d  is not None: vals.append(f"RSI(d)={rsi_d:.1f}")
        if rsi_h  is not None: vals.append(f"RSI(1h)={rsi_h:.1f}")
        if macd_d is not None: vals.append(f"MACD_hist(d)={macd_d:.4f}")
        if macd_h is not None: vals.append(f"MACD_hist(1h)={macd_h:.4f}")

        signal_str = ", ".join(all_signals) if all_signals else "— no signals"
        print(f"  {ticker:6}  {signal_str}")
        print(f"          {' | '.join(vals)}")
        if all_signals:
            any_fired = True

    print()
    if any_fired:
        print("Indicator detection working — signals fired on live data.")
    else:
        print("No indicator signals fired on the current candle. "
              "Check the RSI/MACD values above — all within neutral range. "
              "Detection logic is active.")
