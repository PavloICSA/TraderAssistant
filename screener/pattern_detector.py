"""
Candlestick pattern detector — detects 8 patterns on the last complete candle
of an OHLCV DataFrame.

Bullish patterns (contribute +1 to LONG score):
  Hammer, Bullish Engulfing, Morning Star, Bullish Doji

Bearish patterns (contribute -1 to SHORT score):
  Shooting Star, Bearish Engulfing, Evening Star, Bearish Doji

All patterns use manual OHLCV math (no TA-Lib dependency).

Public API:
  detect_patterns(df, timeframe_label) -> list[str]
    Returns a list of fired signal strings, e.g. ["Hammer (1h)", "Bullish Doji (daily)"]
"""

import pandas as pd


# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------

# Minimum ratio of wick length to body size to qualify as Hammer / Shooting Star
WICK_BODY_RATIO = 2.0

# Doji: body is <= this fraction of the total candle range (high - low)
DOJI_BODY_RATIO = 0.05

# Morning / Evening Star: "large body" means body > this fraction of range
STAR_LARGE_BODY_RATIO = 0.4

# Morning / Evening Star: small middle candle body < this fraction of range
STAR_SMALL_BODY_RATIO = 0.25

# Doji trend context: look back this many candles to establish trend direction
TREND_LOOKBACK = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body(o: float, c: float) -> float:
    """Absolute body size."""
    return abs(c - o)


def _range(h: float, l: float) -> float:
    """Total candle range (high - low). Returns a tiny epsilon to avoid /0."""
    return max(h - l, 1e-10)


def _upper_wick(o: float, h: float, c: float) -> float:
    return h - max(o, c)


def _lower_wick(o: float, l: float, c: float) -> float:
    return min(o, c) - l


def _is_bullish(o: float, c: float) -> bool:
    return c > o


def _is_bearish(o: float, c: float) -> bool:
    return c < o


# ---------------------------------------------------------------------------
# Single-candle patterns (operate on last candle, index -1)
# ---------------------------------------------------------------------------

def _hammer(df: pd.DataFrame) -> bool:
    """
    Hammer (bullish reversal):
      - Small body in the upper portion of the range
      - Lower wick >= WICK_BODY_RATIO * body
      - Upper wick < body
    """
    if len(df) < 2:
        return False
    o, h, l, c = df["Open"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]
    body = _body(o, c)
    if body == 0:
        return False
    low_wick  = _lower_wick(o, l, c)
    high_wick = _upper_wick(o, h, c)
    return low_wick >= WICK_BODY_RATIO * body and high_wick < body


def _shooting_star(df: pd.DataFrame) -> bool:
    """
    Shooting Star (bearish reversal):
      - Small body in the lower portion of the range
      - Upper wick >= WICK_BODY_RATIO * body
      - Lower wick < body
    """
    if len(df) < 2:
        return False
    o, h, l, c = df["Open"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]
    body = _body(o, c)
    if body == 0:
        return False
    high_wick = _upper_wick(o, h, c)
    low_wick  = _lower_wick(o, l, c)
    return high_wick >= WICK_BODY_RATIO * body and low_wick < body


def _is_doji(o: float, h: float, l: float, c: float) -> bool:
    """Body is <= DOJI_BODY_RATIO of the total candle range."""
    body  = _body(o, c)
    rng   = _range(h, l)
    return body / rng <= DOJI_BODY_RATIO


def _bullish_doji(df: pd.DataFrame) -> bool:
    """
    Bullish Doji:
      - Last candle is a Doji
      - Preceding TREND_LOOKBACK candles show a downtrend (lower lows)
    """
    if len(df) < TREND_LOOKBACK + 1:
        return False
    o, h, l, c = df["Open"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]
    if not _is_doji(o, h, l, c):
        return False
    lows = df["Low"].iloc[-(TREND_LOOKBACK + 1):-1]
    return lows.iloc[-1] < lows.iloc[0]  # last low < first low = downtrend


