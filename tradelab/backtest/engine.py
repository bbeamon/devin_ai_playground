"""Portfolio backtester driven by target weights.

Timing (no look-ahead): weights for bar ``t`` are computed from data up to the close of
``t``. With ``execution="next_open"`` (default) they are filled at the open of ``t+1``;
with ``execution="close"`` they are filled at the close of ``t`` (optimistic).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from tradelab.backtest.costs import CostModel
from tradelab.config import BacktestSettings, RiskSettings
from tradelab.risk.metrics import summarize


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    positions: pd.DataFrame
    weights: pd.DataFrame
    target_weights: pd.DataFrame
    trades: pd.DataFrame
    cash: pd.Series
    benchmark_returns: pd.Series | None = None
    signals: pd.DataFrame | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    risk_free_rate: float = 0.0

    @property
    def metrics(self) -> dict[str, Any]:
        return summarize(
            self.returns,
            benchmark=self.benchmark_returns,
            risk_free=self.risk_free_rate,
            weights=self.weights,
            trades=self.trades,
        )


TRADE_COLUMNS = [
    "date",
    "symbol",
    "side",
    "qty",
    "price",
    "fill_price",
    "notional",
    "commission",
    "slippage_cost",
]


class Backtester:
    def __init__(
        self, settings: BacktestSettings | None = None, risk: RiskSettings | None = None
    ) -> None:
        self.settings = settings or BacktestSettings()
        self.risk = risk or RiskSettings()
        self.costs = CostModel.from_settings(self.settings)

    def run(
        self,
        data: dict[str, pd.DataFrame],
        target_weights: pd.DataFrame,
        benchmark: pd.Series | None = None,
        signals: pd.DataFrame | None = None,
    ) -> BacktestResult:
        s = self.settings
        symbols = list(target_weights.columns)
        missing = [sym for sym in symbols if sym not in data]
        if missing:
            raise KeyError(f"Missing price data for {missing}")
        index = target_weights.index
        opens = pd.DataFrame({k: data[k]["open"] for k in symbols}).reindex(index)
        closes = pd.DataFrame({k: data[k]["close"] for k in symbols}).reindex(index)
        tw = target_weights.fillna(0.0)
        if not s.allow_short:
            tw = tw.clip(lower=0.0)

        o, c, w = opens.to_numpy(float), closes.to_numpy(float), tw.to_numpy(float)
        n, m = c.shape
        shares = np.zeros(m)
        cash = float(s.initial_cash)
        equity_hist = np.empty(n)
        cash_hist = np.empty(n)
        pos_hist = np.zeros((n, m))
        trades: list[dict[str, Any]] = []
        last_close: np.ndarray = np.full(m, np.nan)

        def rebalance(i: int, target: np.ndarray, px: np.ndarray) -> None:
            nonlocal cash
            valuation = np.where(np.isnan(px), last_close, px)
            held = np.nan_to_num(shares * valuation)
            equity = cash + held.sum()
            if equity <= 0:
                return
            for j in range(m):
                price = px[j]
                if np.isnan(price) or price <= 0:
                    continue
                current_w = shares[j] * price / equity
                full_exit = target[j] == 0 and shares[j] != 0
                if not full_exit and abs(target[j] - current_w) < s.rebalance_threshold:
                    continue
                desired = target[j] * equity / price
                if not s.fractional_shares:
                    desired = float(np.trunc(desired))
                delta = desired - shares[j]
                if abs(delta * price) < max(self.risk.min_trade_notional, 1e-9):
                    continue
                fill = self.costs.fill_price(price, delta)
                fee = self.costs.commission(delta, fill)
                cash -= delta * fill + fee
                shares[j] += delta
                trades.append(
                    {
                        "date": index[i],
                        "symbol": symbols[j],
                        "side": "buy" if delta > 0 else "sell",
                        "qty": abs(delta),
                        "price": price,
                        "fill_price": fill,
                        "notional": abs(delta) * fill,
                        "commission": fee,
                        "slippage_cost": abs(delta) * abs(fill - price),
                    }
                )

        for i in range(n):
            if s.execution == "next_open" and i > 0:
                rebalance(i, w[i - 1], o[i])
            elif s.execution == "close":
                rebalance(i, w[i], c[i])
            last_close = np.where(np.isnan(c[i]), last_close, c[i])
            equity_hist[i] = cash + np.nansum(shares * last_close)
            cash_hist[i] = cash
            pos_hist[i] = shares

        equity = pd.Series(equity_hist, index=index, name="equity")
        returns = equity.pct_change().fillna(0.0).rename("returns")
        positions = pd.DataFrame(pos_hist, index=index, columns=symbols)
        held_value = positions * closes.ffill().fillna(0.0)
        weights = held_value.div(equity.replace(0, np.nan), axis=0).fillna(0.0)
        bench = None
        if benchmark is not None:
            bench = benchmark.reindex(index).pct_change(fill_method=None).fillna(0.0)
            bench.name = "benchmark"
        return BacktestResult(
            equity=equity,
            returns=returns,
            positions=positions,
            weights=weights,
            target_weights=tw,
            trades=pd.DataFrame(trades, columns=TRADE_COLUMNS),
            cash=pd.Series(cash_hist, index=index, name="cash"),
            benchmark_returns=bench,
            signals=signals,
            metadata={"settings": s.model_dump()},
            risk_free_rate=self.risk.risk_free_rate,
        )
