import numpy as np
import pandas as pd

from auditlens.backtest import _portfolio_weights, _returns_with_costs, performance_metrics


def test_costs_reduce_gross_return_when_portfolio_changes():
    dates = pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31"])
    weights = pd.DataFrame({"A": [1.0, 0.0, 0.0], "B": [0.0, 1.0, 1.0]}, index=dates)
    returns = pd.DataFrame({"A": [0.0, 0.10, 0.0], "B": [0.0, 0.0, 0.10]}, index=dates)
    net, gross, costs, turnover = _returns_with_costs(weights, returns, cost_bps=10)
    assert costs.sum() > 0
    assert net.dropna().sum() < gross.dropna().sum()
    assert turnover.max() > 0


def test_performance_metrics_reports_drawdown():
    returns = pd.Series([0.10, -0.20, 0.05], index=pd.date_range("2024-01-31", periods=3, freq="ME"))
    metrics = performance_metrics(returns)
    assert metrics["max_drawdown"] < 0
    assert metrics["months"] == 3


def test_portfolio_selects_top_alpha_names_and_keeps_quality_filter_baseline():
    date = pd.Timestamp("2024-01-31")
    scores = pd.DataFrame(
        {
            "rebalance_date": [date] * 4,
            "ticker": ["A", "B", "C", "D"],
            "alpha_score": [1.0, 2.0, 3.0, 4.0],
            "quality_score": [4.0, 3.0, 2.0, 1.0],
        }
    )
    alpha, quality, baseline = _portfolio_weights(
        scores,
        ["A", "B", "C", "D"],
        score_column="alpha_score",
        selection_fraction=0.5,
        quality_filter_exclude_fraction=0.25,
        minimum_names=2,
    )
    assert set(alpha.columns[alpha.loc[date].gt(0)]) == {"C", "D"}
    assert set(quality.columns[quality.loc[date].gt(0)]) == {"A", "B", "C"}
    assert np.isclose(baseline.loc[date].sum(), 1.0)


def test_quality_filter_does_not_depend_on_alpha_score_availability():
    date = pd.Timestamp("2024-01-31")
    scores = pd.DataFrame(
        {
            "rebalance_date": [date] * 4,
            "ticker": ["A", "B", "C", "D"],
            "alpha_score": [1.0, 2.0, 3.0, np.nan],
            "quality_score": [4.0, 3.0, 2.0, 1.0],
        }
    )
    _, quality, _ = _portfolio_weights(
        scores,
        ["A", "B", "C", "D"],
        score_column="alpha_score",
        selection_fraction=0.5,
        quality_filter_exclude_fraction=0.25,
        minimum_names=2,
    )
    assert set(quality.columns[quality.loc[date].gt(0)]) == {"A", "B", "C"}