def _bearish_doji(df: pd.DataFrame) -> bool:
    """
    Bearish Doji:
      - Last candle is a Doji
      - Preceding TREND_LOOKBACK candles show an uptrend (higher highs)
    """
    if len(df) < TREND_LOOKBACK + 1:
        return False
    o, h, l, c = df["Open"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]
    if not _is_doji(o, h, l, c):
        return False
    highs = df["High"].iloc[-(TREND_LOOKBACK + 1):-1]
    return highs.iloc[-1] > highs.iloc[0]  # last high > first high = uptrend


# ---------------------------------------------------------------------------
# Two-candle patterns (operate on candles -2 and -1)
# ---------------------------------------------------------------------------

def _bullish_engulfing(df: pd.DataFrame) -> bool:
    """
    Bullish Engulfing:
      - Candle[-2]: bearish
      - Candle[-1]: bullish, body fully engulfs body of candle[-2]
    """
    if len(df) < 2:
        return False
    o1, c1 = df["Open"].iloc[-2], df["Close"].iloc[-2]
    o0, c0 = df["Open"].iloc[-1], df["Close"].iloc[-1]
    return (
        _is_bearish(o1, c1) and
        _is_bullish(o0, c0) and
        o0 <= c1 and   # opens at or below prior close
        c0 >= o1       # closes at or above prior open
    )


def _bearish_engulfing(df: pd.DataFrame) -> bool:
    """
    Bearish Engulfing:
      - Candle[-2]: bullish
      - Candle[-1]: bearish, body fully engulfs body of candle[-2]
    """
    if len(df) < 2:
        return False
    o1, c1 = df["Open"].iloc[-2], df["Close"].iloc[-2]
    o0, c0 = df["Open"].iloc[-1], df["Close"].iloc[-1]
    return (
        _is_bullish(o1, c1) and
        _is_bearish(o0, c0) and
        o0 >= c1 and   # opens at or above prior close
        c0 <= o1       # closes at or below prior open
    )


# ---------------------------------------------------------------------------
# Three-candle patterns (operate on candles -3, -2, -1)
# ---------------------------------------------------------------------------

def _morning_star(df: pd.DataFrame) -> bool:
    """
    Morning Star (bullish reversal):
      - Candle[-3]: large bearish body
      - Candle[-2]: small body (indecision / doji-like), gaps down or near prior close
      - Candle[-1]: large bullish body, closes above midpoint of candle[-3]
    """
    if len(df) < 3:
        return False
    o2, h2, l2, c2 = df["Open"].iloc[-3], df["High"].iloc[-3], df["Low"].iloc[-3], df["Close"].iloc[-3]
    o1, h1, l1, c1 = df["Open"].iloc[-2], df["High"].iloc[-2], df["Low"].iloc[-2], df["Close"].iloc[-2]
    o0, h0, l0, c0 = df["Open"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]

    rng2 = _range(h2, l2)
    rng1 = _range(h1, l1)
    rng0 = _range(h0, l0)

    large_bearish = _is_bearish(o2, c2) and _body(o2, c2) / rng2 >= STAR_LARGE_BODY_RATIO
    small_middle  = _body(o1, c1) / rng1 <= STAR_SMALL_BODY_RATIO
    large_bullish = _is_bullish(o0, c0) and _body(o0, c0) / rng0 >= STAR_LARGE_BODY_RATIO
    midpoint_c2   = (o2 + c2) / 2
    closes_above  = c0 > midpoint_c2

    return large_bearish and small_middle and large_bullish and closes_above


def _evening_star(df: pd.DataFrame) -> bool:
    """
    Evening Star (bearish reversal):
      - Candle[-3]: large bullish body
      - Candle[-2]: small body (indecision / doji-like), gaps up or near prior close
      - Candle[-1]: large bearish body, closes below midpoint of candle[-3]
    """
    if len(df) < 3:
        return False
    o2, h2, l2, c2 = df["Open"].iloc[-3], df["High"].iloc[-3], df["Low"].iloc[-3], df["Close"].iloc[-3]
    o1, h1, l1, c1 = df["Open"].iloc[-2], df["High"].iloc[-2], df["Low"].iloc[-2], df["Close"].iloc[-2]
    o0, h0, l0, c0 = df["Open"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]

    rng2 = _range(h2, l2)
    rng1 = _range(h1, l1)
    rng0 = _range(h0, l0)

    large_bullish = _is_bullish(o2, c2) and _body(o2, c2) / rng2 >= STAR_LARGE_BODY_RATIO
    small_middle  = _body(o1, c1) / rng1 <= STAR_SMALL_BODY_RATIO
    large_bearish = _is_bearish(o0, c0) and _body(o0, c0) / rng0 >= STAR_LARGE_BODY_RATIO
    midpoint_c2   = (o2 + c2) / 2
    closes_below  = c0 < midpoint_c2

    return large_bullish and small_middle and large_bearish and closes_below


