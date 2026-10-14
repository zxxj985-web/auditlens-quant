from __future__ import annotations

import numpy as np
import pandas as pd


FACTOR_COLUMNS = [
    "cfo_to_net_income",
    "accrual_quality",
    "free_cash_flow_to_assets",
    "net_margin",
    "low_leverage",
    "interest_coverage",
    "cash_to_debt",
    "receivables_efficiency",
    "inventory_efficiency",
]

IMPROVEMENT_FACTORS = {
    "cfo_to_net_income": "cfo_to_net_income_change",
    "accrual_quality": "accrual_quality_change",
    "free_cash_flow_to_assets": "free_cash_flow_to_assets_change",
    "net_margin": "net_margin_change",
    "low_leverage": "low_leverage_change",
    "interest_coverage": "interest_coverage_change",
    "cash_to_debt": "cash_to_debt_change",
    "receivables_efficiency": "receivables_efficiency_change",
    "inventory_efficiency": "inventory_efficiency_change",
}

MARKET_FACTOR_COLUMNS = [
    "momentum_6_1",
    "trend_10m",
    "low_volatility_6m",
    "earnings_yield",
    "free_cash_flow_yield",
    "book_to_price",
]


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.where(denominator.abs() > 1e-12)
    return numerator / denominator


def build_fundamental_factors(fundamentals: pd.DataFrame) -> pd.DataFrame:
    frame = fundamentals.copy()
    frame["stat_date"] = pd.to_datetime(frame["stat_date"])
    frame["publication_date"] = pd.to_datetime(frame["publication_date"])
    frame = frame.sort_values(["ticker", "stat_date"])

    previous_assets = frame.groupby("ticker")["total_assets"].shift(1)
    average_assets = (frame["total_assets"] + previous_assets) / 2
    average_assets = average_assets.fillna(frame["total_assets"])

    frame["cfo_to_net_income"] = _safe_divide(
        frame["operating_cash_flow"], frame["net_income"].abs()
    )
    frame["accrual_quality"] = -_safe_divide(
        frame["net_income"] - frame["operating_cash_flow"], average_assets
    )
    frame["free_cash_flow_to_assets"] = _safe_divide(frame["free_cash_flow"], average_assets)
    frame["net_margin"] = _safe_divide(frame["net_income"], frame["revenue"])
    frame["low_leverage"] = -_safe_divide(frame["total_liabilities"], frame["total_assets"])
    frame["interest_coverage"] = _safe_divide(frame["ebit"], frame["interest_expense"].abs())
    frame["cash_to_debt"] = _safe_divide(frame["cash"], frame["total_debt"])
    frame["receivables_efficiency"] = -_safe_divide(
        frame["accounts_receivable"], frame["revenue"]
    )
    frame["inventory_efficiency"] = -_safe_divide(frame["inventory"], frame["revenue"])

    if "common_equity" not in frame:
        frame["common_equity"] = frame["total_assets"] - frame["total_liabilities"]
    else:
        frame["common_equity"] = frame["common_equity"].fillna(
            frame["total_assets"] - frame["total_liabilities"]
        )

    frame[FACTOR_COLUMNS] = frame[FACTOR_COLUMNS].replace([np.inf, -np.inf], np.nan)
    for source, output in IMPROVEMENT_FACTORS.items():
        frame[output] = frame.groupby("ticker", sort=False)[source].diff()
    improvement_columns = list(IMPROVEMENT_FACTORS.values())
    frame[improvement_columns] = frame[improvement_columns].replace([np.inf, -np.inf], np.nan)
    return frame


def add_market_factors(
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    market_config: dict,
) -> pd.DataFrame:
    """Attach point-in-time price, momentum, risk, and valuation features.

    All price features are observed at the rebalance month-end. Portfolio weights
    are shifted by one month in the backtest, so these values cannot affect the
    return of the month in which they are measured.
    """

    frequency = str(market_config.get("rebalance_frequency", "ME"))
    monthly_prices = prices.sort_index().resample(frequency).last()
    monthly_returns = monthly_prices.pct_change(fill_method=None)

    momentum_months = int(market_config.get("momentum_months", 6))
    skip_months = int(market_config.get("momentum_skip_months", 1))
    trend_months = int(market_config.get("trend_months", 10))
    volatility_months = int(market_config.get("volatility_months", 6))

    momentum = (
        monthly_prices.shift(skip_months)
        / monthly_prices.shift(momentum_months + skip_months)
        - 1
    )
    trend = monthly_prices / monthly_prices.rolling(
        trend_months, min_periods=trend_months
    ).mean() - 1
    low_volatility = -monthly_returns.rolling(
        volatility_months, min_periods=volatility_months
    ).std(ddof=1) * np.sqrt(12)

    def to_long(frame: pd.DataFrame, name: str) -> pd.Series:
        series = frame.rename_axis(index="rebalance_date", columns="ticker").stack(
            future_stack=True
        )
        return series.rename(name)

    market = pd.concat(
        [
            to_long(monthly_prices, "month_end_price"),
            to_long(momentum, "momentum_6_1"),
            to_long(trend, "trend_10m"),
            to_long(low_volatility, "low_volatility_6m"),
        ],
        axis=1,
    ).reset_index()

    enriched = panel.merge(market, on=["rebalance_date", "ticker"], how="left")
    shares_source = (
        enriched["shares_outstanding"]
        if "shares_outstanding" in enriched
        else pd.Series(np.nan, index=enriched.index)
    )
    shares = pd.to_numeric(shares_source, errors="coerce")
    price = pd.to_numeric(enriched["month_end_price"], errors="coerce")
    market_cap = shares * price
    market_cap = market_cap.where((shares > 0) & (price > 0))
    enriched["market_cap"] = market_cap
    enriched["earnings_yield"] = _safe_divide(enriched["net_income"], market_cap)
    enriched["free_cash_flow_yield"] = _safe_divide(enriched["free_cash_flow"], market_cap)
    enriched["book_to_price"] = _safe_divide(enriched["common_equity"], market_cap)
    enriched[MARKET_FACTOR_COLUMNS] = enriched[MARKET_FACTOR_COLUMNS].replace(
        [np.inf, -np.inf], np.nan
    )
    return enriched


