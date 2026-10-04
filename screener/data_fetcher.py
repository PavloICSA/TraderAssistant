"""
Data fetcher — fetches OHLCV data from Yahoo Finance via yfinance.

Provides:
  fetch_daily(tickers)  -> tuple[dict[str, pd.DataFrame], dict[str, str]]
  fetch_1h(tickers)     -> tuple[dict[str, pd.DataFrame], dict[str, str]]

Each DataFrame has columns: Open, High, Low, Close, Volume (float64).
Returns (results, failed) where failed maps ticker -> error reason.
Raises DataFetchError only when ALL tickers fail.

Symbol normalisation (_candidates):
  Users may enter symbols in natural formats across all asset classes.
  The fetcher tries an ordered candidate chain per ticker:
    Stocks/ETFs/indices  →  AAPL, SPY, ^VIX  (pass through)
    Crypto bare          →  SOL → [SOL, SOL-USD]
    Forex                →  EURUSD / EUR/USD → [EURUSD=X]
    Futures roots        →  GC / CL → [GC=F, GC]

Fetches are parallelised with ThreadPoolExecutor (MAX_WORKERS threads).
"""

import re
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_WORKERS = 10

# ---------------------------------------------------------------------------
# Known futures roots → Yahoo =F suffix
# ---------------------------------------------------------------------------
_FUTURES_ROOTS = {
    "GC", "SI", "HG", "PL", "PA",           # metals
    "CL", "NG", "RB", "HO", "BZ",           # energy
    "ZW", "ZC", "ZS", "ZO", "ZR",           # grains
    "CC", "KC", "SB", "CT",                  # softs
    "ES", "NQ", "YM", "RTY",                 # equity index futures
}

# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------

def _candidates(raw: str) -> list[str]:
    """
    Given a user-supplied symbol, return an ordered list of Yahoo Finance
    candidates to try (most likely first).
    """
    s = raw.strip().upper()

    # Already fully qualified — return as-is
    if s.endswith("=X") or s.endswith("=F") or s.endswith("-USD"):
        return [s]

    # Index symbols
    if s.startswith("^"):
        return [s]

    # Forex: strip common separators, check for two 3-letter currency codes
    s_clean = re.sub(r"[/\-\s]", "", s)
    if len(s_clean) == 6 and s_clean.isalpha():
        _CURRENCIES = {
            "USD","EUR","GBP","JPY","CHF","AUD","CAD","NZD","HKD","SGD",
            "NOK","SEK","DKK","MXN","TRY","ZAR","CNY","CNH","INR","BRL",
            "RUB","KRW","TWD","THB","PLN","CZK","HUF","ILS","CLP","COP",
        }
        if s_clean[:3] in _CURRENCIES and s_clean[3:] in _CURRENCIES:
            return [s_clean + "=X"]

    # Known futures root
    if s in _FUTURES_ROOTS:
        return [s + "=F", s]

    # Default: try as-is, then with -USD (catches bare crypto like SOL, ADA)
    return [s, s + "-USD"]


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
    Fetch OHLCV for a single ticker using the _candidates resolution chain.
    Returns (ticker, df, error_msg) — ticker key is always the original
    user-supplied symbol regardless of which candidate succeeded.
    """
    last_err = None
    for candidate in _candidates(ticker):
        try:
            raw = yf.download(
                candidate,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
            )
            df = _normalise(raw, candidate, interval)
            return ticker, df, None          # success — keep original key
        except DataFetchError as e:
            last_err = str(e)
        except Exception as e:
            last_err = f"{candidate} ({interval}): unexpected error — {e}"

    return ticker, None, last_err or f"No data found for {ticker}."


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
