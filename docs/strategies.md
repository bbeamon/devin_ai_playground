# Strategy engine

## Concepts

- **Strategy** (`tradelab.strategies.base.Strategy`) — maps one symbol's OHLCV
  `DataFrame` to a signal series in `[-1, 1]` (1 = fully long, 0 = flat, -1 = fully short).
  Signals at bar *t* may only use data up to *t*'s close; the backtester handles fill timing.
- **Params** — each strategy declares a Pydantic `Params` model, so YAML/UI inputs are
  type-checked and cross-validated (e.g. `fast < slow`).
- **Registry** — `@register_strategy` makes a class available by `name`;
  `create_strategy("module.path:ClassName", ...)` loads unregistered classes.
- **StrategyEngine** — applies a strategy to every symbol in the universe and converts
  signals to portfolio target weights using a sizing method and risk caps.

## Built-in strategies

| Name | Parameters | Logic |
|---|---|---|
| `buy_and_hold` | — | Always long |
| `sma_crossover` | `fast=20`, `slow=50`, `allow_short=false` | Long when fast SMA > slow SMA |
| `ema_crossover` | same as SMA | EMA version |
| `rsi_mean_reversion` | `period=14`, `oversold=30`, `overbought=70` | Enter long below oversold, exit above overbought |
| `bollinger_reversion` | `window=20`, `num_std=2.0` | Enter below lower band, exit at middle band |
| `momentum` | `lookback=126`, `skip=0`, `allow_short=false` | Long if trailing return > 0 (`skip=21` for 12-1 momentum) |
| `donchian_breakout` | `entry_window=20`, `exit_window=10` | Long on close above prior N-bar high, exit below prior M-bar low |
| `macd` | `fast=12`, `slow=26`, `signal=9` | Long when MACD line > signal line |
| `ensemble` | `components: [...]` | Weighted average of component signals |

Indicators (`tradelab.strategies.indicators`): `sma`, `ema`, `rsi` (Wilder),
`bollinger_bands`, `macd`, `atr`, `donchian`.

## YAML configuration

```yaml
name: SMA 20/50 crossover - mega-cap tech
strategy: sma_crossover
params: {fast: 20, slow: 50}
universe: [AAPL, MSFT, NVDA, GOOGL]
start: 2018-01-01
end: 2024-12-31
benchmark: SPY
sizing:
  method: equal_weight        # equal_weight | fixed_fraction | vol_target
  fraction: 0.1               # fixed_fraction: weight per active signal
  target_vol: 0.10            # vol_target: annualised per-asset vol target
  vol_lookback: 20
  max_asset_leverage: 1.0     # vol_target: cap per asset before portfolio limits
```

Ensemble:

```yaml
strategy: ensemble
components:
  - {strategy: sma_crossover, params: {fast: 50, slow: 200}, weight: 0.5}
  - {strategy: momentum, params: {lookback: 126}, weight: 0.5}
universe: [SPY, QQQ, IWM, TLT, GLD]
```

Load with `StrategyConfig.from_yaml(path)` or paste into the Backtest page's YAML tab.
Examples live in `config/strategies/`.

After sizing, `StrategyEngine` enforces `risk.max_position_weight`,
`risk.max_gross_leverage`, and clips shorts unless `backtest.allow_short` is true.

## Writing a strategy

```python
import pandas as pd
from pydantic import Field

from tradelab.strategies import Strategy, StrategyParams, register_strategy
from tradelab.strategies.indicators import atr, sma


class _Params(StrategyParams):
    window: int = Field(50, ge=2)
    atr_mult: float = Field(2.0, gt=0)


@register_strategy
class KeltnerBreakout(Strategy):
    name = "keltner_breakout"
    description = "Long when close breaks above SMA + k*ATR."
    Params = _Params

    def compute(self, df: pd.DataFrame) -> pd.Series:
        p = self.params
        upper = sma(df["close"], p.window) + p.atr_mult * atr(df, p.window)
        return (df["close"] > upper).astype(float)
```

Import the module before use (or reference it as `strategy: mypkg.mymodule:KeltnerBreakout`).
Add a no-look-ahead test: `tests/test_strategies.py::test_no_lookahead` runs every
registered strategy on truncated vs. full data and checks the overlapping signals match.
