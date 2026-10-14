from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf

from auditlens.utils import PROJECT_ROOT, ensure_output_directories, project_path, write_json


STATEMENT_FIELDS: dict[str, tuple[str, ...]] = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "net_income": ("Net Income", "Net Income Common Stockholders"),
    "ebit": ("EBIT", "Operating Income"),
    "interest_expense": ("Interest Expense", "Interest Expense Non Operating"),
    "gross_profit": ("Gross Profit",),
    "total_assets": ("Total Assets",),
    "total_liabilities": (
        "Total Liabilities Net Minority Interest",
        "Total Liabilities",
    ),
    "current_assets": ("Current Assets",),
    "current_liabilities": ("Current Liabilities",),
    "cash": (
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents",
        "Cash Financial",
    ),
    "total_debt": ("Total Debt",),
    "accounts_receivable": ("Accounts Receivable", "Receivables"),
    "inventory": ("Inventory",),
    "common_equity": (
        "Stockholders Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    ),
    "shares_outstanding": (
        "Ordinary Shares Number",
        "Share Issued",
    ),
    "operating_cash_flow": (
        "Operating Cash Flow",
        "Total Cash From Operating Activities",
    ),
    "free_cash_flow": ("Free Cash Flow",),
}


@dataclass
class FetchResult:
    prices: pd.DataFrame
    fundamentals: pd.DataFrame
    universe: pd.DataFrame
    metadata: dict


def _numeric_value(frame: pd.DataFrame, aliases: Iterable[str], period: pd.Timestamp) -> float:
    if frame is None or frame.empty:
        return np.nan
    matching_columns = [
        column
        for column in frame.columns
        if pd.Timestamp(column).normalize() == pd.Timestamp(period).normalize()
    ]
    if not matching_columns:
        return np.nan
    source_period = matching_columns[0]
    for name in aliases:
        if name in frame.index:
            value = pd.to_numeric(frame.at[name, source_period], errors="coerce")
            return float(value) if pd.notna(value) else np.nan
    return np.nan


def _normalize_earnings_dates(raw: pd.DataFrame | None) -> pd.DatetimeIndex:
    if raw is None or raw.empty:
        return pd.DatetimeIndex([])
    dates = pd.DatetimeIndex(pd.to_datetime(raw.index, errors="coerce")).dropna()
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    return dates.normalize().sort_values().unique()


def _publication_date(
    period: pd.Timestamp,
    earnings_dates: pd.DatetimeIndex,
    window_days: int,
    fallback_lag_days: int,
) -> tuple[pd.Timestamp, str]:
    lower = period + pd.Timedelta(days=1)
    upper = period + pd.Timedelta(days=window_days)
    candidates = earnings_dates[(earnings_dates >= lower) & (earnings_dates <= upper)]
    if len(candidates):
        return pd.Timestamp(candidates[0]), "reported_earnings_date"
    return period + pd.Timedelta(days=fallback_lag_days), "conservative_lag"


def fetch_ticker_fundamentals(
    ticker_symbol: str,
    company: str,
    industry: str,
    earnings_window_days: int,
    fallback_lag_days: int,
) -> pd.DataFrame:
    ticker = yf.Ticker(ticker_symbol)
    # The property accessors return human-readable row labels (for example
    # ``Total Revenue``), while the ``get_*_stmt`` methods currently return
    # compact labels (for example ``TotalRevenue``).  Using one stable schema
    # keeps the field map explicit and auditable.
    income = ticker.income_stmt
    balance = ticker.balance_sheet
    cashflow = ticker.cash_flow
    try:
        earnings_dates = _normalize_earnings_dates(ticker.get_earnings_dates(limit=40))
    except Exception:
        earnings_dates = pd.DatetimeIndex([])

    periods: set[pd.Timestamp] = set()
    for frame in (income, balance, cashflow):
        if frame is not None and not frame.empty:
            periods.update(pd.Timestamp(value).normalize() for value in frame.columns)

    records: list[dict] = []
    for period in sorted(periods):
        publication_date, date_source = _publication_date(
            period,
            earnings_dates,
            earnings_window_days,
            fallback_lag_days,
        )
        record = {
            "ticker": ticker_symbol,
            "company": company,
            "industry": industry,
            "stat_date": period,
            "publication_date": publication_date,
            "publication_date_source": date_source,
        }
        for output_name, aliases in STATEMENT_FIELDS.items():
            source = cashflow if output_name in {"operating_cash_flow", "free_cash_flow"} else (
                income
                if output_name
                in {"revenue", "net_income", "ebit", "interest_expense", "gross_profit"}
                else balance
            )
            record[output_name] = _numeric_value(source, aliases, period)
        records.append(record)
    return pd.DataFrame.from_records(records)