def monthly_rebalance_dates(prices: pd.DataFrame, frequency: str = "ME") -> pd.DatetimeIndex:
    return prices.sort_index().resample(frequency).last().index


def align_factors_point_in_time(
    factors: pd.DataFrame,
    rebalance_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    aligned: list[pd.DataFrame] = []
    normalized_dates = pd.DatetimeIndex(rebalance_dates).sort_values().astype("datetime64[ns]")
    left_template = pd.DataFrame({"rebalance_date": normalized_dates})

    for ticker, group in factors.groupby("ticker", sort=True):
        right = group.copy()
        right["publication_date"] = pd.to_datetime(right["publication_date"]).astype("datetime64[ns]")
        right = right.sort_values(["publication_date", "stat_date"]).drop_duplicates(
            "publication_date", keep="last"
        )
        merged = pd.merge_asof(
            left_template,
            right,
            left_on="rebalance_date",
            right_on="publication_date",
            direction="backward",
            allow_exact_matches=True,
        )
        merged["ticker"] = ticker
        aligned.append(merged)

    panel = pd.concat(aligned, ignore_index=True)
    panel = panel.dropna(subset=["publication_date"]).reset_index(drop=True)
    if (panel["publication_date"] > panel["rebalance_date"]).any():
        raise AssertionError("Point-in-time violation: a report was used before publication.")
    return panel


def _winsorized_zscore(series: pd.Series, lower: float, upper: float) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if len(valid) < 2:
        return pd.Series(np.nan, index=series.index, dtype=float)
    low_value, high_value = valid.quantile([lower, upper])
    clipped = numeric.clip(low_value, high_value)
    scale = clipped.std(ddof=0)
    if pd.isna(scale) or scale < 1e-12:
        return pd.Series(np.nan, index=series.index, dtype=float)
    return (clipped - clipped.mean()) / scale


def score_cross_sections(panel: pd.DataFrame, factor_config: dict) -> pd.DataFrame:
    result_frames: list[pd.DataFrame] = []
    lower = float(factor_config["winsor_lower"])
    upper = float(factor_config["winsor_upper"])
    min_industry_size = int(factor_config["minimum_industry_size"])
    quality_weights = factor_config.get("quality_weights", factor_config.get("weights", {}))
    quality_weights = {key: float(value) for key, value in quality_weights.items()}
    alpha_weights = {
        key: float(value) for key, value in factor_config.get("alpha_weights", {}).items()
    }
    diagnostic_factors = list(factor_config.get("diagnostic_factors", []))
    all_factors = list(
        dict.fromkeys([*quality_weights, *alpha_weights, *diagnostic_factors])
    )

    def weighted_score(scored: pd.DataFrame, weights: dict[str, float]) -> tuple[pd.Series, pd.Series]:
        z_columns = [f"z_{factor}" for factor in weights]
        weight_series = pd.Series({f"z_{factor}": weight for factor, weight in weights.items()})
        available = scored[z_columns].notna()
        weighted_sum = scored[z_columns].mul(weight_series, axis=1).sum(axis=1, skipna=True)
        available_weight = available.mul(weight_series, axis=1).sum(axis=1)
        return weighted_sum / available_weight.replace(0, np.nan), available.sum(axis=1)

    for _, group in panel.groupby("rebalance_date", sort=True):
        scored = group.copy()
        for factor in all_factors:
            z = _winsorized_zscore(scored[factor], lower, upper)
            if factor_config.get("industry_neutral", True) and "industry" in scored:
                counts = scored.groupby("industry")[factor].transform("count")
                industry_mean = z.groupby(scored["industry"]).transform("mean")
                z = z.where(counts < min_industry_size, z - industry_mean)
                valid = z.dropna()
                if len(valid) >= 3 and valid.std(ddof=0) > 1e-12:
                    z = (z - valid.mean()) / valid.std(ddof=0)
            scored[f"z_{factor}"] = z

        scored["quality_score"], scored["quality_factor_count"] = weighted_score(
            scored, quality_weights
        )
        # Retain the original V1 field name for downstream compatibility.
        scored["factor_count"] = scored["quality_factor_count"]
        scored.loc[
            scored["quality_factor_count"]
            < int(
                factor_config.get(
                    "minimum_quality_factor_count",
                    factor_config.get("minimum_factor_count", 5),
                )
            ),
            "quality_score",
        ] = np.nan

        if alpha_weights:
            scored["alpha_score"], scored["alpha_factor_count"] = weighted_score(
                scored, alpha_weights
            )
            scored.loc[
                scored["alpha_factor_count"]
                < int(factor_config.get("minimum_alpha_factor_count", 9)),
                "alpha_score",
            ] = np.nan

            for component, factors in factor_config.get("components", {}).items():
                component_weights = {
                    factor: alpha_weights[factor]
                    for factor in factors
                    if factor in alpha_weights
                }
                if component_weights:
                    scored[f"{component}_score"], scored[f"{component}_factor_count"] = (
                        weighted_score(scored, component_weights)
                    )
        result_frames.append(scored)

    return pd.concat(result_frames, ignore_index=True).sort_values(
        ["rebalance_date", "ticker"]
    )
