import pandas as pd

from auditlens.backtest import _returns_with_costs, performance_metrics


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
