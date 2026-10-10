"""Local CSV provider: reads ``<directory>/<SYMBOL>.csv`` with a date column + OHLCV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tradelab.data.base import DataError, DataProvider


class CSVDataProvider(DataProvider):
    name = "csv"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def fetch(
        self, symbol: str, start: pd.Timestamp | None, end: pd.Timestamp | None, interval: str
    ) -> pd.DataFrame:
        path = self.directory / f"{symbol}.csv"
        if not path.exists():
            raise DataError(f"CSV file not found: {path}")
        df = pd.read_csv(path)
        cols = {c.lower(): c for c in df.columns}
        date_col = next((cols[c] for c in ("date", "datetime", "timestamp") if c in cols), None)
        if date_col is None:
            raise DataError(f"{path} must contain a date/datetime/timestamp column")
        df[date_col] = pd.to_datetime(df[date_col])
        return df.set_index(date_col)
