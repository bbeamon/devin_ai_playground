"""Pre-trade risk checks applied before any (paper) order is submitted."""

from __future__ import annotations

from dataclasses import dataclass, field

from tradelab.config import RiskSettings


@dataclass
class RiskCheckResult:
    approved: bool
    reasons: list[str] = field(default_factory=list)


class PreTradeRiskChecker:
    def __init__(self, settings: RiskSettings | None = None) -> None:
        self.settings = settings or RiskSettings()

    def check_order(
        self,
        symbol: str,
        qty: float,
        price: float,
        equity: float,
        current_qty: float = 0.0,
        allow_short: bool = False,
    ) -> RiskCheckResult:
        s = self.settings
        reasons: list[str] = []
        notional = abs(qty) * price
        if qty == 0:
            reasons.append("zero quantity")
        if price <= 0:
            reasons.append("non-positive price")
        if notional > s.max_order_notional:
            reasons.append(
                f"order notional ${notional:,.2f} exceeds max ${s.max_order_notional:,.2f}"
            )
        new_qty = current_qty + qty
        if not allow_short and new_qty < -1e-9:
            reasons.append("order would create a short position (shorting disabled)")
        if equity > 0:
            new_weight = abs(new_qty) * price / equity
            if new_weight > s.max_position_weight + 1e-9:
                reasons.append(
                    f"resulting position weight {new_weight:.1%} exceeds max "
                    f"{s.max_position_weight:.1%}"
                )
        else:
            reasons.append("account equity is not positive")
        return RiskCheckResult(approved=not reasons, reasons=reasons)
