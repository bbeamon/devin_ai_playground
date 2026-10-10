"""Broker factory. Every broker returned here is paper/simulated or a non-trading stub."""

from __future__ import annotations

from typing import Any

from tradelab.brokers.base import Broker
from tradelab.config import AlpacaCredentials, BrokerSettings
from tradelab.safety import assert_paper_mode

BROKER_NAMES = ("simulated", "alpaca_paper", "ibkr", "schwab", "fidelity")


def create_broker(
    name: str | None = None,
    settings: BrokerSettings | None = None,
    credentials: AlpacaCredentials | None = None,
    **kwargs: Any,
) -> Broker:
    settings = settings or BrokerSettings()
    assert_paper_mode(settings.trading_mode)
    name = name or settings.name
    if name == "simulated":
        from tradelab.brokers.simulated import SimulatedBroker

        return SimulatedBroker(**kwargs)
    if name == "alpaca_paper":
        from tradelab.brokers.alpaca_paper import AlpacaPaperBroker

        creds = credentials or AlpacaCredentials()
        return AlpacaPaperBroker(
            creds.api_key, creds.secret_key, data_feed=creds.data_feed, **kwargs
        )
    if name == "ibkr":
        from tradelab.brokers.stubs import InteractiveBrokersBroker

        return InteractiveBrokersBroker(**kwargs)
    if name == "schwab":
        from tradelab.brokers.stubs import SchwabBroker

        return SchwabBroker()
    if name == "fidelity":
        from tradelab.brokers.stubs import FidelityBroker

        return FidelityBroker()
    raise ValueError(f"Unknown broker {name!r}. Choose from {BROKER_NAMES}")
