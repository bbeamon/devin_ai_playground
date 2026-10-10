"""Ensemble strategy: weighted average of component strategy signals."""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from tradelab.strategies.base import Strategy, StrategyParams
from tradelab.strategies.registry import create_strategy, register_strategy


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: str
    params: dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(1.0, gt=0)


class _EnsembleParams(StrategyParams):
    components: list[Component] = Field(min_length=1)


@register_strategy
class Ensemble(Strategy):
    name = "ensemble"
    description = "Weighted average of component strategy signals."
    Params = _EnsembleParams

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.members: list[tuple[Strategy, float]] = [
            (create_strategy(c.strategy, **c.params), c.weight) for c in self.params.components
        ]

    @property
    def warmup(self) -> int:
        return max(s.warmup for s, _ in self.members)

    def compute(self, df: pd.DataFrame) -> pd.Series:
        total = sum(w for _, w in self.members)
        out = sum(s.generate_signals(df) * w for s, w in self.members) / total
        return pd.Series(out, index=df.index)
