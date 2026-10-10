"""On-disk cache wrapper for any DataProvider."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from tradelab.data.base import DataProvider


class CachedDataProvider(DataProvider):
    """Caches each (provider, symbol, start, end, interval) request as CSV.

    Requests whose ``end`` is in the future or unspecified are not cached, since the
    data would still change.
    """

    def __init__(self, inner: DataProvider, cache_dir: str | Path) -> None:
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.name = f"cached:{inner.name}"

    def _path(
        self, symbol: str, start: pd.Timestamp | None, end: pd.Timestamp | None, interval: str
    ) -> Path:
        key = f"{self.inner.name}|{symbol}|{start}|{end}|{interval}"
        digest = hashlib.sha1(key.encode()).hexdigest()[:16]
        return self.cache_dir / self.inner.name / f"{symbol}_{interval}_{digest}.csv"

    def fetch(
        self, symbol: str, start: pd.Timestamp | None, end: pd.Timestamp | None, interval: str
    ) -> pd.DataFrame:
        cacheable = end is not None and end < pd.Timestamp.today().normalize()
        path = self._path(symbol, start, end, interval)
        if cacheable and path.exists():
            return pd.read_csv(path, index_col="date", parse_dates=["date"])
        df = self.inner.fetch(symbol, start, end, interval)
        if cacheable and df is not None and not df.empty:
            from tradelab.data.base import normalize_ohlcv

            path.parent.mkdir(parents=True, exist_ok=True)
            normalize_ohlcv(df).to_csv(path, index_label="date")
        return df

    def clear(self) -> int:
        removed = 0
        if self.cache_dir.exists():
            for p in self.cache_dir.rglob("*.csv"):
                p.unlink()
                removed += 1
        return removed
