"""Yahoo Finance provider via ``yfinance`` (split/dividend-adjusted prices)."""

from __future__ import annotations

import pandas as pd

from tradelab.data.base import DataError, DataProvider


class YahooDataProvider(DataProvider):
    name = "yahoo"

    def __init__(self, auto_adjust: bool = True) -> None:
        self.auto_adjust = auto_adjust

    def fetch(
        self, symbol: str, start: pd.Timestamp | None, end: pd.Timestamp | None, interval: str
    ) -> pd.DataFrame:
        import yfinance as yf

        kwargs: dict = {"interval": interval, "auto_adjust": self.auto_adjust, "progress": False}
        if start is not None:
            kwargs["start"] = start.strftime("%Y-%m-%d")
        if end is not None:
            # yfinance treats `end` as exclusive
            kwargs["end"] = (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if start is None and end is None:
            kwargs["period"] = "max"
        try:
            df = yf.download(symbol, **kwargs)
        except Exception as exc:  # pragma: no cover - network dependent
            raise DataError(f"yfinance download failed for {symbol}: {exc}") from exc
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(-1, axis=1) if df.columns.nlevels > 1 else df
        return df
