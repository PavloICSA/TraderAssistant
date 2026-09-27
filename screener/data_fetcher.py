"""
Data fetcher — fetches OHLCV data from Yahoo Finance via yfinance.

Provides:
  fetch_daily(tickers)  -> dict[str, pd.DataFrame]  (90-day lookback, 1d interval)
  fetch_1h(tickers)     -> dict[str, pd.DataFrame]  (30-day lookback, 1h interval)

Each DataFrame has columns: Open, High, Low, Close, Volume (float64).
Raises DataFetchError when a network failure or empty response occurs.
"""

import yfinance as yf
import pandas as pd


class DataFetchError(Exception):
    """Raised when OHLCV data cannot be fetched or is empty."""
    pass


def _normalise(df: pd.DataFrame, ticker: str, timeframe: str) -> pd.DataFrame:
    """
    Normalise a raw yfinance DataFrame to a clean 5-column OHLCV frame.
    yfinance may return a MultiIndex when downloading a single ticker via
    yf.download(); this flattens it.
    """
    if df is None or df.empty:
        raise DataFetchError(
            f"No data returned for {ticker} ({timeframe}). "
            "The ticker may be invalid or Yahoo Finance may be unavailable."
        )

    # Flatten MultiIndex columns produced by yf.download (ticker, field) -> field
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Keep only the standard OHLCV columns
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataFetchError(
            f"Missing columns {missing} for {ticker} ({timeframe})."
        )

    df = df[required].copy()
    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)

    if df.empty:
        raise DataFetchError(
            f"All rows dropped after NaN removal for {ticker} ({timeframe})."
        )

    return df


def fetch_daily(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    Fetch 90 days of daily OHLCV data for each ticker.

    Returns a dict mapping ticker symbol -> DataFrame.
    Skips tickers that fail individually; raises DataFetchError only when
    ALL tickers fail.
    """
    results: dict[str, pd.DataFrame] = {}
    errors: list[str] = []

    for ticker in tickers:
        try:
            raw = yf.download(
                ticker,
                period="90d",
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
            results[ticker] = _normalise(raw, ticker, "daily")
        except DataFetchError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"{ticker} (daily): unexpected error — {e}")

    if not results:
        raise DataFetchError(
            "Failed to fetch daily data for all tickers. Errors:\n" +
            "\n".join(errors)
        )

    return results


def fetch_1h(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    Fetch 30 days of 1-hour OHLCV data for each ticker.
    yfinance supports 1h up to ~730 days but freshness degrades; 30d is reliable.

    Returns a dict mapping ticker symbol -> DataFrame.
    Skips tickers that fail individually; raises DataFetchError only when
    ALL tickers fail.
    """
    results: dict[str, pd.DataFrame] = {}
    errors: list[str] = []

    for ticker in tickers:
        try:
            raw = yf.download(
                ticker,
                period="30d",
                interval="1h",
                auto_adjust=True,
                progress=False,
            )
            results[ticker] = _normalise(raw, ticker, "1h")
        except DataFetchError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"{ticker} (1h): unexpected error — {e}")

    if not results:
        raise DataFetchError(
            "Failed to fetch 1h data for all tickers. Errors:\n" +
            "\n".join(errors)
        )

    return results


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json, os, sys

    # Support running as: python screener/data_fetcher.py OR python -m screener.data_fetcher
    base = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base, "..", "config.json")
    sys.path.insert(0, os.path.join(base, ".."))

    with open(config_path, encoding="utf-8") as f:
        tickers = json.load(f)["tickers"]

    print(f"Fetching data for: {tickers}\n")

    print("=== DAILY (90d) ===")
    daily = fetch_daily(tickers)
    for ticker, df in daily.items():
        print(f"  {ticker:6}  shape={df.shape}  "
              f"first={df.index[0].date()}  last={df.index[-1].date()}  "
              f"close[-1]={df['Close'].iloc[-1]:.2f}")

    print()
    print("=== 1-HOUR (30d) ===")
    hourly = fetch_1h(tickers)
    for ticker, df in hourly.items():
        print(f"  {ticker:6}  shape={df.shape}  "
              f"last={str(df.index[-1])[:16]}  "
              f"close[-1]={df['Close'].iloc[-1]:.2f}")
