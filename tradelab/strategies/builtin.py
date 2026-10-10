"""Built-in strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from tradelab.strategies import indicators as ind
from tradelab.strategies.base import Strategy, StrategyParams
from tradelab.strategies.registry import register_strategy


def _hold_state(entries: pd.Series, exits: pd.Series) -> pd.Series:
    """Convert entry/exit booleans into a 0/1 position that persists between events."""
    state = pd.Series(np.nan, index=entries.index)
    state[exits.fillna(False)] = 0.0
    state[entries.fillna(False)] = 1.0
    return state.ffill().fillna(0.0)


@register_strategy
class BuyAndHold(Strategy):
    name = "buy_and_hold"
    description = "Always fully long. Useful as a baseline."

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index)


class _CrossParams(StrategyParams):
    fast: int = Field(20, ge=1)
    slow: int = Field(50, ge=2)
    allow_short: bool = False

    @model_validator(mode="after")
    def _check(self) -> _CrossParams:
        if self.fast >= self.slow:
            raise ValueError("fast must be < slow")
        return self


@register_strategy
class SMACrossover(Strategy):
    name = "sma_crossover"
    description = "Long when fast SMA > slow SMA (short when below if allow_short)."
    Params = _CrossParams

    @property
    def warmup(self) -> int:
        return self.params.slow

    def _ma(self, s: pd.Series, n: int) -> pd.Series:
        return ind.sma(s, n)

    def compute(self, df: pd.DataFrame) -> pd.Series:
        p = self.params
        fast, slow = self._ma(df["close"], p.fast), self._ma(df["close"], p.slow)
        sig = pd.Series(np.where(fast > slow, 1.0, -1.0 if p.allow_short else 0.0), index=df.index)
        return sig.where(slow.notna())


@register_strategy
class EMACrossover(SMACrossover):
    name = "ema_crossover"
    description = "Long when fast EMA > slow EMA (short when below if allow_short)."

    def _ma(self, s: pd.Series, n: int) -> pd.Series:
        return ind.ema(s, n)


class _RSIParams(StrategyParams):
    period: int = Field(14, ge=2)
    oversold: float = Field(30, gt=0, lt=100)
    overbought: float = Field(70, gt=0, lt=100)

    @model_validator(mode="after")
    def _check(self) -> _RSIParams:
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be < overbought")
        return self


@register_strategy
class RSIMeanReversion(Strategy):
    name = "rsi_mean_reversion"
    description = "Enter long when RSI < oversold; exit when RSI > overbought."
    Params = _RSIParams

    @property
    def warmup(self) -> int:
        return self.params.period + 1

    def compute(self, df: pd.DataFrame) -> pd.Series:
        p = self.params
        r = ind.rsi(df["close"], p.period)
        return _hold_state(r < p.oversold, r > p.overbought)


class _BBParams(StrategyParams):
    window: int = Field(20, ge=2)
    num_std: float = Field(2.0, gt=0)


@register_strategy
class BollingerReversion(Strategy):
    name = "bollinger_reversion"
    description = "Enter long on close below lower band; exit on close above middle band."
    Params = _BBParams

    @property
    def warmup(self) -> int:
        return self.params.window

    def compute(self, df: pd.DataFrame) -> pd.Series:
        p = self.params
        lower, mid, _ = ind.bollinger_bands(df["close"], p.window, p.num_std)
        return _hold_state(df["close"] < lower, df["close"] > mid)


class _MomParams(StrategyParams):
    lookback: int = Field(126, ge=2)
    skip: int = Field(0, ge=0, description="Most-recent bars to skip (e.g. 21 for 12-1 momentum)")
    allow_short: bool = False


@register_strategy
class Momentum(Strategy):
    name = "momentum"
    description = "Time-series momentum: long if trailing return over `lookback` bars > 0."
    Params = _MomParams

    @property
    def warmup(self) -> int:
        return self.params.lookback + self.params.skip

    def compute(self, df: pd.DataFrame) -> pd.Series:
        p = self.params
        c = df["close"].shift(p.skip)
        ret = c / c.shift(p.lookback) - 1
        sig = pd.Series(np.where(ret > 0, 1.0, -1.0 if p.allow_short else 0.0), index=df.index)
        return sig.where(ret.notna())


class _DonchianParams(StrategyParams):
    entry_window: int = Field(20, ge=2)
    exit_window: int = Field(10, ge=2)


@register_strategy
class DonchianBreakout(Strategy):
    name = "donchian_breakout"
    description = "Turtle-style: long on close above prior N-bar high; exit below prior M-bar low."
    Params = _DonchianParams

    @property
    def warmup(self) -> int:
        return self.params.entry_window + 1

    def compute(self, df: pd.DataFrame) -> pd.Series:
        p = self.params
        upper, _ = ind.donchian(df, p.entry_window)
        _, lower = ind.donchian(df, p.exit_window)
        return _hold_state(df["close"] > upper, df["close"] < lower)


class _MACDParams(StrategyParams):
    fast: int = Field(12, ge=1)
    slow: int = Field(26, ge=2)
    signal: int = Field(9, ge=1)


@register_strategy
class MACDTrend(Strategy):
    name = "macd"
    description = "Long while the MACD line is above its signal line."
    Params = _MACDParams

    @property
    def warmup(self) -> int:
        return self.params.slow + self.params.signal

    def compute(self, df: pd.DataFrame) -> pd.Series:
        p = self.params
        line, sig, _ = ind.macd(df["close"], p.fast, p.slow, p.signal)
        return pd.Series(np.where(line > sig, 1.0, 0.0), index=df.index).where(sig.notna())
