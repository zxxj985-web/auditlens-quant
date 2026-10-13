from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from auditlens.backtest import BacktestResult
from auditlens.utils import PROJECT_ROOT


COLORS = {
    "strategy": "#0B5CAD",
    "equal_weight": "#7A7A7A",
    "benchmark": "#D97706",
}


def _save_figure(fig: plt.Figure, name: str) -> Path:
    path = PROJECT_ROOT / "outputs/figures" / name
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def create_figures(result: BacktestResult, scored_panel: pd.DataFrame) -> list[Path]:
    performance = result.performance
    returns = performance[["strategy", "equal_weight", "benchmark"]].dropna(how="all")
    wealth = (1 + returns.fillna(0)).cumprod()

    fig, ax = plt.subplots(figsize=(9, 5))
    for column in wealth:
        ax.plot(wealth.index, wealth[column], label=column, color=COLORS[column], linewidth=1.8)
    ax.set_title("Cumulative wealth (net of modeled costs)")
    ax.set_ylabel("Growth of 1.0")
    ax.grid(alpha=0.25)
    ax.legend()
    paths = [_save_figure(fig, "cumulative_returns.png")]

    drawdown = wealth / wealth.cummax() - 1
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for column in drawdown:
        ax.plot(drawdown.index, drawdown[column], label=column, color=COLORS[column], linewidth=1.5)
    ax.set_title("Drawdown")
    ax.set_ylabel("Drawdown")
    ax.grid(alpha=0.25)
    ax.legend()
    paths.append(_save_figure(fig, "drawdown.png"))

    rolling_mean = returns.rolling(12, min_periods=8).mean() * 12
    rolling_volatility = returns.rolling(12, min_periods=8).std(ddof=1) * np.sqrt(12)
    rolling_sharpe = rolling_mean / rolling_volatility
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for column in rolling_sharpe:
        ax.plot(
            rolling_sharpe.index,
            rolling_sharpe[column],
            label=column,
            color=COLORS[column],
            linewidth=1.4,
        )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Rolling 12-month Sharpe ratio (risk-free rate = 0)")
    ax.grid(alpha=0.25)
    ax.legend()
    paths.append(_save_figure(fig, "rolling_sharpe.png"))

    coverage = scored_panel.groupby("rebalance_date")["quality_score"].count()
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(coverage.index, coverage.values, color="#198754", linewidth=1.8)
    ax.set_title("Number of companies with a valid quality score")
    ax.set_ylabel("Companies")
    ax.grid(alpha=0.25)
    paths.append(_save_figure(fig, "factor_coverage.png"))

    if not result.factor_ic.empty:
        summary = (
            result.factor_ic.groupby("factor")["rank_ic"]
            .agg(["mean", "count"])
            .sort_values("mean")
        )
        fig, ax = plt.subplots(figsize=(8, 5))
        colors = ["#B91C1C" if value < 0 else "#0B5CAD" for value in summary["mean"]]
        ax.barh(summary.index, summary["mean"], color=colors)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title("Mean monthly cross-sectional Rank IC")
        ax.set_xlabel("Rank IC")
        ax.grid(axis="x", alpha=0.25)
        paths.append(_save_figure(fig, "factor_rank_ic.png"))
    return paths


def _format_percent(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:.2%}"


def _format_number(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:.3f}"


def write_markdown_report(
    result: BacktestResult,
    scored_panel: pd.DataFrame,
    fundamentals: pd.DataFrame,
    config: dict,
) -> Path:
    metrics = result.metrics.copy()
    full = metrics[metrics["period"] == "full"].set_index("portfolio")
    oos = metrics[metrics["period"] == "out_of_sample"].set_index("portfolio")
    source_counts = fundamentals["publication_date_source"].value_counts()
    reported_count = int(source_counts.get("reported_earnings_date", 0))
    fallback_count = int(source_counts.get("conservative_lag", 0))
    total_reports = reported_count + fallback_count
    reported_share = reported_count / total_reports if total_reports else np.nan

    def metric_table(frame: pd.DataFrame) -> str:
        rows = [
            "| 组合 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | Calmar | 月胜率 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for name in ("strategy", "equal_weight", "benchmark"):
            if name not in frame.index:
                continue
            row = frame.loc[name]
            rows.append(
                f"| {name} | {_format_percent(row['annualized_return'])} | "
                f"{_format_percent(row['annualized_volatility'])} | {_format_number(row['sharpe'])} | "
                f"{_format_percent(row['max_drawdown'])} | {_format_number(row['calmar'])} | "
                f"{_format_percent(row['monthly_win_rate'])} |"
            )
        return "\n".join(rows)

    ic_summary = (
        result.factor_ic.groupby("factor")["rank_ic"].agg(["mean", "count"]).sort_values("mean", ascending=False)
        if not result.factor_ic.empty
        else pd.DataFrame()
    )
    ic_rows = ["| 因子 | 平均 Rank IC | 有效月份 |", "|---|---:|---:|"]
    for factor, row in ic_summary.iterrows():
        ic_rows.append(f"| {factor} | {_format_number(row['mean'])} | {int(row['count'])} |")

    start = result.performance.index.min().date() if not result.performance.empty else "—"
    end = result.performance.index.max().date() if not result.performance.empty else "—"
    coverage = scored_panel.groupby("rebalance_date")["quality_score"].count()
    report = f"""# AuditLens Quant 回测报告

> 本报告由代码自动生成。结果属于历史研究，不构成投资建议，也不代表未来收益。

## 摘要

- 回测区间：{start} 至 {end}
- 股票池：大型非金融 A 股静态演示股票池；市场基准使用沪深 300 ETF 代理
- 策略：排除财务质量—信用风险评分最低的 {config['backtest']['exclude_bottom_fraction']:.0%}，其余等权
- 交易成本：单边换手 {config['backtest']['transaction_cost_bps']} bps
- 样本外起点：{config['backtest']['out_of_sample_start']}
- 月均有效评分公司数：{coverage.mean():.1f}
- 财报发布日期直接匹配占比：{_format_percent(reported_share)}；其余使用保守滞后规则

## 全区间表现

{metric_table(full)}

## 样本外表现

{metric_table(oos)}

## 因子与下一月收益的横截面相关

{chr(10).join(ic_rows)}

Rank IC 为横截面秩相关，只描述历史关系；数值接近零或为负都属于有效研究结果，不应筛选或隐藏。

## 图表

![累计净值](../../outputs/figures/cumulative_returns.png)

![回撤](../../outputs/figures/drawdown.png)

![滚动 Sharpe](../../outputs/figures/rolling_sharpe.png)

![因子覆盖](../../outputs/figures/factor_coverage.png)

![因子 Rank IC](../../outputs/figures/factor_rank_ic.png)

## 主要限制

1. 股票池为静态演示样本，存在幸存者偏差，不能把结果视为完整市场回测。
2. 免费数据源可能回填或修订历史报表；报告保留发布日期来源以便审计。
3. 使用年度报表，信号更新频率较低；月度调仓主要用于价格和组合层面的风险管理。
4. 当前只建模线性交易成本，未完整模拟涨跌停、停牌和大额冲击成本。
5. 银行和保险未纳入首版，后续需要专门的资本充足率与资产质量因子体系。

## 可复现性

运行 `python -m auditlens all --force` 可重新下载公开数据并生成表格、图表和本报告。原始数据不提交到公开仓库，以遵守数据提供方条款并避免把回填后的快照误认为固定研究样本。
"""
    path = PROJECT_ROOT / "reports/generated/AuditLens_Quant_Report.md"
    path.write_text(report, encoding="utf-8")
    return path
