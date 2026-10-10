import datetime as dt

import _common
import numpy as np
import streamlit as st

from tradelab.backtest import grid_search
from tradelab.strategies import StrategyConfig, list_strategies

st.set_page_config(page_title="Optimizer", layout="wide")
st.title("Parameter optimizer")
st.caption(
    "Grid search with an in-sample / out-of-sample split. Beware of over-fitting: judge on OOS metrics."
)

strategies = {k: v for k, v in list_strategies().items() if k != "ensemble"}
name = st.sidebar.selectbox(
    "Strategy", list(strategies), index=list(strategies).index("sma_crossover")
)
schema = strategies[name].param_schema().get("properties", {})
numeric = {k: v for k, v in schema.items() if v.get("type") in ("integer", "number")}
provider, symbols, start, end = _common.sidebar_data_inputs("SPY, QQQ", key="opt")
split = st.sidebar.date_input("OOS starts", dt.date(2022, 1, 1))

grid = {}
st.subheader("Parameter ranges")
for pname, spec in numeric.items():
    c1, c2, c3 = st.columns(3)
    d = spec.get("default", 1)
    is_int = spec.get("type") == "integer"
    lo = c1.number_input(f"{pname} min", value=d, key=f"{pname}_lo")
    hi = c2.number_input(f"{pname} max", value=d * 3 if is_int else d, key=f"{pname}_hi")
    steps = c3.number_input(f"{pname} steps", 1, 20, 3 if is_int else 1, key=f"{pname}_n")
    vals = np.linspace(lo, hi, int(steps))
    grid[pname] = sorted({int(round(v)) for v in vals}) if is_int else [float(v) for v in vals]
n = int(np.prod([len(v) for v in grid.values()])) if grid else 0
st.write(f"{n} combinations")
metric = st.selectbox("Rank by (OOS)", ["sharpe", "cagr", "calmar", "sortino", "max_drawdown"])

if st.button("Run grid search", type="primary", disabled=n == 0 or n > 400):
    data = _common.safe_load(provider, symbols, start, end)
    if data:
        cfg = StrategyConfig(name=name, strategy=name, universe=symbols, benchmark=None)
        bar = st.progress(0.0)
        df = grid_search(
            cfg,
            grid,
            data,
            _common.get_settings(),
            split_date=split,
            on_progress=lambda i, t: bar.progress(i / t),
        )
        st.session_state["grid_results"] = (df, list(grid))

saved = st.session_state.get("grid_results")
if saved is not None:
    df, grid_keys = saved
    sort_col = f"oos_{metric}"
    if sort_col in df:
        df = df.sort_values(sort_col, ascending=False)  # max_drawdown is negative: higher is better
    cols = (
        [k for k in grid_keys if k in df]
        + [
            c
            for c in df.columns
            if c.split("_", 1)[-1] in ("sharpe", "cagr", "max_drawdown", "calmar", "sortino")
        ]
        + (["error"] if "error" in df else [])
    )
    st.dataframe(df[cols], use_container_width=True)
    st.download_button("Download results", df.to_csv(index=False).encode(), "grid_search.csv")
