from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from tradelab.backtest import CostModel
from tradelab.brokers import (
    BrokerError,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    SimulatedBroker,
    TimeInForce,
    create_broker,
)
from tradelab.brokers.alpaca_paper import AlpacaPaperBroker
from tradelab.config import AlpacaCredentials, RiskSettings
from tradelab.execution import Rebalancer
from tradelab.risk import PreTradeRiskChecker


# ---------- models ----------
def test_order_request_validation():
    with pytest.raises(ValueError):
        OrderRequest("AAPL", 0, OrderSide.BUY)
    with pytest.raises(ValueError):
        OrderRequest("", 1, OrderSide.BUY)
    with pytest.raises(ValueError):
        OrderRequest("AAPL", 1, OrderSide.BUY, OrderType.LIMIT)
    with pytest.raises(ValueError):
        OrderRequest("AAPL", 1, OrderSide.BUY, OrderType.STOP)
    assert OrderRequest("AAPL", 2, OrderSide.SELL).signed_qty == -2


# ---------- simulated broker ----------
@pytest.fixture
def sim():
    return SimulatedBroker(initial_cash=10_000, prices={"AAPL": 100.0, "MSFT": 200.0})


def test_market_buy_and_sell(sim):
    o = sim.submit_order(OrderRequest("aapl", 10, OrderSide.BUY))
    assert o.status == OrderStatus.FILLED and o.filled_avg_price == 100
    assert sim.cash == 9_000
    pos = sim.get_position("AAPL")
    assert pos.qty == 10 and pos.avg_entry_price == 100
    sim.set_price("AAPL", 110)
    assert sim.get_account().equity == pytest.approx(10_100)
    assert sim.get_position("AAPL").unrealized_pl == pytest.approx(100)
    sim.close_position("AAPL")
    assert sim.get_positions() == [] and sim.cash == pytest.approx(10_100)


def test_average_price(sim):
    sim.submit_order(OrderRequest("AAPL", 10, OrderSide.BUY))
    sim.set_price("AAPL", 120)
    sim.submit_order(OrderRequest("AAPL", 10, OrderSide.BUY))
    assert sim.get_position("AAPL").avg_entry_price == pytest.approx(110)


def test_short_rejected_by_default(sim):
    o = sim.submit_order(OrderRequest("AAPL", 1, OrderSide.SELL))
    assert o.status == OrderStatus.REJECTED


def test_insufficient_cash_rejected(sim):
    assert sim.submit_order(OrderRequest("MSFT", 100, OrderSide.BUY)).status == OrderStatus.REJECTED


def test_limit_order_lifecycle(sim):
    o = sim.submit_order(OrderRequest("AAPL", 5, OrderSide.BUY, OrderType.LIMIT, limit_price=95))
    assert o.status == OrderStatus.ACCEPTED and sim.list_orders("open") == [o]
    sim.set_price("AAPL", 94)
    assert o.status == OrderStatus.FILLED and o.filled_avg_price == 94
    assert sim.list_orders("closed") == [o]


def test_stop_order_triggers(sim):
    sim.submit_order(OrderRequest("AAPL", 5, OrderSide.BUY))
    stop = sim.submit_order(OrderRequest("AAPL", 5, OrderSide.SELL, OrderType.STOP, stop_price=90))
    sim.set_price("AAPL", 95)
    assert stop.status == OrderStatus.ACCEPTED
    sim.set_price("AAPL", 89)
    assert stop.status == OrderStatus.FILLED


def test_cancel(sim):
    o = sim.submit_order(OrderRequest("AAPL", 5, OrderSide.BUY, OrderType.LIMIT, limit_price=50))
    assert sim.cancel_all_orders() == 1
    assert o.status == OrderStatus.CANCELED
    with pytest.raises(BrokerError):
        sim.cancel_order(o.id)
    with pytest.raises(BrokerError):
        sim.get_order("nope")


def test_unknown_price(sim):
    with pytest.raises(BrokerError):
        sim.get_latest_price("ZZZ")


