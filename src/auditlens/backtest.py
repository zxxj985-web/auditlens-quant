from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    performance: pd.DataFrame
    weights: pd.DataFrame
    baseline_weights: pd.DataFrame
    metrics: pd.DataFrame
    factor_ic: pd.DataFrame
    yearly_returns: pd.DataFrame


def _portfolio_weights(
    scores: pd.DataFrame,
    price_columns: list[str],
    exclude_bottom_fraction: float,
    minimum_names: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.DatetimeIndex(sorted(scores["rebalance_date"].unique()))
    strategy = pd.DataFrame(0.0, index=dates, columns=price_columns)
    baseline = pd.DataFrame(0.0, index=dates, columns=price_columns)

    for date, group in scores.groupby("rebalance_date"):
        valid = group.dropna(subset=["quality_score"])
        valid = valid[valid["ticker"].isin(price_columns)]
        names = valid["ticker"].drop_duplicates().tolist()
        if len(names) < minimum_names:
            continue
        baseline.loc[date, names] = 1.0 / len(names)

        keep_count = max(minimum_names, int(np.ceil(len(valid) * (1 - exclude_bottom_fraction))))
        selected = (
            valid.sort_values(["quality_score", "ticker"], ascending=[False, True])
            .drop_duplicates("ticker")
            .head(keep_count)["ticker"]
            .tolist()
        )
        strategy.loc[date, selected] = 1.0 / len(selected)
    return strategy, baseline


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
    factor_columns.append("quality_score")
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

    strategy_weights, baseline_weights = _portfolio_weights(
        scored_panel,
        available_tickers,
        float(config["exclude_bottom_fraction"]),
        int(config["minimum_names"]),
    )
    strategy_weights = strategy_weights.reindex(monthly_prices.index).fillna(0.0)
    baseline_weights = baseline_weights.reindex(monthly_prices.index).fillna(0.0)

    strategy, strategy_gross, strategy_cost, strategy_turnover = _returns_with_costs(
        strategy_weights, asset_returns, float(config["transaction_cost_bps"])
    )
    baseline, _, baseline_cost, baseline_turnover = _returns_with_costs(
        baseline_weights, asset_returns, float(config["transaction_cost_bps"])
    )
    benchmark = monthly_prices[benchmark_ticker].pct_change(fill_method=None)

    performance = pd.DataFrame(
        {
            "strategy": strategy,
            "equal_weight": baseline,
            "benchmark": benchmark,
            "strategy_gross": strategy_gross,
            "strategy_cost": strategy_cost,
            "strategy_turnover": strategy_turnover,
            "baseline_cost": baseline_cost,
            "baseline_turnover": baseline_turnover,
            "holdings": strategy_weights.shift(1).gt(0).sum(axis=1),
        }
    )
    first_valid = performance["strategy"].first_valid_index()
    if first_valid is not None:
        performance = performance.loc[first_valid:]

    metric_rows: list[dict] = []
    for label, returns, turnover in (
        ("strategy", performance["strategy"], performance["strategy_turnover"]),
        ("equal_weight", performance["equal_weight"], performance["baseline_turnover"]),
        ("benchmark", performance["benchmark"], None),
    ):
        metric_rows.append({"period": "full", "portfolio": label, **performance_metrics(
            returns, int(config["annualization_periods"]), turnover
        )})

    oos_start = pd.Timestamp(config["out_of_sample_start"])
    oos = performance.loc[performance.index >= oos_start]
    for label, returns, turnover in (
        ("strategy", oos["strategy"], oos["strategy_turnover"]),
        ("equal_weight", oos["equal_weight"], oos["baseline_turnover"]),
        ("benchmark", oos["benchmark"], None),
    ):
        metric_rows.append({"period": "out_of_sample", "portfolio": label, **performance_metrics(
            returns, int(config["annualization_periods"]), turnover
        )})
    metrics = pd.DataFrame(metric_rows)

    factor_ic = _factor_rank_ic(scored_panel, asset_returns)
    yearly_returns = (
        performance[["strategy", "equal_weight", "benchmark"]]
        .groupby(performance.index.year)
        .apply(lambda frame: (1 + frame).prod(min_count=1) - 1, include_groups=False)
    )
    yearly_returns.index.name = "year"
    return BacktestResult(
        performance=performance,
        weights=strategy_weights,
        baseline_weights=baseline_weights,
        metrics=metrics,
        factor_ic=factor_ic,
        yearly_returns=yearly_returns,
    )
