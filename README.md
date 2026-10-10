# tradelab — algorithmic trading research platform

A modular Python platform for researching equity strategies: historical data,
a configurable strategy engine, an event-free vectorised/iterative backtester,
risk analytics, a Streamlit UI and **paper-only** order routing through a broker
abstraction layer (Alpaca paper today; IBKR / Schwab / Fidelity scaffolded).

> **Live-money trading is disabled.** `tradelab.safety.LIVE_TRADING_ENABLED` is a
> hard-coded `False` constant (not read from config or env). Every order path
> verifies the broker is paper, Alpaca is pinned to `paper-api.alpaca.markets`,
> live-looking Alpaca keys (`AK…`) are rejected, and IBKR only accepts paper ports.
> See [docs/brokers.md](docs/brokers.md#safety-model).

## Features

| Area | What's included |
|---|---|
| Data | Yahoo Finance (default), Alpaca historical bars, local CSV, deterministic synthetic data; on-disk cache; OHLCV normalisation + validation |
| Strategies | Registry + Pydantic-validated params; YAML configs; built-ins: buy & hold, SMA/EMA crossover, RSI mean reversion, Bollinger reversion, momentum, Donchian breakout, MACD; weighted ensembles; custom strategies via `module:Class` |
| Sizing | Equal weight, fixed fraction, volatility targeting; max position weight, gross leverage cap, long-only |
| Backtesting | Next-open (default, no look-ahead) or close execution, commissions (per-share / % / min), slippage, fractional or whole shares, rebalance threshold, benchmark comparison, parameter grid search with out-of-sample split |
| Risk analytics | CAGR, vol, Sharpe, Sortino, Calmar, max drawdown & duration, VaR/CVaR, beta/alpha, tracking error, information ratio, win rate, profit factor, turnover, exposure, rolling stats, monthly returns |
| Brokers | Broker-neutral models (`OrderRequest`, `Order`, `Position`, `Account`); simulated broker; Alpaca paper adapter; IBKR / Schwab / Fidelity stubs; pre-trade risk checks; target-weight rebalancer |
| UI | Streamlit multipage app: Data Explorer, Backtest, Risk Analytics, Optimizer, Paper Trading |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -U pip setuptools wheel
pip install -e ".[dev]"
cp .env.example .env            # optional: Alpaca *paper* keys
streamlit run app/Home.py       # http://localhost:8501
pytest -m "not network"         # offline test suite
```

Pick the **synthetic** provider in the sidebar to use the app fully offline.

### Programmatic use

```python
from tradelab.backtest import run_backtest
from tradelab.risk.metrics import format_metrics
from tradelab.strategies import StrategyConfig

cfg = StrategyConfig.from_yaml("config/strategies/sma_crossover.yaml")
result = run_backtest(cfg)  # downloads via the configured provider
print(format_metrics(result.metrics()))
```

## Documentation

- [Getting started](docs/getting_started.md) — install, configuration, Alpaca paper setup
- [Architecture](docs/architecture.md) — package layout and data flow
- [Strategies](docs/strategies.md) — strategy engine, YAML configs, writing your own
- [Backtesting & risk](docs/backtesting_and_risk.md) — execution model, costs, metrics
- [Brokers](docs/brokers.md) — abstraction layer, safety model, IBKR/Schwab/Fidelity roadmap

## Project layout

```
app/                Streamlit UI (Home.py + pages/)
config/             default.yaml + example strategy YAMLs
tradelab/
  safety.py         live-trading kill switch and paper guards
  config.py         typed settings (Pydantic)
  data/             providers, cache, normalisation
  strategies/       indicators, base class, registry, built-ins, ensemble, engine
  backtest/         cost model, backtester, runner / grid search
  risk/             metrics, sizing, pre-trade limits
  brokers/          models, base class, simulated, alpaca_paper, stubs, factory
  execution/        target-weight rebalancer
  ui/               Plotly charts
tests/              pytest suite (offline by default; `-m network` for Yahoo)
```

## Disclaimer

For research and education only. Not investment advice. Backtest results are
hypothetical and do not account for every real-world effect.