def test_slippage_and_commission():
    b = SimulatedBroker(
        10_000, {"X": 100}, costs=CostModel(commission_per_share=1, slippage_bps=100)
    )
    o = b.submit_order(OrderRequest("X", 10, OrderSide.BUY))
    assert o.filled_avg_price == pytest.approx(101)
    assert b.cash == pytest.approx(10_000 - 1010 - 10)


def test_factory_creates_sim():
    assert isinstance(create_broker("simulated", initial_cash=5), SimulatedBroker)
    with pytest.raises(ValueError):
        create_broker("robinhood")


def test_factory_alpaca_requires_keys():
    with pytest.raises(BrokerError):
        create_broker("alpaca_paper", credentials=AlpacaCredentials(api_key="", secret_key=""))


# ---------- alpaca adapter (mocked client) ----------
class FakeAlpacaClient:
    _base_url = "https://paper-api.alpaca.markets"

    def __init__(self):
        self.submitted = []

    def get_account(self):
        return SimpleNamespace(
            account_number="PA123",
            cash="1000.5",
            equity="2000",
            buying_power="4000",
            currency="USD",
            status=SimpleNamespace(value="ACTIVE"),
        )

    def get_all_positions(self):
        return [
            SimpleNamespace(
                symbol="AAPL", qty="3", avg_entry_price="100", current_price="110", side="long"
            ),
            SimpleNamespace(
                symbol="TSLA",
                qty="2",
                avg_entry_price="200",
                current_price="190",
                side=SimpleNamespace(value="short"),
            ),
        ]

    def _order(self, req, status="accepted"):
        return SimpleNamespace(
            id="abc",
            symbol=req.symbol,
            qty=str(req.qty),
            side=req.side,
            order_type=req.type,
            time_in_force=req.time_in_force,
            status=status,
            limit_price=getattr(req, "limit_price", None),
            stop_price=getattr(req, "stop_price", None),
            filled_qty="0",
            filled_avg_price=None,
            client_order_id=None,
            submitted_at=datetime.now(timezone.utc),
        )

    def submit_order(self, req):
        self.submitted.append(req)
        return self._order(req)

    def get_clock(self):
        return SimpleNamespace(is_open=False)

    def get_orders(self, filter):
        from alpaca.trading.requests import MarketOrderRequest

        return [
            self._order(
                MarketOrderRequest(symbol="AAPL", qty=1, side="buy", time_in_force="day"), "filled"
            )
        ]

    def cancel_order_by_id(self, oid):
        self.canceled = oid


def test_alpaca_mapping():
    client = FakeAlpacaClient()
    b = AlpacaPaperBroker(trading_client=client)
    acct = b.get_account()
    assert (
        acct.is_paper
        and acct.cash == 1000.5
        and acct.account_id == "PA123"
        and acct.status == "active"
    )
    pos = {p.symbol: p for p in b.get_positions()}
    assert pos["AAPL"].qty == 3 and pos["TSLA"].qty == -2
    assert b.is_market_open() is False
    orders = b.list_orders("closed")
    assert orders[0].status == OrderStatus.FILLED


@pytest.mark.parametrize(
    "req,cls",
    [
        (OrderRequest("AAPL", 1.5, OrderSide.BUY), "MarketOrderRequest"),
        (
            OrderRequest(
                "AAPL", 1, OrderSide.SELL, OrderType.LIMIT, TimeInForce.GTC, limit_price=150
            ),
            "LimitOrderRequest",
        ),
        (
            OrderRequest("AAPL", 1, OrderSide.SELL, OrderType.STOP, stop_price=90),
            "StopOrderRequest",
        ),
        (
            OrderRequest(
                "AAPL", 1, OrderSide.BUY, OrderType.STOP_LIMIT, limit_price=101, stop_price=100
            ),
            "StopLimitOrderRequest",
        ),
    ],
)
def test_alpaca_order_translation(req, cls):
    client = FakeAlpacaClient()
    o = AlpacaPaperBroker(trading_client=client).submit_order(req)
    sent = client.submitted[0]
    assert type(sent).__name__ == cls
    assert o.symbol == "AAPL" and o.side == req.side and o.status == OrderStatus.ACCEPTED
    assert o.order_type == req.order_type and o.broker == "alpaca_paper"


