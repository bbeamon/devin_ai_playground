"""Strategy interface.

A strategy maps one symbol's OHLCV history to a *signal* series in ``[-1, 1]`` indexed
like the input: +1 = fully long, 0 = flat, -1 = fully short. The signal at bar ``t`` may
only use information available at the close of bar ``t``; the backtester handles the
execution lag. Position sizing and risk limits are applied separately by the engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import pandas as pd
from pydantic import BaseModel, ConfigDict


class StrategyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Strategy(ABC):
    name: ClassVar[str] = "base"
    description: ClassVar[str] = ""
    Params: ClassVar[type[StrategyParams]] = StrategyParams

    def __init__(self, **params: Any) -> None:
        # Typed as Any so subclasses can access their own parameter fields.
        self.params: Any = self.Params(**params)

    @property
    def warmup(self) -> int:
        """Number of bars needed before the signal is meaningful."""
        return 0

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Return raw signal (may contain NaN during warm-up)."""

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        sig = self.compute(df).reindex(df.index)
        return sig.fillna(0.0).clip(-1.0, 1.0).astype(float).rename(self.name)

    @classmethod
    def param_schema(cls) -> dict[str, Any]:
        return cls.Params.model_json_schema()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.params.model_dump()})"
