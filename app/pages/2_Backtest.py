import datetime as dt
import json

import _common
import streamlit as st
import yaml
from pydantic import ValidationError

from tradelab.backtest import run_backtest
from tradelab.config import BacktestSettings, Settings
from tradelab.strategies import StrategyConfig, list_strategies
from tradelab.ui import charts

st.set_page_config(page_title="Backtest", layout="wide")
st.title("Backtest")

base = _common.get_settings()
mode = st.sidebar.radio("Configure via", ["Form", "YAML"], horizontal=True)
provider = st.sidebar.selectbox(
    "Data provider", _common.PROVIDERS, index=_common.PROVIDERS.index(base.data.provider)
)

cfg: StrategyConfig | None = None
if mode == "Form":
    strategies = list_strategies()
    names = [n for n in strategies if n != "ensemble"]
    name = st.sidebar.selectbox("Strategy", names, index=names.index("sma_crossover"))
    st.sidebar.caption(strategies[name].description)
    schema = strategies[name].param_schema().get("properties", {})
    params = {}
    for pname, spec in schema.items():
        default = spec.get("default")
        if spec.get("type") == "boolean":
            params[pname] = st.sidebar.checkbox(pname, value=bool(default))
        elif spec.get("type") == "integer":
            params[pname] = int(st.sidebar.number_input(pname, value=int(default), step=1))
        elif spec.get("type") == "number":
            params[pname] = float(st.sidebar.number_input(pname, value=float(default)))
    universe = _common.parse_symbols(st.sidebar.text_area("Universe", "AAPL, MSFT, NVDA, GOOGL"))
    c1, c2 = st.sidebar.columns(2)
    start = c1.date_input("Start", value=dt.date(2018, 1, 1))
    end = c2.date_input("End")
    benchmark = st.sidebar.text_input("Benchmark", "SPY").strip().upper() or None
    sizing = st.sidebar.selectbox("Sizing", ["equal_weight", "vol_target", "fixed_fraction"])
    sizing_cfg: dict = {"method": sizing}
    if sizing == "vol_target":
        sizing_cfg["target_vol"] = st.sidebar.slider("Target vol", 0.02, 0.40, 0.10, 0.01)
    if sizing == "fixed_fraction":
        sizing_cfg["fraction"] = st.sidebar.slider("Fraction per asset", 0.01, 1.0, 0.10, 0.01)
    try:
        cfg = StrategyConfig(
            name=name,
            strategy=name,
            params=params,
            universe=universe,
            start=start,
            end=end,
            benchmark=benchmark,
            sizing=sizing_cfg,
        )
    except ValidationError as exc:
        st.error(f"Invalid configuration: {exc}")
else:
    examples = sorted((_common.ROOT / "config" / "strategies").glob("*.yaml"))
    choice = st.sidebar.selectbox("Load example", [p.name for p in examples])
    text = st.text_area(
        "Strategy YAML", (_common.ROOT / "config" / "strategies" / choice).read_text(), height=320
    )
    try:
        cfg = StrategyConfig.model_validate(yaml.safe_load(text))
    except (ValidationError, yaml.YAMLError) as exc:
        st.error(f"Invalid YAML configuration: {exc}")

with st.sidebar.expander("Execution & costs"):
    bt = base.backtest
    initial_cash = st.number_input("Initial cash", value=float(bt.initial_cash), step=10_000.0)
    slippage = st.number_input("Slippage (bps)", value=float(bt.slippage_bps), step=1.0)
    commission_pct = (
        st.number_input(
            "Commission (% of notional)", value=float(bt.commission_pct * 100), step=0.01
        )
        / 100
    )
    execution = st.selectbox(
        "Execution", ["next_open", "close"], index=["next_open", "close"].index(bt.execution)
    )
    allow_short = st.checkbox("Allow short", value=bt.allow_short)
    threshold = st.number_input(
        "Rebalance threshold (weight)",
        value=float(bt.rebalance_threshold),
        step=0.005,
        format="%.3f",
    )
with st.sidebar.expander("Risk limits"):
    rk = base.risk
    max_pos = st.slider("Max position weight", 0.05, 1.0, float(rk.max_position_weight), 0.05)
    max_gross = st.slider("Max gross leverage", 0.1, 2.0, float(rk.max_gross_leverage), 0.1)

if cfg is not None and st.sidebar.button("Run backtest", type="primary"):
    settings = Settings(
        data=base.data,
        backtest=BacktestSettings(
            **{
                **bt.model_dump(),
                "initial_cash": initial_cash,
                "slippage_bps": slippage,
                "commission_pct": commission_pct,
                "execution": execution,
                "allow_short": allow_short,
                "rebalance_threshold": threshold,
            }
        ),
        risk=rk.model_copy(
            update={"max_position_weight": max_pos, "max_gross_leverage": max_gross}
        ),
        broker=base.broker,
    )
    symbols = cfg.universe + (
        [cfg.benchmark] if cfg.benchmark and cfg.benchmark not in cfg.universe else []
    )
    data = _common.safe_load(
        provider, symbols, cfg.start or dt.date(2010, 1, 1), cfg.end or dt.date.today()
    )
    if data:
        bench = data[cfg.benchmark]["close"] if cfg.benchmark else None
        try:
            with st.spinner("Running backtest..."):
                result = run_backtest(
                    cfg, settings, data={s: data[s] for s in cfg.universe}, benchmark=bench
                )
            st.session_state["last_result"] = result
            st.session_state["last_data"] = data
        except (ValueError, KeyError) as exc:
            st.error(f"Backtest failed: {exc}")

result = st.session_state.get("last_result")
if result is None:
    st.info("Configure a strategy in the sidebar and click **Run backtest**.")
    st.stop()

meta = result.metadata.get("strategy", {})
st.subheader(meta.get("name", "Backtest"))
_common.metric_cards(
    result.metrics,
    [
        ("total_return", "Total return"),
        ("cagr", "CAGR"),
        ("sharpe", "Sharpe"),
        ("max_drawdown", "Max drawdown"),
        ("annual_volatility", "Volatility"),
        ("sortino", "Sortino"),
        ("benchmark_total_return", "Benchmark return"),
        ("num_trades", "Trades"),
    ],
)
st.plotly_chart(
    charts.equity_chart(result.equity, result.benchmark_returns), use_container_width=True
)
st.plotly_chart(charts.drawdown_chart(result.returns), use_container_width=True)
st.plotly_chart(charts.weights_chart(result.weights), use_container_width=True)

data = st.session_state.get("last_data", {})
if result.signals is not None and data:
    sym = st.selectbox("Inspect signals for", list(result.signals.columns))
    st.plotly_chart(
        charts.price_chart(
            data[sym].loc[result.signals.index[0] :],
            sym,
            signals=result.signals[sym].gt(0).astype(float),
        ),
        use_container_width=True,
    )

tab1, tab2, tab3 = st.tabs(["Trades", "All metrics", "Config"])
with tab1:
    st.dataframe(result.trades, use_container_width=True)
    st.download_button(
        "Download trades CSV", result.trades.to_csv(index=False).encode(), "trades.csv"
    )
with tab2:
    from tradelab.risk import format_metrics

    st.table(format_metrics(result.metrics))
with tab3:
    st.code(json.dumps(result.metadata, indent=2, default=str), language="json")
st.caption("See **Risk Analytics** for deeper analysis of this result.")
