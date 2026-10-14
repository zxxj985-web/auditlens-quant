# Data dictionary

## Identifiers and dates

| Field | Meaning |
|---|---|
| `ticker` | Yahoo Finance A-share symbol, such as `600519.SS` |
| `company` | Company name used for reporting |
| `industry` | Coarse project-specific industry group |
| `stat_date` | Financial statement period end |
| `publication_date` | Date on which the report is treated as publicly available |
| `publication_date_source` | `reported_earnings_date` or `conservative_lag` |
| `rebalance_date` | Calendar month-end signal timestamp |
| `return_date` | Month-end associated with the next holding-period return |

## Raw statement values

Currency values use the units returned by the data provider. Ratios are therefore unit invariant.

| Field | Statement concept |
|---|---|
| `revenue` | Total revenue |
| `net_income` | Net income |
| `ebit` | Earnings before interest and tax |
| `interest_expense` | Interest expense |
| `total_assets` | Total assets |
| `total_liabilities` | Total liabilities |
| `common_equity` | Equity attributable to common shareholders when available |
| `cash` | Cash, equivalents, and short-term investments when available |
| `total_debt` | Interest-bearing total debt |
| `accounts_receivable` | Accounts receivable |
| `inventory` | Inventory |
| `operating_cash_flow` | Cash flow from operations |
| `free_cash_flow` | Provider-calculated free cash flow |
| `shares_outstanding` | Period-end ordinary shares outstanding |

## Accounting factors

Every transformed factor follows the convention “higher is better.” A suffix of `_change` means the year-over-year improvement in the corresponding level factor.

| Factor | Definition |
|---|---|
| `cfo_to_net_income` | Operating cash flow divided by absolute net income |
| `accrual_quality` | Negative accruals divided by average assets |
| `free_cash_flow_to_assets` | Free cash flow divided by average assets |
| `net_margin` | Net income divided by revenue |
| `low_leverage` | Negative liabilities-to-assets ratio |
| `interest_coverage` | EBIT divided by absolute interest expense |
| `cash_to_debt` | Cash and short-term investments divided by total debt |
| `receivables_efficiency` | Negative receivables-to-revenue ratio |
| `inventory_efficiency` | Negative inventory-to-revenue ratio |
| `low_leverage_change` | Year-over-year improvement in low leverage |
| `net_margin_change` | Year-over-year improvement in net margin |
| `receivables_efficiency_change` | Year-over-year improvement in receivables efficiency |

The pipeline also calculates `_change` versions of the other accounting factors for diagnostics, even when they are not used by the production score.

## Market and valuation factors

| Factor | Definition |
|---|---|
| `momentum_6_1` | Six-month price momentum excluding the most recent month |
| `trend_10m` | Price divided by its trailing ten-month moving average, minus one |
| `low_volatility_6m` | Negative trailing six-month standard deviation of monthly returns |
| `market_cap` | Point-in-time adjusted price multiplied by shares outstanding |
| `earnings_yield` | Net income divided by point-in-time market capitalisation |
| `free_cash_flow_yield` | Free cash flow divided by point-in-time market capitalisation |
| `book_to_price` | Common equity divided by point-in-time market capitalisation |

Adjusted historical prices and period-end share counts are an approximation. A production-grade implementation should reconstruct split-consistent shares and use a dedicated point-in-time market-cap source.

## Scores

Within each rebalance month, raw factors are winsorised, standardised and, where the industry sample is large enough, industry neutralised.

| Field | Meaning |
|---|---|
| `z_<factor>` | Cross-sectional z-score of a factor |
| `quality_score` | V1 availability-adjusted weighted accounting-quality score |
| `alpha_score` | V2 availability-adjusted weighted production score |
| `quality_factor_count` | Number of valid V1 inputs for a row |
| `factor_count` | Backward-compatible alias of `quality_factor_count` |
| `alpha_factor_count` | Number of valid V2 inputs for a row |
| `cashflow_quality_score` | Equal-weight diagnostic component score |
| `operating_improvement_score` | Equal-weight diagnostic component score |
| `defensive_risk_score` | Low-volatility diagnostic component score |

The V2 production score uses free-cash-flow yield, accrual quality, CFO-to-net-income, leverage improvement, margin improvement, receivables-efficiency improvement and six-month low volatility. Exact weights live in `configs/base.yaml`.

## Portfolio outputs

| Field | Meaning |
|---|---|
| `alpha_strategy` | Net return of the top-ranked V2 portfolio after modeled turnover cost |
| `quality_filter` | Net return of the V1 quality-filter portfolio |
| `equal_weight` | Net return of all eligible scored companies |
| `benchmark` | Return of the CSI 300 ETF proxy |
| `<portfolio>_gross` | Portfolio return before modeled cost |
| `<portfolio>_cost` | Monthly turnover cost deduction |
| `<portfolio>_turnover` | One-way monthly portfolio turnover |
| `<portfolio>_holdings` | Number of names held during the return month |

## Evaluation fields

| Field | Meaning |
|---|---|
| `period` | `full` or `validation` evaluation window |
| `annualized_return` | Compounded monthly return annualised to 12 periods |
| `annualized_volatility` | Monthly return standard deviation multiplied by square root of 12 |
| `sharpe` | Annualised return divided by annualised volatility; risk-free rate assumed zero |
| `max_drawdown` | Worst peak-to-trough decline in cumulative wealth |
| `rank_ic` | Monthly Spearman rank correlation between a signal and next-month stock returns |
