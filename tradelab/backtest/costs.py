"""Transaction cost model."""

from __future__ import annotations

from dataclasses import dataclass

from tradelab.config import BacktestSettings


@dataclass(frozen=True)
class CostModel:
    commission_per_share: float = 0.0
    commission_pct: float = 0.0
    min_commission: float = 0.0
    slippage_bps: float = 0.0

    @classmethod
    def from_settings(cls, s: BacktestSettings) -> CostModel:
        return cls(s.commission_per_share, s.commission_pct, s.min_commission, s.slippage_bps)

    def fill_price(self, price: float, qty: float) -> float:
        """Adverse slippage: buys fill higher, sells fill lower."""
        sign = 1.0 if qty > 0 else -1.0
        return price * (1 + sign * self.slippage_bps / 10_000)

    def commission(self, qty: float, fill_price: float) -> float:
        if qty == 0:
            return 0.0
        fee = abs(qty) * self.commission_per_share + abs(qty) * fill_price * self.commission_pct
        return max(fee, self.min_commission)
