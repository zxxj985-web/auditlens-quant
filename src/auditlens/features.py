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
    frame[FACTOR_COLUMNS] = frame[FACTOR_COLUMNS].replace([np.inf, -np.inf], np.nan)
    return frame


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
    weights = {key: float(value) for key, value in factor_config["weights"].items()}

    for _, group in panel.groupby("rebalance_date", sort=True):
        scored = group.copy()
        for factor in weights:
            z = _winsorized_zscore(scored[factor], lower, upper)
            if factor_config.get("industry_neutral", True) and "industry" in scored:
                counts = scored.groupby("industry")[factor].transform("count")
                industry_mean = z.groupby(scored["industry"]).transform("mean")
                z = z.where(counts < min_industry_size, z - industry_mean)
                valid = z.dropna()
                if len(valid) >= 3 and valid.std(ddof=0) > 1e-12:
                    z = (z - valid.mean()) / valid.std(ddof=0)
            scored[f"z_{factor}"] = z

        z_columns = [f"z_{factor}" for factor in weights]
        weight_series = pd.Series({f"z_{factor}": weight for factor, weight in weights.items()})
        available = scored[z_columns].notna()
        weighted_sum = scored[z_columns].mul(weight_series, axis=1).sum(axis=1, skipna=True)
        available_weight = available.mul(weight_series, axis=1).sum(axis=1)
        scored["factor_count"] = available.sum(axis=1)
        scored["quality_score"] = weighted_sum / available_weight.replace(0, np.nan)
        scored.loc[
            scored["factor_count"] < int(factor_config["minimum_factor_count"]),
            "quality_score",
        ] = np.nan
        result_frames.append(scored)

    return pd.concat(result_frames, ignore_index=True).sort_values(
        ["rebalance_date", "ticker"]
    )
