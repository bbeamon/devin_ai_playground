"""Deterministic synthetic OHLCV data (geometric Brownian motion) for offline demos/tests."""

from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from tradelab.data.base import DataProvider


class SyntheticDataProvider(DataProvider):
    name = "synthetic"

    def __init__(
        self,
        seed: int = 42,
        annual_drift: float = 0.08,
        annual_vol: float = 0.20,
        start_price: float = 100.0,
        default_start: str = "2018-01-01",
        default_end: str = "2024-12-31",
    ) -> None:
        self.seed = seed
        self.annual_drift = annual_drift
        self.annual_vol = annual_vol
        self.start_price = start_price
        self.default_start = default_start
        self.default_end = default_end

    def fetch(
        self, symbol: str, start: pd.Timestamp | None, end: pd.Timestamp | None, interval: str
    ) -> pd.DataFrame:
        if interval != "1d":
            raise ValueError("SyntheticDataProvider only supports interval='1d'")
        s = start or pd.Timestamp(self.default_start)
        e = end or pd.Timestamp(self.default_end)
        # Generate from a fixed origin so the same symbol always yields the same path
        # regardless of the requested window.
        origin = min(pd.Timestamp("2000-01-03"), s)
        dates = pd.bdate_range(origin, e, name="date")
        rng = np.random.default_rng(self.seed + zlib.crc32(symbol.encode()))
        n = len(dates)
        dt = 1 / 252
        drift = (self.annual_drift - 0.5 * self.annual_vol**2) * dt
        rets = rng.normal(drift, self.annual_vol * np.sqrt(dt), n)
        close = self.start_price * np.exp(np.cumsum(rets))
        gap = rng.normal(0, self.annual_vol * np.sqrt(dt) * 0.3, n)
        open_ = np.concatenate([[self.start_price], close[:-1]]) * np.exp(gap)
        spread = np.abs(rng.normal(0, self.annual_vol * np.sqrt(dt) * 0.5, n))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.integers(500_000, 5_000_000, n).astype(float)
        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        )
        return df[df.index >= s]
