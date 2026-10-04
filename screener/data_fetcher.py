"""
Data fetcher — fetches OHLCV data from Yahoo Finance via yfinance.

Provides:
  fetch_daily(tickers)  -> dict[str, pd.DataFrame]  (90-day lookback, 1d interval)
  fetch_1h(tickers)     -> dict[str, pd.DataFrame]  (30-day lookback, 1h interval)

Each DataFrame has columns: Open, High, Low, Close, Volume (float64).
Raises DataFetchError when a network failure or empty response occurs.

Fetches are parallelised with ThreadPoolExecutor (MAX_WORKERS threads) to
keep scan time reasonable for large watchlists.
"""

import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# Maximum parallel yfinance requests — keeps us well clear of rate limits
MAX_WORKERS = 10


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


def _fetch_one(ticker: str, period: str, interval: str) -> tuple[str, pd.DataFrame | None, str | None]:
    """
    Fetch OHLCV for a single ticker. Returns (ticker, df, error_msg).

    If the ticker returns empty data and doesn't already end in '-USD',
    automatically retries with '-USD' appended (handles crypto symbols like
    SOL → SOL-USD, BNB → BNB-USD).  The original ticker key is preserved
    in the result so the rest of the pipeline is unaffected.
    """
    def _try(sym: str) -> tuple[pd.DataFrame | None, str | None]:
        try:
            raw = yf.download(
                sym,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
            )
            return _normalise(raw, sym, interval), None
        except DataFetchError as e:
            return None, str(e)
        except Exception as e:
            return None, f"{sym} ({interval}): unexpected error — {e}"

    df, err = _try(ticker)

    # Auto-retry with -USD suffix for crypto symbols entered without it
    if df is None and not ticker.upper().endswith("-USD"):
        df_retry, err_retry = _try(ticker + "-USD")
        if df_retry is not None:
            return ticker, df_retry, None   # success — keep original ticker key
        # Both failed; return the original error (more recognisable to the user)

    return ticker, df, err


def fetch_daily(tickers: list[str]) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """
    Fetch 90 days of daily OHLCV data for each ticker, concurrently.

    Returns:
        (results, failed)
        results: dict[ticker -> DataFrame] for successful fetches
        failed:  dict[ticker -> reason]   for tickers that could not be fetched

    Raises DataFetchError only when ALL tickers fail.
    """
    results: dict[str, pd.DataFrame] = {}
    failed:  dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t, "90d", "1d"): t for t in tickers}
        for future in as_completed(futures):
            ticker, df, err = future.result()
            if df is not None:
                results[ticker] = df
            else:
                failed[ticker] = err or "Unknown error"

    if not results:
        raise DataFetchError(
            "Failed to fetch daily data for all tickers.\n" +
            "\n".join(f"  {t}: {r}" for t, r in failed.items())
        )
    return results, failed


def fetch_1h(tickers: list[str]) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """
    Fetch 30 days of 1-hour OHLCV data for each ticker, concurrently.

    Returns:
        (results, failed)
        results: dict[ticker -> DataFrame] for successful fetches
        failed:  dict[ticker -> reason]   for tickers that could not be fetched

    Raises DataFetchError only when ALL tickers fail.
    """
    results: dict[str, pd.DataFrame] = {}
    failed:  dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t, "30d", "1h"): t for t in tickers}
        for future in as_completed(futures):
            ticker, df, err = future.result()
            if df is not None:
                results[ticker] = df
            else:
                failed[ticker] = err or "Unknown error"

    if not results:
        raise DataFetchError(
            "Failed to fetch 1h data for all tickers.\n" +
            "\n".join(f"  {t}: {r}" for t, r in failed.items())
        )
    return results, failed


# ---------------------------------------------------------------------------
# Manual test entry point (benchmarks concurrent fetching)
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
