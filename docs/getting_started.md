# Getting started

## Requirements

- Python 3.10+
- Internet access for Yahoo Finance / Alpaca data (optional — the `synthetic`
  and `csv` providers work offline)

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip setuptools wheel     # editable installs need a modern setuptools
pip install -e ".[dev]"                 # or: pip install -r requirements.txt
```

## Run

```bash
streamlit run app/Home.py
```

Pages:

1. **Data Explorer** — load OHLCV, data-quality checks, candlesticks with SMA/Bollinger/RSI, correlations, CSV export.
2. **Backtest** — configure a strategy via form or YAML, costs, execution and risk limits; view equity, drawdown, weights, trades and metrics.
3. **Risk Analytics** — deep-dive on the last backtest: rolling Sharpe/vol/beta, VaR/CVaR, return distribution, monthly heatmap.
4. **Optimizer** — grid search over numeric parameters with optional out-of-sample split.
5. **Paper Trading** — simulated or Alpaca paper broker: account, positions, strategy rebalance preview with pre-trade checks, manual orders, cancel.

## Configuration

`config/default.yaml` holds platform defaults (data provider, cache, costs,
execution, risk limits, broker). Point to another file with
`TRADELAB_CONFIG=/path/to/file.yaml`.

```yaml
data:     {provider: yahoo, cache_enabled: true, cache_dir: .cache/data, csv_dir: data/csv}
backtest: {initial_cash: 100000, slippage_bps: 5, execution: next_open, allow_short: false}
risk:     {max_position_weight: 0.25, max_gross_leverage: 1.0, max_order_notional: 25000}
broker:   {name: simulated, trading_mode: paper}   # any other trading_mode is rejected
```

Strategy configs live in `config/strategies/*.yaml` — see [strategies.md](strategies.md).

### CSV data

Put one file per symbol at `data/csv/<SYMBOL>.csv` with a `date` column plus
`open, high, low, close, volume` and select the `csv` provider.

## Alpaca paper trading (manual step)

1. Create a free account at <https://alpaca.markets> and open the **Paper Trading** dashboard.
2. Generate **paper** API keys (they start with `PK`). Live keys (`AK…`) are rejected.
3. `cp .env.example .env` and fill in:

   ```dotenv
   ALPACA_API_KEY=PK...
   ALPACA_SECRET_KEY=...
   ALPACA_DATA_FEED=iex      # 'sip' requires a paid data subscription
   ```

4. Restart Streamlit, open **Paper Trading**, choose `alpaca_paper`.

`.env` is git-ignored. Never commit keys.

## Tests and quality checks

```bash
pytest -m "not network"          # offline suite (default in CI)
pytest -m network                # hits Yahoo Finance
pytest --cov=tradelab            # coverage
ruff check . && ruff format --check .
mypy tradelab
```
