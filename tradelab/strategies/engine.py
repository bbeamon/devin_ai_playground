"""Configurable strategy engine: YAML/dict config -> signals -> sized, risk-limited weights."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tradelab.config import RiskSettings, load_yaml
from tradelab.risk import sizing
from tradelab.strategies.base import Strategy
from tradelab.strategies.registry import create_strategy


class SizingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["equal_weight", "fixed_fraction", "vol_target"] = "equal_weight"
    fraction: float = Field(0.1, gt=0, le=10)
    target_vol: float = Field(0.10, gt=0)
    vol_lookback: int = Field(20, ge=2)
    max_asset_leverage: float = Field(1.0, gt=0)


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "Unnamed strategy"
    strategy: str
    params: dict[str, Any] = Field(default_factory=dict)
    components: list[dict[str, Any]] | None = None
    universe: list[str] = Field(min_length=1)
    start: date | None = None
    end: date | None = None
    benchmark: str | None = "SPY"
    sizing: SizingConfig = SizingConfig()

    @field_validator("universe")
    @classmethod
    def _upper(cls, v: list[str]) -> list[str]:
        out = list(dict.fromkeys(s.strip().upper() for s in v if s.strip()))
        if not out:
            raise ValueError("universe must contain at least one symbol")
        return out

    @model_validator(mode="after")
    def _components(self) -> StrategyConfig:
        if self.components is not None:
            self.params = {**self.params, "components": self.components}
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be before end")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> StrategyConfig:
        return cls.model_validate(load_yaml(path))

    def build_strategy(self) -> Strategy:
        return create_strategy(self.strategy, **self.params)


def align_closes(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame({sym: df["close"] for sym, df in data.items()}).sort_index()


class StrategyEngine:
    def __init__(
        self,
        config: StrategyConfig,
        risk: RiskSettings | None = None,
        allow_short: bool = False,
    ) -> None:
        self.config = config
        self.risk = risk or RiskSettings()
        self.allow_short = allow_short
        self.strategy = config.build_strategy()

    def signals(self, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        missing = [s for s in self.config.universe if s not in data]
        if missing:
            raise KeyError(f"Missing data for symbols: {missing}")
        sigs = {s: self.strategy.generate_signals(data[s]) for s in self.config.universe}
        return pd.DataFrame(sigs).sort_index().fillna(0.0)

    def target_weights(
        self, data: dict[str, pd.DataFrame], signals: pd.DataFrame | None = None
    ) -> pd.DataFrame:
        sig = self.signals(data) if signals is None else signals
        cfg = self.config.sizing
        if cfg.method == "equal_weight":
            raw = sizing.equal_weight(sig)
        elif cfg.method == "fixed_fraction":
            raw = sizing.fixed_fraction(sig, cfg.fraction)
        else:
            closes = align_closes({s: data[s] for s in sig.columns}).reindex(sig.index)
            raw = sizing.volatility_target(
                sig, closes, cfg.target_vol, cfg.vol_lookback, cfg.max_asset_leverage
            )
        return sizing.apply_weight_limits(
            raw, self.risk.max_position_weight, self.risk.max_gross_leverage, self.allow_short
        )

    def latest_target_weights(self, data: dict[str, pd.DataFrame]) -> pd.Series:
        w = self.target_weights(data)
        return w.iloc[-1] if len(w) else pd.Series(0.0, index=self.config.universe)
