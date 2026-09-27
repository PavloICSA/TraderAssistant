"""
Indicator signal detector — detects MACD, Bollinger Band, and RSI signals
on an OHLCV DataFrame using the `ta` library.

Bullish signals (contribute +1 to LONG score):
  - MACD bullish crossover  (MACD line crosses above signal line from below)
  - Lower Bollinger Band touch/cross  (close <= lower band)
  - RSI oversold  (RSI < 30)

Bearish signals (contribute -1 to SHORT score):
  - MACD bearish crossover  (MACD line crosses below signal line from above)
  - Upper Bollinger Band touch/cross  (close >= upper band)
  - RSI overbought  (RSI > 70)

All signals are evaluated on the last complete candle (index -1), using
candle -2 as the prior candle for crossover detection.

Public API:
  detect_indicators(df, timeframe_label) -> list[str]
    Returns a list of fired signal strings, e.g.
    ["MACD bullish crossover (1h)", "RSI oversold (daily)"]
"""

import pandas as pd
import ta


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
    Detect Bollinger Band lower-band touch (bullish) and upper-band touch (bearish)
    on the last candle.
    """
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

    if upper.isna().iloc[-1] or lower.isna().iloc[-1]:
        return []

    close = df["Close"].iloc[-1]
    signals = []

    if close <= lower.iloc[-1]:
        signals.append(f"Lower BB touch ({label})")
    if close >= upper.iloc[-1]:
        signals.append(f"Upper BB touch ({label})")
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

    label = timeframe_label
    signals: list[str] = []
    signals.extend(_macd_signals(df, label))
    signals.extend(_bb_signals(df, label))
    signals.extend(_rsi_signals(df, label))
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