# ---------------------------------------------------------------------------
# Candle date label helper
# ---------------------------------------------------------------------------

def _candle_label(df: pd.DataFrame, timeframe_label: str) -> str:
    """
    Build a display label including the candle date and a staleness warning
    if the last candle is older than expected for its timeframe.

    Examples:
      "daily, Sep 25"
      "daily, Sep 24 ⚠ stale"
      "1h, 14:30"
    """
    from datetime import datetime, timezone, timedelta

    last_ts = df.index[-1]

    # Normalise to a timezone-aware datetime
    if hasattr(last_ts, 'tzinfo') and last_ts.tzinfo is not None:
        last_dt = last_ts.to_pydatetime()
    else:
        last_dt = last_ts.to_pydatetime().replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)

    if timeframe_label == "daily":
        date_str = last_dt.strftime("%b %d")
        # Stale if the last daily candle is more than 3 calendar days old
        # (accounts for weekends and market holidays)
        stale = (now - last_dt).days > 3
        suffix = " ⚠ stale" if stale else ""
        return f"{timeframe_label}, {date_str}{suffix}"
    else:
        # For intraday, show the time; stale if > 26 hours old
        time_str = last_dt.strftime("%H:%M")
        stale = (now - last_dt).total_seconds() > 26 * 3600
        suffix = " ⚠ stale" if stale else ""
        return f"{timeframe_label}, {time_str}{suffix}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_patterns(df: pd.DataFrame, timeframe_label: str) -> list[str]:
    """
    Detect all 8 candlestick patterns on the last complete candle of df.

    Args:
        df:               OHLCV DataFrame (columns: Open, High, Low, Close, Volume)
        timeframe_label:  e.g. "daily" or "1h" — appended to signal strings

    Returns:
        List of fired signal strings, e.g. ["Hammer (1h, Sep 25)", "Bullish Doji (daily, Sep 24 ⚠ stale)"]
    """
    if df is None or len(df) < 3:
        return []

    signals: list[str] = []
    label = _candle_label(df, timeframe_label)

    # Bullish patterns
    if _hammer(df):
        signals.append(f"Hammer ({label})")
    if _bullish_engulfing(df):
        signals.append(f"Bullish Engulfing ({label})")
    if _morning_star(df):
        signals.append(f"Morning Star ({label})")
    if _bullish_doji(df):
        signals.append(f"Bullish Doji ({label})")

    # Bearish patterns
    if _shooting_star(df):
        signals.append(f"Shooting Star ({label})")
    if _bearish_engulfing(df):
        signals.append(f"Bearish Engulfing ({label})")
    if _evening_star(df):
        signals.append(f"Evening Star ({label})")
    if _bearish_doji(df):
        signals.append(f"Bearish Doji ({label})")

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

    print(f"Detecting candlestick patterns for: {tickers}\n")

    daily_data = fetch_daily(tickers)
    hourly_data = fetch_1h(tickers)

    any_fired = False
    for ticker in tickers:
        daily_signals = detect_patterns(daily_data.get(ticker), "daily") if ticker in daily_data else []
        hourly_signals = detect_patterns(hourly_data.get(ticker), "1h")   if ticker in hourly_data else []
        all_signals = daily_signals + hourly_signals
        status = ", ".join(all_signals) if all_signals else "— no patterns"
        print(f"  {ticker:6}  {status}")
        if all_signals:
            any_fired = True

    print()
    if any_fired:
        print("Pattern detection working — signals fired on live data.")
    else:
        print("No patterns fired on the current candle. This is normal — "
              "patterns are relatively rare. The detection logic is active.")