def test_alpaca_errors_wrapped():
    client = FakeAlpacaClient()
    client.submit_order = lambda req: (_ for _ in ()).throw(
        RuntimeError("insufficient buying power")
    )
    with pytest.raises(BrokerError, match="insufficient"):
        AlpacaPaperBroker(trading_client=client).submit_order(
            OrderRequest("AAPL", 1, OrderSide.BUY)
        )


# ---------- risk checks + rebalancer ----------
def test_pre_trade_checks():
    c = PreTradeRiskChecker(RiskSettings(max_order_notional=1000, max_position_weight=0.2))
    assert c.check_order("A", 5, 100, 10_000).approved
    r = c.check_order("A", 30, 100, 10_000)
    assert (
        not r.approved
        and any("notional" in x for x in r.reasons)
        and any("weight" in x for x in r.reasons)
    )
    assert not c.check_order("A", -1, 100, 10_000).approved  # short
    assert not c.check_order("A", 1, 100, 0).approved


def test_rebalancer_plan_and_execute():
    b = SimulatedBroker(10_000, {"A": 100, "B": 50, "C": 10})
    b.submit_order(OrderRequest("C", 100, OrderSide.BUY))
    risk = RiskSettings(max_position_weight=0.5, max_order_notional=100_000)
    rb = Rebalancer(b, risk)
    plan = rb.plan(pd.Series({"A": 0.3, "B": 0.6}))
    df = plan.to_frame().set_index("symbol")
    assert df.loc["C", "side"] == "sell" and df.loc["C", "qty"] == 100  # not in target -> exit
    assert not df.loc["B", "approved"]  # 60% > 50% cap
    assert df.loc["A", "approved"] and df.loc["A", "qty"] == pytest.approx(30)
    assert plan.proposed[0].side == OrderSide.SELL  # sells first
    rb.execute(plan)
    assert {o.symbol for o in plan.submitted} == {"A", "C"}
    assert b.get_position("A").qty == pytest.approx(30) and b.get_position("C") is None


def test_rebalancer_order_cap():
    b = SimulatedBroker(10_000, {s: 10.0 for s in "ABCD"})
    plan = Rebalancer(b, RiskSettings(max_orders_per_run=2)).plan(
        pd.Series(dict.fromkeys("ABCD", 0.2))
    )
    assert sum(p.approved for p in plan.proposed) == 2


def test_rebalancer_whole_shares():
    b = SimulatedBroker(1_000, {"A": 300})
    plan = Rebalancer(
        b, RiskSettings(max_position_weight=1, max_order_notional=1e9), fractional=False
    ).plan(pd.Series({"A": 1.0}))
    assert plan.proposed[0].qty == 3


def test_pre_trade_limit_boundary_is_inclusive_under_float_error():
    from tradelab.config import RiskSettings
    from tradelab.risk.limits import PreTradeRiskChecker

    c = PreTradeRiskChecker(RiskSettings(max_order_notional=25_000, max_position_weight=0.25))
    price, equity = 137.13, 100_000.0
    qty = 0.25 * equity / price  # notional == 25,000 up to float rounding
    assert c.check_order("X", qty, price, equity).approved


def test_simulated_rejections_carry_reason():
    from tradelab.brokers import OrderRequest, OrderSide, SimulatedBroker

    b = SimulatedBroker(initial_cash=100)
    b.set_price("A", 50)
    short = b.submit_order(OrderRequest("A", 1, OrderSide.SELL))
    assert short.status.value == "rejected" and "shorting disabled" in short.reject_reason
    broke = b.submit_order(OrderRequest("A", 10, OrderSide.BUY))
    assert broke.status.value == "rejected" and "insufficient cash" in broke.reject_reason
