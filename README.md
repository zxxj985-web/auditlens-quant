# AuditLens Alpha

AuditLens Alpha is a point-in-time A-share factor-research and portfolio-engineering project. It tests whether a focused combination of cash-flow quality, operating improvement, and defensive risk can improve a long-only equity portfolio after publication lags, turnover, and transaction costs.

The project is built as a reproducible research system rather than a personal-experience narrative. Its main purpose is to demonstrate factor design, time-series alignment, portfolio construction, validation discipline, testing, and honest failure analysis for future quantitative research or trading-development work.

## Research question

Can a compact, economically interpretable signal outperform a broad quality filter and an equal-weight universe without relying on future financial statements?

The current candidate signal combines:

- free-cash-flow yield;
- accrual quality and operating cash-flow conversion;
- year-over-year improvement in leverage, margin, and receivables efficiency;
- six-month low volatility.

Each month the strategy selects the highest-scoring 30% of eligible companies, subject to a six-name diversification floor, and holds them at equal weights during the following month.

## Current evidence

Data through 2026-09-30 produced 30 investable monthly observations from a static universe of 27 large non-financial A-share companies.

| Period | Portfolio | Annualized return | Sharpe | Maximum drawdown |
|---|---|---:|---:|---:|
| Full research sample | AuditLens Alpha | 16.05% | 0.865 | -9.76% |
| Full research sample | V1 quality filter | 5.40% | 0.276 | -10.83% |
| Full research sample | Eligible-universe equal weight | 6.56% | 0.347 | -10.31% |
| Full research sample | CSI 300 ETF proxy | 11.70% | 0.569 | -11.70% |
| 2026 validation window | AuditLens Alpha | 0.72% | 0.053 | -9.76% |
| 2026 validation window | V1 quality filter | -10.81% | -0.613 | -10.56% |
| 2026 validation window | Eligible-universe equal weight | -10.30% | -0.639 | -10.31% |
| 2026 validation window | CSI 300 ETF proxy | -5.73% | -0.341 | -11.70% |

The full-sample result is encouraging, but it is not proof of durable alpha. The factor family was refined after diagnostics, and the 2026 window informed model selection, so it is a validation window rather than an untouched test set. A locked walk-forward or live-forward test is still required.

![Cumulative wealth](outputs/figures/cumulative_returns.png)

## What changed from V1

V1 retained 80% of the universe after removing companies with the weakest static financial quality. It behaved primarily as a risk filter.

V2 makes four structural changes:

1. It targets a concentrated top-ranked portfolio rather than merely excluding the bottom tail.
2. It uses changes in fundamentals, not only their levels.
3. It adds point-in-time valuation using historical shares outstanding and month-end prices.
4. It treats unsuccessful candidates, including broad momentum and trend signals, as diagnostics instead of hiding them.

The V1 portfolio remains in every output as `quality_filter`, providing a direct baseline.

## Research controls

- Financial statements are aligned to reported earnings dates when available.
- A conservative 120-day lag is used when a publication date is unavailable.
- Month-end signals are applied only to the following month's return.
- Cross-sectional factors are winsorized, standardized, and industry-neutralized when possible.
- The model requires at least six of the seven production factors for eligibility.
- Portfolio selection uses the top 30%, with a minimum of six holdings.
- Results include 10 bps of modeled one-way turnover cost.
- Automated tests cover publication-date leakage, market-feature timing, factor directions, portfolio selection, costs, and drawdown.

## Quick start

```bash
python -m pip install -e ".[dev]"
python -m auditlens all --force
```

Reuse the local data cache:

```bash
python -m auditlens run
```

Run the test suite:

```bash
pytest
```

## Outputs

- `outputs/tables/performance_metrics.csv`: full-sample and validation metrics
- `outputs/tables/monthly_performance.csv`: Alpha, V1, equal-weight, and benchmark returns
- `outputs/tables/factor_rank_ic.csv`: monthly cross-sectional Rank IC for production and rejected factors
- `outputs/figures/`: cumulative wealth, drawdown, rolling Sharpe, coverage, and IC figures
- `reports/generated/AuditLens_Alpha_Report.md`: automatically generated Chinese report
- `data/processed/factor_panel.parquet`: local point-in-time research panel, excluded from Git

Downloaded raw and processed data remain outside version control. Derived tables, figures, and the generated report are committed so the published claims can be inspected.

## Structure

```text
auditlens-quant/
├── configs/              # Universe, factors, and portfolio settings
├── data/                 # Local raw and processed data; ignored by Git
├── docs/                 # Research design, data dictionary, presentation guide
├── notebooks/            # Evidence-oriented walkthrough
├── outputs/              # Versioned summary tables and figures
├── reports/generated/    # Versioned generated report
├── src/auditlens/        # Data, features, portfolio, and reporting code
└── tests/                # Leakage, timing, selection, and cost tests
```

## Important limitations

- The universe is static and subject to survivorship bias.
- The research period is short because free statement history is limited.
- Yahoo Finance may revise historical statement fields.
- The 2026 window is not a pristine holdout because it informed candidate selection.
- The execution model does not simulate limit-up/limit-down, suspensions, taxes, or market impact in full.
- Banks and insurers require a separate factor definition and are excluded.
- This is educational research, not investment advice.

See [`docs/research_design.md`](docs/research_design.md) for formulas and the validation roadmap, and [`docs/research_presentation.md`](docs/research_presentation.md) for a research-focused presentation guide.
