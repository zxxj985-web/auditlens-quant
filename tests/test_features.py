import numpy as np
import pandas as pd

from auditlens.features import (
    add_market_factors,
    align_factors_point_in_time,
    build_fundamental_factors,
    score_cross_sections,
)


def test_point_in_time_alignment_never_uses_future_report():
    factors = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "company": ["A", "A"],
            "industry": ["Tech", "Tech"],
            "stat_date": pd.to_datetime(["2022-12-31", "2023-12-31"]),
            "publication_date": pd.to_datetime(["2023-04-10", "2024-04-15"]),
            "quality_score": [1.0, 2.0],
        }
    )
    dates = pd.to_datetime(["2023-03-31", "2023-04-30", "2024-03-31", "2024-04-30"])
    aligned = align_factors_point_in_time(factors, dates)
    assert (aligned["publication_date"] <= aligned["rebalance_date"]).all()
    april_2023 = aligned.loc[aligned["rebalance_date"] == pd.Timestamp("2023-04-30")].iloc[0]
    march_2024 = aligned.loc[aligned["rebalance_date"] == pd.Timestamp("2024-03-31")].iloc[0]
    april_2024 = aligned.loc[aligned["rebalance_date"] == pd.Timestamp("2024-04-30")].iloc[0]
    assert april_2023["stat_date"] == pd.Timestamp("2022-12-31")
    assert march_2024["stat_date"] == pd.Timestamp("2022-12-31")
    assert april_2024["stat_date"] == pd.Timestamp("2023-12-31")


def test_factor_directions_reward_cash_flow_and_low_leverage():
    frame = pd.DataFrame(
        {
            "ticker": ["GOOD", "RISKY"],
            "company": ["Good", "Risky"],
            "industry": ["Industrial", "Industrial"],
            "stat_date": pd.to_datetime(["2023-12-31", "2023-12-31"]),
            "publication_date": pd.to_datetime(["2024-04-01", "2024-04-01"]),
            "publication_date_source": ["reported_earnings_date"] * 2,
            "revenue": [100.0, 100.0],
            "net_income": [10.0, 10.0],
            "ebit": [15.0, 8.0],
            "interest_expense": [1.0, 4.0],
            "gross_profit": [40.0, 20.0],
            "total_assets": [100.0, 100.0],
            "total_liabilities": [20.0, 80.0],
            "current_assets": [60.0, 20.0],
            "current_liabilities": [20.0, 40.0],
            "cash": [30.0, 2.0],
            "total_debt": [10.0, 60.0],
            "accounts_receivable": [5.0, 30.0],
            "inventory": [5.0, 35.0],
            "operating_cash_flow": [14.0, 2.0],
            "free_cash_flow": [12.0, -3.0],
        }
    )
    factors = build_fundamental_factors(frame).set_index("ticker")
    assert factors.loc["GOOD", "cfo_to_net_income"] > factors.loc["RISKY", "cfo_to_net_income"]
    assert factors.loc["GOOD", "low_leverage"] > factors.loc["RISKY", "low_leverage"]
    assert factors.loc["GOOD", "receivables_efficiency"] > factors.loc["RISKY", "receivables_efficiency"]


def test_score_requires_minimum_number_of_factors():
    panel = pd.DataFrame(
        {
            "rebalance_date": pd.to_datetime(["2024-04-30"] * 3),
            "ticker": ["A", "B", "C"],
            "industry": ["One", "One", "One"],
            "factor_a": [1.0, 2.0, np.nan],
            "factor_b": [2.0, 1.0, np.nan],
        }
    )
    config = {
        "winsor_lower": 0.0,
        "winsor_upper": 1.0,
        "minimum_factor_count": 2,
        "industry_neutral": False,
        "minimum_industry_size": 3,
        "weights": {"factor_a": 0.5, "factor_b": 0.5},
    }
    scored = score_cross_sections(panel, config).set_index("ticker")
    assert pd.notna(scored.loc["A", "quality_score"])
    assert pd.isna(scored.loc["C", "quality_score"])


def test_improvement_factors_reward_better_cash_conversion_and_lower_leverage():
    frame = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA"],
            "company": ["A", "A"],
            "industry": ["One", "One"],
            "stat_date": pd.to_datetime(["2023-12-31", "2024-12-31"]),
            "publication_date": pd.to_datetime(["2024-04-01", "2025-04-01"]),
            "publication_date_source": ["reported_earnings_date"] * 2,
            "revenue": [100.0, 120.0],
            "net_income": [10.0, 12.0],
            "ebit": [14.0, 18.0],
            "interest_expense": [2.0, 2.0],
            "gross_profit": [30.0, 38.0],
            "total_assets": [100.0, 110.0],
            "total_liabilities": [60.0, 50.0],
            "current_assets": [45.0, 55.0],
            "current_liabilities": [30.0, 25.0],
            "cash": [12.0, 20.0],
            "total_debt": [40.0, 30.0],
            "accounts_receivable": [20.0, 18.0],
            "inventory": [15.0, 14.0],
            "operating_cash_flow": [8.0, 15.0],
            "free_cash_flow": [5.0, 11.0],
            "shares_outstanding": [10.0, 10.0],
            "common_equity": [40.0, 60.0],
        }
    )
    factors = build_fundamental_factors(frame).sort_values("stat_date")
    latest = factors.iloc[-1]
    assert latest["cfo_to_net_income_change"] > 0
    assert latest["low_leverage_change"] > 0
    assert latest["receivables_efficiency_change"] > 0


def test_market_factors_use_only_prices_available_at_rebalance_date():
    dates = pd.date_range("2024-01-31", periods=9, freq="ME")
    prices = pd.DataFrame({"AAA": np.arange(10.0, 19.0)}, index=dates)
    panel = pd.DataFrame(
        {
            "rebalance_date": [dates[7]],
            "ticker": ["AAA"],
            "net_income": [2.0],
            "free_cash_flow": [3.0],
            "common_equity": [20.0],
            "shares_outstanding": [2.0],
        }
    )
    config = {
        "rebalance_frequency": "ME",
        "momentum_months": 6,
        "momentum_skip_months": 1,
        "trend_months": 3,
        "volatility_months": 3,
    }
    original = add_market_factors(panel, prices, config).iloc[0]
    changed_future = prices.copy()
    changed_future.loc[dates[8], "AAA"] = 10_000.0
    rerun = add_market_factors(panel, changed_future, config).iloc[0]
    assert np.isclose(original["momentum_6_1"], prices.loc[dates[6], "AAA"] / prices.loc[dates[0], "AAA"] - 1)
    assert np.isclose(original["market_cap"], prices.loc[dates[7], "AAA"] * 2.0)
    assert np.isclose(original["momentum_6_1"], rerun["momentum_6_1"])
    assert np.isclose(original["trend_10m"], rerun["trend_10m"])
