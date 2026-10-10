"""Alpaca **paper** trading adapter (alpaca-py).

The underlying ``TradingClient`` is always created with ``paper=True`` and its base URL is
verified against the paper endpoint. There is intentionally no option to point this
adapter at a live account.
"""

from __future__ import annotations

from typing import Any

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
    TimeInForce,
)
from tradelab.safety import assert_alpaca_paper_url, check_alpaca_paper_key

_STATUS_MAP = {
    "new": OrderStatus.NEW,
    "accepted": OrderStatus.ACCEPTED,
    "pending_new": OrderStatus.PENDING,
    "accepted_for_bidding": OrderStatus.PENDING,
    "held": OrderStatus.PENDING,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "done_for_day": OrderStatus.EXPIRED,
    "canceled": OrderStatus.CANCELED,
    "pending_cancel": OrderStatus.PENDING,
    "expired": OrderStatus.EXPIRED,
    "replaced": OrderStatus.CANCELED,
    "rejected": OrderStatus.REJECTED,
    "suspended": OrderStatus.REJECTED,
    "stopped": OrderStatus.FILLED,
}


def _val(x: Any) -> str:
    return str(getattr(x, "value", x)).lower()


def _f(x: Any, default: float = 0.0) -> float:
    return float(x) if x not in (None, "") else default


class AlpacaPaperBroker(Broker):
    name = "alpaca_paper"
    capabilities = BrokerCapabilities(
        paper_trading=True,
        fractional_shares=True,
        short_selling=True,
        order_types=frozenset(OrderType),
        asset_classes=frozenset({AssetClass.EQUITY, AssetClass.ETF}),
        notes="Alpaca paper account via alpaca-py. Fractional orders must be DAY market/limit.",
    )

    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        trading_client: Any | None = None,
        data_client: Any | None = None,
        data_feed: str = "iex",
    ) -> None:
        if trading_client is None:
            if not (api_key and secret_key):
                raise BrokerError(
                    "Alpaca paper trading requires ALPACA_API_KEY and ALPACA_SECRET_KEY "
                    "(paper-account keys). See .env.example."
                )
            check_alpaca_paper_key(api_key)
            from alpaca.trading.client import TradingClient

            trading_client = TradingClient(api_key, secret_key, paper=True)
        base = getattr(trading_client, "_base_url", None)
        if base is not None:
            assert_alpaca_paper_url(str(getattr(base, "value", base)))
        self._client: Any = trading_client
        self._data_client: Any = data_client
        self._api_key, self._secret_key = api_key, secret_key
        self._data_feed = data_feed

    @property
    def is_paper(self) -> bool:
        return True

    # ---- mapping helpers ----
    @staticmethod
    def _to_order(o: Any) -> Order:
        otype = _val(getattr(o, "order_type", None) or getattr(o, "type", "market"))
        return Order(
            id=str(o.id),
            symbol=o.symbol,
            qty=_f(o.qty),
            side=OrderSide(_val(o.side)),
            order_type=OrderType(otype)
            if otype in OrderType._value2member_map_
            else OrderType.MARKET,
            time_in_force=TimeInForce(_val(o.time_in_force))
            if _val(o.time_in_force) in TimeInForce._value2member_map_
            else TimeInForce.DAY,
            status=_STATUS_MAP.get(_val(o.status), OrderStatus.PENDING),
            limit_price=_f(o.limit_price) if o.limit_price is not None else None,
            stop_price=_f(o.stop_price) if o.stop_price is not None else None,
            filled_qty=_f(o.filled_qty),
            filled_avg_price=_f(o.filled_avg_price) if o.filled_avg_price is not None else None,
            client_order_id=o.client_order_id,
            submitted_at=o.submitted_at,
            broker="alpaca_paper",
        )

    # ---- Broker API ----
    def get_account(self) -> Account:
        a = self._client.get_account()
        return Account(
            account_id=str(a.account_number),
            cash=_f(a.cash),
            equity=_f(a.equity),
            buying_power=_f(a.buying_power),
            currency=a.currency or "USD",
            is_paper=True,
            broker=self.name,
            status=_val(a.status),
        )

    def get_positions(self) -> list[Position]:
        out = []
        for p in self._client.get_all_positions():
            qty = _f(p.qty)
            if _val(getattr(p, "side", "long")) == "short" and qty > 0:
                qty = -qty
            out.append(
                Position(
                    symbol=p.symbol,
                    qty=qty,
                    avg_entry_price=_f(p.avg_entry_price),
                    current_price=_f(p.current_price),
                )
            )
        return out

    def get_latest_price(self, symbol: str) -> float:
        if self._data_client is None:
            from alpaca.data.historical import StockHistoricalDataClient

            self._data_client = StockHistoricalDataClient(self._api_key, self._secret_key)
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockLatestTradeRequest

        req = StockLatestTradeRequest(
            symbol_or_symbols=symbol.upper(), feed=DataFeed(self._data_feed)
        )
        trades = self._data_client.get_stock_latest_trade(req)
        return float(trades[symbol.upper()].price)

    def is_market_open(self) -> bool:
        return bool(self._client.get_clock().is_open)

    def _submit_order(self, request: OrderRequest) -> Order:
        from alpaca.trading import requests as rq
        from alpaca.trading.enums import OrderSide as ASide
        from alpaca.trading.enums import TimeInForce as ATif

        common: dict[str, Any] = {
            "symbol": request.symbol.upper(),
            "qty": request.qty,
            "side": ASide(request.side.value),
            "time_in_force": ATif(request.time_in_force.value),
            "client_order_id": request.client_order_id,
        }
        t = request.order_type
        req: Any
        if t == OrderType.MARKET:
            req = rq.MarketOrderRequest(**common)
        elif t == OrderType.LIMIT:
            req = rq.LimitOrderRequest(**common, limit_price=request.limit_price)
        elif t == OrderType.STOP:
            req = rq.StopOrderRequest(**common, stop_price=request.stop_price)
        else:
            req = rq.StopLimitOrderRequest(
                **common, limit_price=request.limit_price, stop_price=request.stop_price
            )
        try:
            return self._to_order(self._client.submit_order(req))
        except Exception as exc:
            raise BrokerError(f"Alpaca rejected order: {exc}") from exc

    def get_order(self, order_id: str) -> Order:
        return self._to_order(self._client.get_order_by_id(order_id))

    def list_orders(self, status: str = "open") -> list[Order]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        req = GetOrdersRequest(status=QueryOrderStatus(status), limit=500)
        return [self._to_order(o) for o in self._client.get_orders(filter=req)]

    def cancel_order(self, order_id: str) -> None:
        self._client.cancel_order_by_id(order_id)
