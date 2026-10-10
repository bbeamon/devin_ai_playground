"""Build a configured DataProvider."""

from __future__ import annotations

from tradelab.config import AlpacaCredentials, DataSettings
from tradelab.data.base import DataProvider
from tradelab.data.cache import CachedDataProvider
from tradelab.data.csv_provider import CSVDataProvider
from tradelab.data.synthetic import SyntheticDataProvider
from tradelab.data.yahoo import YahooDataProvider


def create_data_provider(
    settings: DataSettings | None = None, credentials: AlpacaCredentials | None = None
) -> DataProvider:
    settings = settings or DataSettings()
    provider: DataProvider
    if settings.provider == "yahoo":
        provider = YahooDataProvider()
    elif settings.provider == "alpaca":
        from tradelab.data.alpaca_data import AlpacaDataProvider

        creds = credentials or AlpacaCredentials()
        provider = AlpacaDataProvider(creds.api_key, creds.secret_key, feed=creds.data_feed)
    elif settings.provider == "csv":
        provider = CSVDataProvider(settings.csv_dir)
    elif settings.provider == "synthetic":
        provider = SyntheticDataProvider()
    else:  # pragma: no cover - guarded by pydantic Literal
        raise ValueError(f"Unknown data provider {settings.provider!r}")
    if settings.cache_enabled and settings.provider not in ("synthetic", "csv"):
        provider = CachedDataProvider(provider, settings.cache_dir)
    return provider
