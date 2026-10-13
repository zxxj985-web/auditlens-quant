from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from auditlens.backtest import run_backtest
from auditlens.data import fetch_all, load_cached_data
from auditlens.features import (
    align_factors_point_in_time,
    build_fundamental_factors,
    monthly_rebalance_dates,
    score_cross_sections,
)
from auditlens.reporting import create_figures, write_markdown_report
from auditlens.utils import PROJECT_ROOT, ensure_output_directories, load_config


DEFAULT_CONFIG = PROJECT_ROOT / "configs/base.yaml"


def _run_analysis(config: dict) -> None:
    ensure_output_directories()
    prices, fundamentals, universe = load_cached_data()
    factors = build_fundamental_factors(fundamentals)
    rebalance_dates = monthly_rebalance_dates(
        prices,
        config["backtest"]["rebalance_frequency"],
    )
    panel = align_factors_point_in_time(factors, rebalance_dates)
    scored = score_cross_sections(panel, config["factors"])
    result = run_backtest(
        prices=prices,
        scored_panel=scored,
        universe_tickers=universe["ticker"].tolist(),
        benchmark_ticker=config["project"]["benchmark_ticker"],
        config=config["backtest"],
    )

    processed = PROJECT_ROOT / "data/processed"
    scored.to_parquet(processed / "factor_panel.parquet", index=False)
    result.weights.to_parquet(processed / "strategy_weights.parquet")

    tables = PROJECT_ROOT / "outputs/tables"
    result.performance.to_csv(tables / "monthly_performance.csv", index_label="date")
    result.metrics.to_csv(tables / "performance_metrics.csv", index=False)
    result.factor_ic.to_csv(tables / "factor_rank_ic.csv", index=False)
    result.yearly_returns.to_csv(tables / "yearly_returns.csv")
    (
        scored.groupby("rebalance_date")
        .agg(
            scored_companies=("quality_score", "count"),
            median_factor_count=("factor_count", "median"),
            newest_statement=("stat_date", "max"),
        )
        .to_csv(tables / "data_quality_by_month.csv")
    )

    create_figures(result, scored)
    report_path = write_markdown_report(result, scored, fundamentals, config)
    print(f"Analysis complete. Report: {report_path}")
    print(result.metrics.to_string(index=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AuditLens Quant research pipeline")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to YAML configuration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Download and cache public market data")
    fetch_parser.add_argument("--force", action="store_true", help="Replace the local cache")

    subparsers.add_parser("run", help="Run factors, backtest, figures, and report from cache")

    all_parser = subparsers.add_parser("all", help="Fetch data and run the full pipeline")
    all_parser.add_argument("--force", action="store_true", help="Replace the local cache")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(Path(args.config))
    if args.command in {"fetch", "all"}:
        fetch_all(config, force=bool(args.force))
    if args.command in {"run", "all"}:
        _run_analysis(config)
