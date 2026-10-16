import datetime as dt
import json

import _common
import pandas as pd
import streamlit as st
import yaml
from pydantic import ValidationError

from tradelab.backtest import run_backtest
from tradelab.config import BacktestSettings, Settings
from tradelab.strategies import StrategyConfig, list_strategies
from tradelab.ui import charts

st.set_page_config(page_title="Backtest", layout="wide")
_common.page_header("Backtest", "Run a cost-aware simulation of a strategy on historical data.")

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
    initial_cash = st.number_input(
        "Initial cash", min_value=1.0, value=float(bt.initial_cash), step=10_000.0
    )
    slippage = st.number_input(
        "Slippage (bps)", min_value=0.0, value=float(bt.slippage_bps), step=1.0
    )
    commission_pct = (
        st.number_input(
            "Commission (% of notional)",
            min_value=0.0,
            value=float(bt.commission_pct * 100),
            step=0.01,
        )
        / 100
    )
    execution = st.selectbox(
        "Execution", ["next_open", "close"], index=["next_open", "close"].index(bt.execution)
    )
    allow_short = st.checkbox("Allow short", value=bt.allow_short)
    threshold = st.number_input(
        "Rebalance threshold (weight)",
        min_value=0.0,
        value=float(bt.rebalance_threshold),
        step=0.005,
        format="%.3f",
    )
with st.sidebar.expander("Risk limits"):
    rk = base.risk
    max_pos = st.slider("Max position weight", 0.05, 1.0, float(rk.max_position_weight), 0.05)
    max_gross = st.slider("Max gross leverage", 0.1, 2.0, float(rk.max_gross_leverage), 0.1)

run_clicked = cfg is not None and st.sidebar.button("Run backtest", type="primary")
if cfg is not None:
    run_clicked = (
        _common.mobile_bar(
            f"**{cfg.strategy}** on {', '.join(cfg.universe)} · {provider} data", "Run backtest"
        )
        or run_clicked
    )
if cfg is not None and run_clicked:
    try:
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
    except ValidationError as exc:
        st.error(f"Invalid execution/cost settings: {exc}")
        st.stop()
    symbols = cfg.universe + (
        [cfg.benchmark] if cfg.benchmark and cfg.benchmark not in cfg.universe else []
    )
    for stale in ("last_result", "last_data"):
        st.session_state.pop(stale, None)
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
_common.plot(charts.equity_chart(result.equity, result.benchmark_returns))
_common.plot(charts.drawdown_chart(result.returns))
_common.plot(charts.weights_chart(result.weights))

last_w = result.weights.iloc[-1] if len(result.weights) else pd.Series(dtype=float)
alloc = last_w[last_w.abs() > 1e-9]
alloc["Cash"] = max(0.0, 1.0 - float(last_w.sum()))
left, right = st.columns(2)
_common.plot(
    charts.allocation_donut(alloc, f"Allocation on {result.weights.index[-1].date()}"), left
)
_common.plot(charts.monthly_returns_bar(result.returns.iloc[1:]), right)
if not result.trades.empty:
    _common.plot(charts.cost_breakdown(result.trades))

data = st.session_state.get("last_data", {})
if result.signals is not None and data:
    sym = st.selectbox("Inspect signals for", list(result.signals.columns))
    _common.plot(
        charts.price_chart(
            data[sym].loc[result.signals.index[0] :],
            sym,
            signals=result.signals[sym].gt(0).astype(float),
        )
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
