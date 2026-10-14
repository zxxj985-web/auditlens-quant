from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    performance: pd.DataFrame
    weights: pd.DataFrame
    quality_filter_weights: pd.DataFrame
    baseline_weights: pd.DataFrame
    metrics: pd.DataFrame
    factor_ic: pd.DataFrame
    yearly_returns: pd.DataFrame


def _portfolio_weights(
    scores: pd.DataFrame,
    price_columns: list[str],
    score_column: str,
    selection_fraction: float,
    quality_filter_exclude_fraction: float,
    minimum_names: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.DatetimeIndex(sorted(scores["rebalance_date"].unique()))
    strategy = pd.DataFrame(0.0, index=dates, columns=price_columns)
    quality_filter = pd.DataFrame(0.0, index=dates, columns=price_columns)
    baseline = pd.DataFrame(0.0, index=dates, columns=price_columns)

    for date, group in scores.groupby("rebalance_date"):
        valid = group.dropna(subset=[score_column])
        valid = valid[valid["ticker"].isin(price_columns)]
        names = valid["ticker"].drop_duplicates().tolist()
        if len(names) < minimum_names:
            continue
        baseline.loc[date, names] = 1.0 / len(names)

        keep_count = min(
            len(valid),
            max(minimum_names, int(np.ceil(len(valid) * selection_fraction))),
        )
        selected = (
            valid.sort_values([score_column, "ticker"], ascending=[False, True])
            .drop_duplicates("ticker")
            .head(keep_count)["ticker"]
            .tolist()
        )
        strategy.loc[date, selected] = 1.0 / len(selected)

        # Keep the V1 comparison independent of V2 eligibility. Otherwise a
        # missing V2 market factor would silently change the historical V1
        # portfolio and make the version comparison unfair.
        quality_valid = group.dropna(subset=["quality_score"])
        quality_valid = quality_valid[quality_valid["ticker"].isin(price_columns)]
        quality_keep_count = min(
            len(quality_valid),
            max(
                minimum_names,
                int(np.ceil(len(quality_valid) * (1 - quality_filter_exclude_fraction))),
            ),
        )
        quality_selected = (
            quality_valid.sort_values(["quality_score", "ticker"], ascending=[False, True])
            .drop_duplicates("ticker")
            .head(quality_keep_count)["ticker"]
            .tolist()
        )
        if quality_selected:
            quality_filter.loc[date, quality_selected] = 1.0 / len(quality_selected)
    return strategy, quality_filter, baseline


def _returns_with_costs(
    weights: pd.DataFrame,
    asset_returns: pd.DataFrame,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    weights = weights.reindex(asset_returns.index).fillna(0.0)
    executed_weights = weights.shift(1).fillna(0.0)
    gross = (executed_weights * asset_returns.fillna(0.0)).sum(axis=1)

    turnover = 0.5 * executed_weights.diff().abs().sum(axis=1)
    first_invested = executed_weights.sum(axis=1).gt(0)
    if first_invested.any():
        first_date = first_invested.idxmax()
        turnover.loc[first_date] = executed_weights.loc[first_date].abs().sum()
    costs = turnover * cost_bps / 10_000
    net = gross - costs
    holdings = executed_weights.gt(0).sum(axis=1)
    net = net.where(holdings > 0)
    gross = gross.where(holdings > 0)
    return net, gross, costs, turnover


def performance_metrics(
    returns: pd.Series,
    annualization: int = 12,
    turnover: pd.Series | None = None,
) -> dict[str, float]:
    clean = returns.dropna()
    if clean.empty:
        return {key: np.nan for key in (
            "total_return", "annualized_return", "annualized_volatility", "sharpe",
            "max_drawdown", "calmar", "monthly_win_rate", "months", "average_monthly_turnover"
        )}
    wealth = (1 + clean).cumprod()
    total_return = wealth.iloc[-1] - 1
    years = len(clean) / annualization
    annualized_return = wealth.iloc[-1] ** (1 / years) - 1 if years > 0 and wealth.iloc[-1] > 0 else np.nan
    volatility = clean.std(ddof=1) * np.sqrt(annualization)
    sharpe = annualized_return / volatility if volatility and volatility > 0 else np.nan
    drawdown = wealth / wealth.cummax() - 1
    max_drawdown = drawdown.min()
    calmar = annualized_return / abs(max_drawdown) if max_drawdown < 0 else np.nan
    average_turnover = np.nan
    if turnover is not None:
        average_turnover = turnover.reindex(clean.index).mean()
    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "monthly_win_rate": (clean > 0).mean(),
        "months": float(len(clean)),
        "average_monthly_turnover": average_turnover,
    }


def _factor_rank_ic(scored_panel: pd.DataFrame, monthly_returns: pd.DataFrame) -> pd.DataFrame:
    forward = monthly_returns.shift(-1)
    records: list[dict] = []
    factor_columns = [column for column in scored_panel.columns if column.startswith("z_")]
    factor_columns.extend(
        column
        for column in scored_panel.columns
        if column.endswith("_score") and column not in factor_columns
    )
    for date, group in scored_panel.groupby("rebalance_date"):
        if date not in forward.index:
            continue
        next_returns = forward.loc[date]
        for factor in factor_columns:
            sample = group[["ticker", factor]].dropna()
            sample["forward_return"] = sample["ticker"].map(next_returns)
            sample = sample.dropna()
            if len(sample) < 5:
                value = np.nan
            else:
                value = sample[factor].rank().corr(sample["forward_return"].rank())
            records.append(
                {
                    "rebalance_date": date,
                    "factor": factor.removeprefix("z_"),
                    "rank_ic": value,
                    "n": len(sample),
                }
            )
    return pd.DataFrame(records)


def run_backtest(
    prices: pd.DataFrame,
    scored_panel: pd.DataFrame,
    universe_tickers: list[str],
    benchmark_ticker: str,
    config: dict,
) -> BacktestResult:
    monthly_prices = prices.sort_index().resample(config["rebalance_frequency"]).last()
    available_tickers = [ticker for ticker in universe_tickers if ticker in monthly_prices.columns]
    asset_returns = monthly_prices[available_tickers].pct_change(fill_method=None)

    strategy_weights, quality_filter_weights, baseline_weights = _portfolio_weights(
        scored_panel,
        available_tickers,
        str(config.get("score_column", "alpha_score")),
        float(config.get("selection_fraction", 0.30)),
        float(config.get("quality_filter_exclude_fraction", 0.20)),
        int(config["minimum_names"]),
    )
    strategy_weights = strategy_weights.reindex(monthly_prices.index).fillna(0.0)
    quality_filter_weights = quality_filter_weights.reindex(monthly_prices.index).fillna(0.0)
    baseline_weights = baseline_weights.reindex(monthly_prices.index).fillna(0.0)

    strategy, strategy_gross, strategy_cost, strategy_turnover = _returns_with_costs(
        strategy_weights, asset_returns, float(config["transaction_cost_bps"])
    )
    quality_filter, quality_filter_gross, quality_filter_cost, quality_filter_turnover = _returns_with_costs(
        quality_filter_weights, asset_returns, float(config["transaction_cost_bps"])
    )
    baseline, baseline_gross, baseline_cost, baseline_turnover = _returns_with_costs(
        baseline_weights, asset_returns, float(config["transaction_cost_bps"])
    )
    benchmark = monthly_prices[benchmark_ticker].pct_change(fill_method=None)

    performance = pd.DataFrame(
        {
            "alpha_strategy": strategy,
            "quality_filter": quality_filter,
            "equal_weight": baseline,
            "benchmark": benchmark,
            "alpha_strategy_gross": strategy_gross,
            "alpha_strategy_cost": strategy_cost,
            "alpha_strategy_turnover": strategy_turnover,
            "quality_filter_gross": quality_filter_gross,
            "quality_filter_cost": quality_filter_cost,
            "quality_filter_turnover": quality_filter_turnover,
            "equal_weight_gross": baseline_gross,
            "equal_weight_cost": baseline_cost,
            "equal_weight_turnover": baseline_turnover,
            "alpha_strategy_holdings": strategy_weights.shift(1).gt(0).sum(axis=1),
            "quality_filter_holdings": quality_filter_weights.shift(1).gt(0).sum(axis=1),
            "equal_weight_holdings": baseline_weights.shift(1).gt(0).sum(axis=1),
        }
    )
    first_valid = performance["alpha_strategy"].first_valid_index()
    if first_valid is not None:
        performance = performance.loc[first_valid:]

    metric_rows: list[dict] = []
    for label, returns, turnover in (
        ("alpha_strategy", performance["alpha_strategy"], performance["alpha_strategy_turnover"]),
        ("quality_filter", performance["quality_filter"], performance["quality_filter_turnover"]),
        ("equal_weight", performance["equal_weight"], performance["equal_weight_turnover"]),
        ("benchmark", performance["benchmark"], None),
    ):
        metric_rows.append({"period": "full", "portfolio": label, **performance_metrics(
            returns, int(config["annualization_periods"]), turnover
        )})

    validation_start = pd.Timestamp(
        config.get("validation_start", config.get("out_of_sample_start", "2026-01-01"))
    )
    validation = performance.loc[performance.index >= validation_start]
    for label, returns, turnover in (
        ("alpha_strategy", validation["alpha_strategy"], validation["alpha_strategy_turnover"]),
        ("quality_filter", validation["quality_filter"], validation["quality_filter_turnover"]),
        ("equal_weight", validation["equal_weight"], validation["equal_weight_turnover"]),
        ("benchmark", validation["benchmark"], None),
    ):
        metric_rows.append({"period": "validation", "portfolio": label, **performance_metrics(
            returns, int(config["annualization_periods"]), turnover
        )})
    metrics = pd.DataFrame(metric_rows)

    factor_ic = _factor_rank_ic(scored_panel, asset_returns)
    yearly_returns = (
        performance[["alpha_strategy", "quality_filter", "equal_weight", "benchmark"]]
        .groupby(performance.index.year)
        .apply(lambda frame: (1 + frame).prod(min_count=1) - 1, include_groups=False)
    )
    yearly_returns.index.name = "year"
    return BacktestResult(
        performance=performance,
        weights=strategy_weights,
        quality_filter_weights=quality_filter_weights,
        baseline_weights=baseline_weights,
        metrics=metrics,
        factor_ic=factor_ic,
        yearly_returns=yearly_returns,
    )
