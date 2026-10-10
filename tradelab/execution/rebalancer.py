"""Turn strategy target weights into (paper) broker orders, with pre-trade risk checks."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from tradelab.brokers.base import Broker, BrokerError
from tradelab.brokers.models import Order, OrderRequest, OrderSide
from tradelab.config import RiskSettings
from tradelab.risk.limits import PreTradeRiskChecker
from tradelab.safety import assert_paper_broker


@dataclass
class ProposedOrder:
    symbol: str
    side: OrderSide
    qty: float
    price: float
    current_qty: float
    target_weight: float
    approved: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def notional(self) -> float:
        return self.qty * self.price


@dataclass
class RebalanceReport:
    equity: float
    proposed: list[ProposedOrder]
    submitted: list[Order] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "qty": p.qty,
                    "price": p.price,
                    "notional": p.notional,
                    "current_qty": p.current_qty,
                    "target_weight": p.target_weight,
                    "approved": p.approved,
                    "reasons": "; ".join(p.reasons),
                }
                for p in self.proposed
            ]
        )


class Rebalancer:
    def __init__(
        self,
        broker: Broker,
        risk: RiskSettings | None = None,
        allow_short: bool = False,
        fractional: bool | None = None,
    ) -> None:
        assert_paper_broker(broker)
        self.broker = broker
        self.risk = risk or RiskSettings()
        self.checker = PreTradeRiskChecker(self.risk)
        self.allow_short = allow_short
        self.fractional = (
            broker.capabilities.fractional_shares if fractional is None else fractional
        )

    def plan(
        self, target_weights: pd.Series, prices: dict[str, float] | None = None
    ) -> RebalanceReport:
        account = self.broker.get_account()
        equity = account.equity
        positions = {p.symbol: p for p in self.broker.get_positions()}
        symbols = sorted(set(target_weights.index.str.upper()) | set(positions))
        tw = target_weights.copy()
        tw.index = tw.index.str.upper()
        proposed: list[ProposedOrder] = []
        for sym in symbols:
            target = float(tw.get(sym, 0.0))
            pos = positions.get(sym)
            current_qty = pos.qty if pos else 0.0
            price = (prices or {}).get(sym) or (pos.current_price if pos else None)
            if not price:
                price = self.broker.get_latest_price(sym)
            desired = target * equity / price
            if not self.fractional:
                desired = float(math.trunc(desired))
            delta = round(desired - current_qty, 6)
            if abs(delta) * price < max(self.risk.min_trade_notional, 1e-9):
                continue
            check = self.checker.check_order(
                sym, delta, price, equity, current_qty, allow_short=self.allow_short
            )
            proposed.append(
                ProposedOrder(
                    symbol=sym,
                    side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                    qty=abs(delta),
                    price=price,
                    current_qty=current_qty,
                    target_weight=target,
                    approved=check.approved,
                    reasons=check.reasons,
                )
            )
        # Sells first so buys have cash available.
        proposed.sort(key=lambda p: (p.side != OrderSide.SELL, p.symbol))
        if len(proposed) > self.risk.max_orders_per_run:
            for p in proposed[self.risk.max_orders_per_run :]:
                p.approved = False
                p.reasons.append("exceeds max_orders_per_run")
        return RebalanceReport(equity=equity, proposed=proposed)

    def execute(self, report: RebalanceReport) -> RebalanceReport:
        assert_paper_broker(self.broker)
        for p in report.proposed:
            if not p.approved:
                continue
            try:
                order = self.broker.submit_order(
                    OrderRequest(symbol=p.symbol, qty=p.qty, side=p.side)
                )
                report.submitted.append(order)
            except (BrokerError, ValueError) as exc:
                report.errors.append(f"{p.symbol}: {exc}")
        return report