def download_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if raw.empty:
        raise RuntimeError("No price data were downloaded.")
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"].copy()
    else:
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close = close.sort_index().dropna(axis=1, how="all")
    close.columns.name = None
    return close


def fetch_all(config: dict, force: bool = False) -> FetchResult:
    ensure_output_directories()
    prices_path = PROJECT_ROOT / "data/raw/prices.parquet"
    fundamentals_path = PROJECT_ROOT / "data/raw/fundamentals.parquet"
    universe_snapshot_path = PROJECT_ROOT / "data/raw/universe_snapshot.csv"
    metadata_path = PROJECT_ROOT / "data/raw/fetch_metadata.json"

    universe = pd.read_csv(project_path(config["project"]["universe_file"]))
    benchmark = config["project"]["benchmark_ticker"]

    if not force and prices_path.exists() and fundamentals_path.exists():
        prices = pd.read_parquet(prices_path)
        fundamentals = pd.read_parquet(fundamentals_path)
        metadata = {
            "cache_used": True,
            "prices_path": str(prices_path),
            "fundamentals_path": str(fundamentals_path),
        }
        return FetchResult(prices, fundamentals, universe, metadata)

    requested_tickers = universe["ticker"].tolist()
    price_tickers = requested_tickers + [benchmark]
    print(f"Downloading prices for {len(price_tickers)} symbols...")
    prices = download_prices(
        price_tickers,
        config["project"]["price_start"],
        config["project"]["price_end"],
    )

    frames: list[pd.DataFrame] = []
    failures: dict[str, str] = {}
    for position, row in enumerate(universe.itertuples(index=False), start=1):
        print(f"[{position:02d}/{len(universe):02d}] fundamentals {row.ticker} {row.company}")
        try:
            frame = fetch_ticker_fundamentals(
                row.ticker,
                row.company,
                row.industry,
                int(config["project"]["earnings_date_window_days"]),
                int(config["project"]["fallback_publication_lag_days"]),
            )
            if frame.empty:
                failures[row.ticker] = "empty financial statements"
            else:
                frames.append(frame)
        except Exception as exc:
            failures[row.ticker] = f"{type(exc).__name__}: {exc}"

    if not frames:
        raise RuntimeError("No financial statements were downloaded.")
    fundamentals = pd.concat(frames, ignore_index=True)
    fundamentals = fundamentals.sort_values(["ticker", "stat_date"]).reset_index(drop=True)

    prices.to_parquet(prices_path)
    fundamentals.to_parquet(fundamentals_path, index=False)
    universe.to_csv(universe_snapshot_path, index=False)
    metadata = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Yahoo Finance via yfinance",
        "price_start": config["project"]["price_start"],
        "price_end_exclusive": config["project"]["price_end"],
        "requested_tickers": len(requested_tickers),
        "price_tickers_returned": [str(value) for value in prices.columns],
        "fundamental_tickers_returned": sorted(fundamentals["ticker"].unique().tolist()),
        "fundamental_failures": failures,
        "publication_date_sources": fundamentals["publication_date_source"].value_counts().to_dict(),
        "cache_used": False,
    }
    write_json(metadata_path, metadata)
    return FetchResult(prices, fundamentals, universe, metadata)


def load_cached_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prices_path = PROJECT_ROOT / "data/raw/prices.parquet"
    fundamentals_path = PROJECT_ROOT / "data/raw/fundamentals.parquet"
    universe_path = PROJECT_ROOT / "data/raw/universe_snapshot.csv"
    missing = [path for path in (prices_path, fundamentals_path, universe_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing cached data files: {missing}. Run the fetch command first.")
    return (
        pd.read_parquet(prices_path),
        pd.read_parquet(fundamentals_path),
        pd.read_csv(universe_path),
    )
