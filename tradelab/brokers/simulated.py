"""In-memory paper broker for offline development, tests and demos."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping

from tradelab.backtest.costs import CostModel
from tradelab.brokers.base import Broker, BrokerError
from tradelab.brokers.models import (
    Account,
    AssetClass,
    BrokerCapabilities,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

PriceSource = Mapping[str, float] | Callable[[str], float]


class SimulatedBroker(Broker):
    name = "simulated"
    capabilities = BrokerCapabilities(
        paper_trading=True,
        fractional_shares=True,
        short_selling=True,
        order_types=frozenset(OrderType),
        asset_classes=frozenset({AssetClass.EQUITY, AssetClass.ETF}),
        notes="In-memory simulator; fills market orders instantly at the latest price.",
    )

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        prices: PriceSource | None = None,
        costs: CostModel | None = None,
        allow_short: bool = False,
    ) -> None:
        self.cash = float(initial_cash)
        self._prices: dict[str, float] = {}
        self._price_fn: Callable[[str], float] | None = None
        if callable(prices):
            self._price_fn = prices
        elif prices is not None:
            self._prices = {k.upper(): float(v) for k, v in prices.items()}
        self.costs = costs or CostModel()
        self.allow_short = allow_short
        self._positions: dict[str, tuple[float, float]] = {}  # symbol -> (qty, avg_price)
        self._orders: dict[str, Order] = {}
        self._ids = itertools.count(1)

    @property
    def is_paper(self) -> bool:
        return True

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol.upper()] = float(price)
        self._process_open_orders()

    def get_latest_price(self, symbol: str) -> float:
        sym = symbol.upper()
        if self._price_fn is not None:
            return float(self._price_fn(sym))
        if sym not in self._prices:
            raise BrokerError(f"No price available for {sym}")
        return self._prices[sym]

    def get_account(self) -> Account:
        equity = self.cash + sum(p.market_value for p in self.get_positions())
        return Account(
            account_id="SIM-PAPER",
            cash=self.cash,
            equity=equity,
            buying_power=max(self.cash, 0.0),
            is_paper=True,
            broker=self.name,
        )

    def get_positions(self) -> list[Position]:
        return [
            Position(sym, qty, avg, self.get_latest_price(sym))
            for sym, (qty, avg) in sorted(self._positions.items())
            if qty != 0
        ]

    def _submit_order(self, request: OrderRequest) -> Order:
        sym = request.symbol.upper()
        order = Order(
            id=f"sim-{next(self._ids)}",
            symbol=sym,
            qty=request.qty,
            side=request.side,
            order_type=request.order_type,
            time_in_force=request.time_in_force,
            status=OrderStatus.ACCEPTED,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            client_order_id=request.client_order_id,
            broker=self.name,
        )
        current_qty = self._positions.get(sym, (0.0, 0.0))[0]
        if not self.allow_short and current_qty + request.signed_qty < -1e-9:
            order.status = OrderStatus.REJECTED
        self._orders[order.id] = order
        if order.status != OrderStatus.REJECTED:
            self._try_fill(order)
        return order

    def _marketable(self, order: Order, price: float) -> bool:
        buy = order.side == OrderSide.BUY
        if order.order_type == OrderType.MARKET:
            return True
        if order.order_type == OrderType.LIMIT:
            assert order.limit_price is not None
            return price <= order.limit_price if buy else price >= order.limit_price
        assert order.stop_price is not None
        triggered = price >= order.stop_price if buy else price <= order.stop_price
        if order.order_type == OrderType.STOP:
            return triggered
        assert order.limit_price is not None
        return triggered and (price <= order.limit_price if buy else price >= order.limit_price)

    def _try_fill(self, order: Order) -> None:
        price = self.get_latest_price(order.symbol)
        if not self._marketable(order, price):
            return
        signed = order.qty if order.side == OrderSide.BUY else -order.qty
        fill = self.costs.fill_price(price, signed)
        if order.limit_price is not None:
            fill = min(fill, order.limit_price) if signed > 0 else max(fill, order.limit_price)
        fee = self.costs.commission(signed, fill)
        if signed > 0 and signed * fill + fee > self.cash + 1e-6:
            order.status = OrderStatus.REJECTED
            return
        self.cash -= signed * fill + fee
        qty, avg = self._positions.get(order.symbol, (0.0, 0.0))
        new_qty = qty + signed
        if abs(new_qty) < 1e-12:
            self._positions.pop(order.symbol, None)
        else:
            same_dir = qty == 0 or (qty > 0) == (signed > 0)
            if same_dir:
                avg = (qty * avg + signed * fill) / new_qty
            elif (qty > 0) != (new_qty > 0):  # flipped through zero
                avg = fill
            self._positions[order.symbol] = (new_qty, avg)
        order.filled_qty = order.qty
        order.filled_avg_price = fill
        order.status = OrderStatus.FILLED

    def _process_open_orders(self) -> None:
        for o in self._orders.values():
            if o.status.is_open:
                self._try_fill(o)

    def get_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise BrokerError(f"Unknown order {order_id}")
        return self._orders[order_id]

    def list_orders(self, status: str = "open") -> list[Order]:
        orders = list(self._orders.values())
        if status == "open":
            return [o for o in orders if o.status.is_open]
        if status == "closed":
            return [o for o in orders if not o.status.is_open]
        return orders

    def cancel_order(self, order_id: str) -> None:
        order = self.get_order(order_id)
        if not order.status.is_open:
            raise BrokerError(f"Order {order_id} is not open ({order.status.value})")
        order.status = OrderStatus.CANCELED
