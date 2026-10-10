"""Alpaca market-data provider (requires Alpaca API keys; read-only)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tradelab.data.base import DataError, DataProvider

_INTERVALS = {"1d": ("Day", 1), "1h": ("Hour", 1), "1m": ("Minute", 1), "15m": ("Minute", 15)}


class AlpacaDataProvider(DataProvider):
    name = "alpaca"

    def __init__(
        self, api_key: str, secret_key: str, feed: str = "iex", client: Any | None = None
    ) -> None:
        if client is None:
            if not (api_key and secret_key):
                raise DataError("Alpaca data provider requires ALPACA_API_KEY/ALPACA_SECRET_KEY")
            from alpaca.data.historical import StockHistoricalDataClient

            client = StockHistoricalDataClient(api_key, secret_key)
        self.client: Any = client
        self.feed = feed

    def fetch(
        self, symbol: str, start: pd.Timestamp | None, end: pd.Timestamp | None, interval: str
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        if interval not in _INTERVALS:
            raise DataError(f"Unsupported interval {interval!r}; choose from {list(_INTERVALS)}")
        unit, amount = _INTERVALS[interval]
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(amount, TimeFrameUnit[unit]),
            start=start.to_pydatetime() if start is not None else None,
            end=(end + pd.Timedelta(days=1)).to_pydatetime() if end is not None else None,
            adjustment=Adjustment.ALL,
            feed=DataFeed(self.feed),
        )
        try:
            bars = self.client.get_stock_bars(req)
        except Exception as exc:  # pragma: no cover - network dependent
            raise DataError(f"Alpaca bars request failed for {symbol}: {exc}") from exc
        df = bars.df
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")
        df = df[["open", "high", "low", "close", "volume"]]
        if interval == "1d":
            idx = pd.DatetimeIndex(df.index)
            if idx.tz is not None:
                idx = idx.tz_convert("America/New_York").tz_localize(None)
            df.index = idx.normalize()
        return df
