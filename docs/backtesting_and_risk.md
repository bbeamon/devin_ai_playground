# Backtesting and risk analytics

## Execution model

`tradelab.backtest.Backtester` simulates a cash account bar by bar.

| Setting (`backtest:`) | Meaning |
|---|---|
| `execution: next_open` | Weights decided at close *t* fill at open *t+1* (default, no look-ahead) |
| `execution: close` | Fill at the same close that produced the signal — optimistic, use for comparison only |
| `slippage_bps` | Adverse price move per fill (buys pay up, sells receive less) |
| `commission_per_share`, `commission_pct`, `min_commission` | Commission per fill = max(min, per-share × qty + pct × notional) |
| `fractional_shares` | If false, quantities are floored to whole shares |
| `allow_short` | If false, negative target weights are clipped to 0 |
| `rebalance_threshold` | Skip trades when \|target − current weight\| is below this; full exits always trade |
| `initial_cash` | Starting equity |

Positions are re-sized towards the **target weight** of current equity on each
bar (subject to `rebalance_threshold`). With `rebalance_threshold: 0` a constant
weight means daily re-balancing, which matters for leveraged or short books.

`BacktestResult` exposes `equity`, `returns`, `positions`, `weights`,
`target_weights`, `trades`, `cash`, `signals`, `benchmark_returns` and
`metrics()`.

### Grid search

`tradelab.backtest.grid_search(cfg, {"fast": [10, 20], "slow": [50, 100]}, data=..., split_date=...)`
returns one row per combination with in-sample and (if `split_date`) out-of-sample
metrics. Invalid combinations (e.g. `fast >= slow`) are reported in an `error`
column rather than aborting. Prefer ranking by out-of-sample metrics to limit
overfitting.

## Metrics (`tradelab.risk.metrics`)

| Metric | Notes |
|---|---|
| Total return, CAGR | CAGR uses calendar years between first and last bar |
| Volatility | Annualised std of periodic returns (252 periods/year by default) |
| Sharpe, Sortino | Excess over `risk_free_rate`; Sortino uses downside deviation |
| Max drawdown, duration | Peak-to-trough on equity; duration in bars |
| Calmar | CAGR / \|max drawdown\| |
| VaR, CVaR | Historical, at the chosen confidence (reported as positive losses) |
| Beta, alpha, tracking error, information ratio, correlation | Versus the benchmark |
| Win rate, profit factor | On periodic returns |
| Turnover, exposure | From the weights matrix |
| Rolling volatility / Sharpe / beta, monthly returns table | Used by the Risk page |

## Pre-trade risk (`tradelab.risk.limits.PreTradeRiskChecker`)

Applied by the paper `Rebalancer` before any order: non-zero quantity, positive
price, `max_order_notional`, long-only (unless shorting is allowed),
`max_position_weight` of post-trade position, and positive account equity. The
rebalancer also caps the number of orders per run (`max_orders_per_run`) and
skips trades below `min_trade_notional`.

## Known simplifications

- Daily bars; no intraday fill modelling, partial fills, or market impact beyond fixed slippage.
- No borrow costs, short-locate constraints, dividends as cash (Yahoo data is
  split/dividend-adjusted), corporate-action edge cases, or margin interest.
- Survivorship bias: the universe is whatever you specify today.
