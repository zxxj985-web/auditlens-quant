# Data dictionary

## Identifiers and dates

| Field | Meaning |
|---|---|
| `ticker` | Yahoo Finance A-share symbol, such as `600519.SS` |
| `company` | Chinese company name used for reporting |
| `industry` | Coarse project-specific industry group |
| `stat_date` | Financial statement period end |
| `publication_date` | Date on which the report is treated as publicly available |
| `publication_date_source` | `reported_earnings_date` or `conservative_lag` |
| `rebalance_date` | Calendar month-end signal timestamp |

## Raw statement values

All currency values use the units returned by the data provider. Ratios are therefore unit invariant.

| Field | Statement concept |
|---|---|
| `revenue` | Total revenue |
| `net_income` | Net income |
| `ebit` | Earnings before interest and tax |
| `interest_expense` | Interest expense |
| `total_assets` | Total assets |
| `total_liabilities` | Total liabilities |
| `cash` | Cash, equivalents, and short-term investments when available |
| `total_debt` | Interest-bearing total debt |
| `accounts_receivable` | Accounts receivable |
| `inventory` | Inventory |
| `operating_cash_flow` | Cash flow from operations |
| `free_cash_flow` | Provider-calculated free cash flow |

## Derived factors

All transformed factors use the convention “higher is better.”

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
| `quality_score` | Availability-adjusted weighted mean of cross-sectional factor z-scores |

## Portfolio outputs

| Field | Meaning |
|---|---|
| `strategy` | Net monthly return after modeled turnover cost |
| `equal_weight` | Net return of all eligible scored companies |
| `benchmark` | Return of the CSI 300 ETF proxy |
| `strategy_gross` | Strategy return before modeled cost |
| `strategy_cost` | Monthly turnover cost deduction |
| `strategy_turnover` | One-way monthly portfolio turnover |
| `holdings` | Number of names held during the return month |
