# Brokers and the safety model

## Abstraction layer

`tradelab.brokers.base.Broker` defines the interface every adapter implements:

```python
get_account() -> Account
get_positions() -> list[Position]
get_position(symbol) -> Position | None
get_latest_price(symbol) -> float
submit_order(OrderRequest) -> Order        # template method: safety guard, then _submit_order
get_order(order_id) -> Order
list_orders(status="open") -> list[Order]
cancel_order(order_id) -> None
cancel_all_orders() -> int
close_position(symbol) -> Order | None     # guarded
capabilities: BrokerCapabilities
is_paper: bool
```

Models in `tradelab.brokers.models` (`OrderRequest`, `Order`, `Position`,
`Account`, enums for side / type / time-in-force / status) are vendor-neutral.
Create adapters with `tradelab.brokers.create_broker(name, ...)`.

| Name | Status |
|---|---|
| `simulated` | In-memory paper broker: market/limit/stop/stop-limit, fractional shares, slippage & commission |
| `alpaca_paper` | Alpaca paper trading via `alpaca-py` |
| `ibkr` | Stub — validates paper ports, not yet implemented |
| `schwab` | Stub — no paper environment; order submission blocked |
| `fidelity` | Stub — no public retail trading API; order submission blocked |

## Safety model

Live-money trading is disabled by multiple independent layers:

1. `tradelab.safety.LIVE_TRADING_ENABLED = False` — a code constant, never read
   from config or environment (a test asserts env vars can't flip it).
2. `BrokerSettings.trading_mode` must be exactly `"paper"`; anything else fails validation.
3. `Broker.submit_order` / `close_position` call `assert_paper_broker`, which
   raises `LiveTradingDisabledError` unless `broker.is_paper` is true. The
   `Rebalancer` checks this too.
4. `AlpacaPaperBroker` always constructs `TradingClient(paper=True)` and verifies
   the client's base URL host is `paper-api.alpaca.markets`.
5. Alpaca keys starting with `AK` (live) are rejected; paper keys start with `PK`.
6. IBKR only accepts paper ports `7497` (TWS) / `4002` (Gateway).
7. The UI requires an explicit confirmation checkbox before sending paper orders.

Re-enabling live trading would require deliberately editing `safety.py`, the
adapters and the tests — it is intentionally not a configuration option.

## Roadmap for additional brokers

### Interactive Brokers
- Use `ib_async` (maintained successor of `ib_insync`) against TWS or IB Gateway in **paper** mode.
- Implement `_submit_order`, `get_positions`, `get_account`, etc. in
  `InteractiveBrokersBroker`; map `Contract`/`Order`/`Trade` to tradelab models.
- Keep `assert_ibkr_paper_port` and also verify the account ID starts with `DU` (paper).

### Charles Schwab
- The Schwab Trader API (developer.schwab.com) requires app approval and OAuth
  with refresh tokens; there is no paper sandbox for order placement.
- Plan: implement read-only `get_account` / `get_positions` / market data first;
  orders stay blocked (`is_paper = False`).

### Fidelity
- No public retail trading API. Support is planned as **import-only**: parse
  exported positions/activity CSVs into `Position`/`Order` models for analytics.

### Adding an adapter
1. Subclass `Broker`, set `name`, `capabilities`, and `is_paper`.
2. Implement the abstract methods (`get_account`, `get_positions`, `get_latest_price`, `_submit_order`, `get_order`, `list_orders`, `cancel_order`).
3. Register it in `tradelab/brokers/factory.py`.
4. Add mapping tests with a fake client (see `tests/test_brokers.py::test_alpaca_mapping`).
