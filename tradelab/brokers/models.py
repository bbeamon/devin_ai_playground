"""Broker-agnostic domain models shared by every broker adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class OrderStatus(str, Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    PENDING = "pending"

    @property
    def is_open(self) -> bool:
        return self in {
            OrderStatus.NEW,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.PENDING,
        }


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    OPTION = "option"
    FUTURE = "future"
    CRYPTO = "crypto"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    qty: float
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: float | None = None
    stop_price: float | None = None
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol is required")
        if self.qty <= 0:
            raise ValueError("qty must be positive (use side to express direction)")
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and not self.limit_price:
            raise ValueError(f"{self.order_type.value} orders require limit_price")
        if self.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and not self.stop_price:
            raise ValueError(f"{self.order_type.value} orders require stop_price")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError("limit_price must be positive")
        if self.stop_price is not None and self.stop_price <= 0:
            raise ValueError("stop_price must be positive")

    @property
    def signed_qty(self) -> float:
        return self.qty if self.side == OrderSide.BUY else -self.qty


@dataclass
class Order:
    id: str
    symbol: str
    qty: float
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce
    status: OrderStatus
    limit_price: float | None = None
    stop_price: float | None = None
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    client_order_id: str | None = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    broker: str = ""
    reject_reason: str | None = None


@dataclass
class Position:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    asset_class: AssetClass = AssetClass.EQUITY

    @property
    def market_value(self) -> float:
        return self.qty * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_entry_price

    @property
    def unrealized_pl(self) -> float:
        return self.market_value - self.cost_basis


@dataclass
class Account:
    account_id: str
    cash: float
    equity: float
    buying_power: float
    currency: str = "USD"
    is_paper: bool = True
    broker: str = ""
    status: str = "active"


@dataclass(frozen=True)
class BrokerCapabilities:
    paper_trading: bool
    fractional_shares: bool = False
    short_selling: bool = False
    order_types: frozenset[OrderType] = frozenset({OrderType.MARKET, OrderType.LIMIT})
    asset_classes: frozenset[AssetClass] = frozenset({AssetClass.EQUITY, AssetClass.ETF})
    implemented: bool = True
    notes: str = ""
