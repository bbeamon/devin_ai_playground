import datetime as dt

import _common
import pandas as pd
import streamlit as st

from tradelab.brokers import (
    BrokerError,
    OrderRequest,
    OrderSide,
    OrderType,
    SimulatedBroker,
    create_broker,
)
from tradelab.config import AlpacaCredentials
from tradelab.execution import Rebalancer
from tradelab.safety import LiveTradingDisabledError
from tradelab.strategies import StrategyConfig, StrategyEngine, list_strategies
from tradelab.ui import charts

st.set_page_config(page_title="Paper Trading", layout="wide")
_common.page_header("Paper Trading", "Simulator or Alpaca paper account. No real money.")
st.warning(_common.PAPER_BANNER)


def flash(level: str, msg: str) -> None:
    st.session_state.setdefault("paper_flash", []).append((level, msg))


for level, msg in st.session_state.pop("paper_flash", []):
    getattr(st, level)(msg)

settings = _common.get_settings()
broker_name = st.sidebar.selectbox(
    "Broker", ["simulated", "alpaca_paper", "ibkr", "schwab", "fidelity"]
)
_common.mobile_bar(f"Broker: **{broker_name}** (paper only)")


def get_broker():
    key = f"broker_{broker_name}"
    if key not in st.session_state:
        if broker_name == "simulated":
            st.session_state[key] = SimulatedBroker(initial_cash=settings.backtest.initial_cash)
        else:
            st.session_state[key] = create_broker(broker_name, settings.broker, AlpacaCredentials())
    return st.session_state[key]


try:
    broker = get_broker()
except (BrokerError, LiveTradingDisabledError, ValueError) as exc:
    st.error(str(exc))
    if broker_name == "alpaca_paper":
        st.info(
            "Set ALPACA_API_KEY / ALPACA_SECRET_KEY (paper keys) in a .env file at the repo root, then reload."
        )
    st.stop()

caps = broker.capabilities
if not caps.implemented:
    st.info(f"**{broker_name}** is a planned integration (stub). {caps.notes}")
    st.stop()

if isinstance(broker, SimulatedBroker):
    st.caption("Simulator prices come from the latest close of the selected data provider.")

try:
    acct = broker.get_account()
except Exception as exc:  # noqa: BLE001 - surface any connectivity problem
    st.error(f"Could not fetch account: {exc}")
    st.stop()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Equity", f"${acct.equity:,.2f}")
c2.metric("Cash", f"${acct.cash:,.2f}")
c3.metric("Buying power", f"${acct.buying_power:,.2f}")
c4.metric("Mode", "PAPER" if acct.is_paper else "UNKNOWN")

st.subheader("Positions")
positions = broker.get_positions()
st.dataframe(
    pd.DataFrame(
        [
            {**p.__dict__, "market_value": p.market_value, "unrealized_pl": p.unrealized_pl}
            for p in positions
        ]
    ),
    use_container_width=True,
)
if positions:
    mv = pd.Series({p.symbol: p.market_value for p in positions})
    mv["Cash"] = max(0.0, acct.cash)
    _common.plot(charts.allocation_donut(mv, "Account allocation by market value"))

st.subheader("Strategy rebalance")
names = list(list_strategies())
c1, c2, c3 = st.columns(3)
strat = c1.selectbox("Strategy", names, index=names.index("sma_crossover"))
universe = _common.parse_symbols(c2.text_input("Universe", "AAPL, MSFT, NVDA, GOOGL"))
provider = c3.selectbox("Signal data provider", _common.PROVIDERS)
if st.button("Compute target portfolio"):
    try:
        cfg = (
            StrategyConfig(name=strat, strategy=strat, universe=universe, benchmark=None)
            if strat != "ensemble"
            else StrategyConfig.from_yaml(
                _common.ROOT / "config/strategies/ensemble.yaml"
            ).model_copy(update={"universe": universe})
        )
        data = _common.safe_load(
            provider, universe, dt.date.today() - dt.timedelta(days=500), dt.date.today()
        )
        if data:
            engine = StrategyEngine(cfg, settings.risk, allow_short=False)
            target = engine.latest_target_weights(data)
            prices = {s: float(df["close"].iloc[-1]) for s, df in data.items()}
            if isinstance(broker, SimulatedBroker):
                for s, p in prices.items():
                    broker.set_price(s, p)
            report = Rebalancer(broker, settings.risk).plan(
                target, prices if isinstance(broker, SimulatedBroker) else None
            )
            st.session_state["plan"] = report
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not compute plan: {exc}")

report = st.session_state.get("plan")
if report is not None:
    st.dataframe(report.to_frame(), use_container_width=True)
    confirm = st.checkbox("I confirm these orders go to a PAPER account")
    if st.button("Submit approved orders", type="primary", disabled=not confirm):
        Rebalancer(broker, settings.risk).execute(report)
        for o in report.submitted:
            if o.status.value == "rejected":
                flash("error", f"{o.side.value} {o.qty:g} {o.symbol}: rejected - {o.reject_reason}")
            else:
                flash("success", f"{o.side.value} {o.qty:g} {o.symbol}: {o.status.value}")
        for e in report.errors:
            flash("error", e)
        st.session_state.pop("plan")
        st.rerun()

st.subheader("Manual order")
with st.form("manual"):
    c1, c2, c3, c4, c5 = st.columns(5)
    sym = c1.text_input("Symbol", "AAPL").upper()
    side = c2.selectbox("Side", [s.value for s in OrderSide])
    qty = c3.number_input("Qty", min_value=0.0, value=1.0)
    otype = c4.selectbox("Type", [t.value for t in OrderType if t in caps.order_types])
    limit = c5.number_input("Limit/stop price", min_value=0.0, value=0.0)
    if st.form_submit_button("Submit paper order"):
        try:
            if isinstance(broker, SimulatedBroker):
                try:
                    broker.get_latest_price(sym)
                except BrokerError:
                    d = _common.safe_load(
                        provider, [sym], dt.date.today() - dt.timedelta(days=10), dt.date.today()
                    )
                    if d:
                        broker.set_price(sym, float(d[sym]["close"].iloc[-1]))
            t = OrderType(otype)
            req = OrderRequest(
                sym,
                qty,
                OrderSide(side),
                t,
                limit_price=limit or None if t in (OrderType.LIMIT, OrderType.STOP_LIMIT) else None,
                stop_price=limit or None if t in (OrderType.STOP, OrderType.STOP_LIMIT) else None,
            )
            o = broker.submit_order(req)
        except (BrokerError, ValueError, LiveTradingDisabledError) as exc:
            st.error(str(exc))
        else:
            if o.status.value == "rejected":
                flash("error", f"Order {o.id} rejected: {o.reject_reason or 'see broker'}")
            else:
                flash("success", f"Order {o.id}: {o.status.value}")
            st.rerun()

st.subheader("Orders")
orders = broker.list_orders("all")
st.dataframe(pd.DataFrame([o.__dict__ for o in orders]), use_container_width=True)
if st.button("Cancel all open orders"):
    flash("info", f"Canceled {broker.cancel_all_orders()} orders")
    st.rerun()
