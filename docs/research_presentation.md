# Research presentation guide

AuditLens Alpha should be presented as evidence of quantitative research and software-engineering ability. It does not need an artificial link to previous internships.

## 30-second version

AuditLens Alpha is a reproducible A-share multi-factor research system. It combines point-in-time financial-statement signals, fundamental improvement, valuation and market-risk features; forms monthly portfolios; applies turnover costs; and compares a new alpha candidate with the first-version quality filter, an equal-weight universe and a market proxy. The emphasis is not one attractive backtest number, but the research controls: publication-date alignment, explicit baselines, rejected-factor diagnostics and honest validation limits.

## Two-minute research walkthrough

1. **Question** — Can a compact and interpretable set of cash-flow, improvement, valuation and defensive factors improve a long-only A-share portfolio after trading costs?
2. **Information timing** — A statement is unavailable until its publication date. Month-end signals are matched only to already-public information and are applied to the following month's return.
3. **Signal design** — The production score combines free-cash-flow yield, accrual quality, cash conversion, leverage improvement, margin improvement, receivables improvement and low volatility.
4. **Portfolio construction** — The candidate holds the top 30% of valid names at equal weight, with a six-name minimum for diversification. It is compared with the V1 quality filter, the same-universe equal-weight portfolio and a CSI 300 ETF proxy.
5. **Research discipline** — Momentum, trend and other plausible factors remain visible in diagnostics even when their historical Rank IC is weak or negative. This prevents the final report from hiding rejected ideas.
6. **Interpretation** — The current full-sample result is encouraging, but the 2026 period influenced model selection and is too short to qualify as a pristine test. The next credible step is a frozen live or walk-forward evaluation with historical constituent data.

## What this project demonstrates

- Python package design, configuration-driven research and automated tests.
- Point-in-time joins and explicit prevention of future-information leakage.
- Cross-sectional signal engineering, portfolio construction and transaction-cost modeling.
- Benchmarking, factor Rank IC diagnostics and evidence-based rejection of hypotheses.
- Clear separation between an exploratory result and a defensible out-of-sample claim.

## Suitable applications

- Quantitative finance, financial engineering or data-science master's applications.
- Quant research, systematic-investing and portfolio-analytics internships.
- Trading-development roles where reproducibility, data pipelines and testing matter.

## Honest result statement

Use the latest numbers from `outputs/tables/performance_metrics.csv`. Describe the full-sample result as a **candidate strategy result**, not proof of persistent alpha. Describe the 2026 block as a **stability check**, not a clean untouched test, because it informed factor selection.

## Recommended next experiment

Freeze V2 without further weight changes, add historical index constituents and more rebalance dates, and evaluate it through rolling train/validation windows or forward paper trading. Predefine the acceptance rule before observing those returns.
