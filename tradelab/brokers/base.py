"""Broker abstraction layer.

Every adapter subclasses :class:`Broker` and implements the ``_``-prefixed hooks. The
public ``submit_order`` / ``close_position`` methods are template methods that run the
paper-only safety guard and request validation *before* delegating to the adapter, so
an adapter cannot accidentally bypass the live-trading kill switch.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from tradelab.brokers.models import (
    Account,
    BrokerCapabilities,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    Position,
)
from tradelab.safety import assert_paper_broker


class BrokerError(RuntimeError):
    """Adapter-level failure (connectivity, rejected request, etc.)."""


class Broker(ABC):
    name: str = "base"
    capabilities: BrokerCapabilities = BrokerCapabilities(paper_trading=False, implemented=False)

    @property
    def is_paper(self) -> bool:
        """True only if this adapter is connected to a paper/simulated environment."""
        return False

    # ----- account / market data -----
    @abstractmethod
    def get_account(self) -> Account: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    def get_position(self, symbol: str) -> Position | None:
        sym = symbol.upper()
        return next((p for p in self.get_positions() if p.symbol == sym), None)

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float: ...

    def is_market_open(self) -> bool:
        return True

    # ----- orders -----
    def submit_order(self, request: OrderRequest) -> Order:
        assert_paper_broker(self)
        caps = self.capabilities
        if request.order_type not in caps.order_types:
            raise BrokerError(f"{self.name} does not support {request.order_type.value} orders")
        if not caps.fractional_shares and request.qty != int(request.qty):
            raise BrokerError(f"{self.name} does not support fractional quantities")
        return self._submit_order(request)

    @abstractmethod
    def _submit_order(self, request: OrderRequest) -> Order: ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order: ...

    @abstractmethod
    def list_orders(self, status: str = "open") -> list[Order]:
        """``status`` is one of ``open`` | ``closed`` | ``all``."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> None: ...

    def cancel_all_orders(self) -> int:
        orders = [o for o in self.list_orders("open") if o.status.is_open]
        for o in orders:
            self.cancel_order(o.id)
        return len(orders)

    def close_position(self, symbol: str) -> Order | None:
        assert_paper_broker(self)
        pos = self.get_position(symbol)
        if pos is None or pos.qty == 0:
            return None
        side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
        return self.submit_order(OrderRequest(symbol=pos.symbol, qty=abs(pos.qty), side=side))

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} paper={self.is_paper}>"


__all__ = ["Broker", "BrokerError", "OrderStatus"]
