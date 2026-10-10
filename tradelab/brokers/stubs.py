"""Placeholder adapters for brokers planned for future integration.

They expose the same :class:`Broker` interface so UI/engine code can be written against
them today. All methods raise ``NotImplementedError`` until implemented. See
``docs/brokers.md`` for integration notes.
"""

from __future__ import annotations

from typing import NoReturn

from tradelab.brokers.base import Broker
from tradelab.brokers.models import (
    Account,
    AssetClass,
    BrokerCapabilities,
    Order,
    OrderRequest,
    OrderType,
    Position,
)
from tradelab.safety import LiveTradingDisabledError, assert_ibkr_paper_port


class _NotImplementedBroker(Broker):
    def _todo(self) -> NoReturn:
        raise NotImplementedError(
            f"The {self.name} adapter is a stub. See docs/brokers.md for the integration plan."
        )

    def get_account(self) -> Account:
        self._todo()

    def get_positions(self) -> list[Position]:
        self._todo()

    def get_latest_price(self, symbol: str) -> float:
        self._todo()

    def _submit_order(self, request: OrderRequest) -> Order:
        self._todo()

    def get_order(self, order_id: str) -> Order:
        self._todo()

    def list_orders(self, status: str = "open") -> list[Order]:
        self._todo()

    def cancel_order(self, order_id: str) -> None:
        self._todo()


class InteractiveBrokersBroker(_NotImplementedBroker):
    """Interactive Brokers via TWS / IB Gateway (planned: ``ib_async``).

    Only paper ports (TWS 7497, Gateway 4002) are accepted.
    """

    name = "ibkr"
    capabilities = BrokerCapabilities(
        paper_trading=True,
        fractional_shares=False,
        short_selling=True,
        order_types=frozenset(OrderType),
        asset_classes=frozenset(AssetClass),
        implemented=False,
        notes="Planned via ib_async against a TWS/IB Gateway paper session.",
    )

    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1) -> None:
        assert_ibkr_paper_port(port)
        self.host, self.port, self.client_id = host, port, client_id

    @property
    def is_paper(self) -> bool:
        return True


class SchwabBroker(_NotImplementedBroker):
    """Charles Schwab Trader API (planned: ``schwab-py``; OAuth).

    Schwab's Trader API does not expose a paper-trading environment, so order submission
    is permanently blocked here; a future adapter would be read-only (accounts, quotes).
    """

    name = "schwab"
    capabilities = BrokerCapabilities(
        paper_trading=False,
        implemented=False,
        notes="No paper environment via API; future adapter will be read-only.",
    )

    def _submit_order(self, request: OrderRequest) -> Order:
        raise LiveTradingDisabledError(
            "Schwab has no paper environment; order submission disabled."
        )


class FidelityBroker(_NotImplementedBroker):
    """Fidelity (no public retail trading API).

    Planned support is import-only (positions/transactions CSV export) for analytics.
    """

    name = "fidelity"
    capabilities = BrokerCapabilities(
        paper_trading=False,
        implemented=False,
        notes="No public retail trading API; future support via CSV position import.",
    )

    def _submit_order(self, request: OrderRequest) -> Order:
        raise LiveTradingDisabledError("Fidelity order submission is not supported.")
