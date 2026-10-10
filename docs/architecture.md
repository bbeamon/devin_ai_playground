# Architecture

```
            ┌────────────── Streamlit UI (app/) ──────────────┐
            │ Data Explorer │ Backtest │ Risk │ Optimizer │ Paper │
            └───────┬───────────┬──────────┬────────────┬──────┘
                    │           │          │            │
   tradelab.data ◄──┘   tradelab.backtest  │     tradelab.execution
   (providers,          (runner, engine,   │      (Rebalancer)
    cache, validate)     costs)            │            │
          │                 │              │            ▼
          ▼                 ▼              │     tradelab.brokers
   tradelab.strategies ──► target weights  │     (Broker ABC → simulated,
   (indicators, registry,  (StrategyEngine)│      alpaca_paper, stubs)
    built-ins, ensemble)                   │            │
                                           ▼            ▼
                                  tradelab.risk   tradelab.safety
                                  (metrics,       (LIVE_TRADING_ENABLED=False,
                                   sizing, limits) paper guards)
```

## Data flow

1. **Data** — a `DataProvider` returns a normalised OHLCV `DataFrame`
   (`DatetimeIndex`, lowercase `open high low close volume`). `create_data_provider`
   wraps network providers in `CachedDataProvider`.
2. **Signals** — each `Strategy.compute(df)` returns a series in `[-1, 1]`
   using only information available at bar *t*'s close.
3. **Weights** — `StrategyEngine.target_weights` turns per-symbol signals into
   portfolio weights (equal weight / fixed fraction / vol target), then applies
   long-only, max position weight and gross leverage caps.
4. **Simulation** — `Backtester.run` trades towards the weights. With
   `execution: next_open` (default) the weight decided at close *t* is filled at
   the open of *t+1*, so there is no look-ahead. Costs and slippage are applied
   per fill.
5. **Analytics** — `BacktestResult.metrics()` calls `tradelab.risk.metrics.summarize`.
6. **Execution** — `Rebalancer` diffs the latest target weights against broker
   positions, runs `PreTradeRiskChecker`, and (only after explicit confirmation)
   submits approved orders through a paper `Broker`.

## Design principles

- **UI is thin.** All logic lives in `tradelab/` and is unit-tested; pages only
  collect inputs and render outputs.
- **Broker-neutral models.** UI and execution code never import vendor SDK types.
- **Safety in the base class.** `Broker.submit_order` is a template method that
  calls `assert_paper_broker` before delegating to `_submit_order`, so adapters
  cannot skip the guard.
- **Typed, validated config.** Pydantic models for settings and strategy params
  produce clear errors for bad YAML.
- **Deterministic offline mode.** `SyntheticDataProvider` makes tests and demos
  reproducible without network access.
