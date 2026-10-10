import _common  # noqa: F401  (path setup)
import streamlit as st

from tradelab import LIVE_TRADING_ENABLED, __version__
from tradelab.strategies import list_strategies

st.set_page_config(page_title="tradelab", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title("tradelab - algorithmic trading research")
st.caption(f"v{__version__}")
st.info(_common.PAPER_BANNER)
assert LIVE_TRADING_ENABLED is False

st.markdown(
    """
Use the pages in the sidebar:

| Page | What it does |
|---|---|
| **Data Explorer** | Load historical OHLCV, inspect data quality, candlestick + indicators, correlations |
| **Backtest** | Configure a strategy (UI or YAML), run a cost-aware backtest, review trades |
| **Risk Analytics** | Drawdowns, VaR/CVaR, rolling Sharpe/vol, benchmark beta/alpha, monthly returns |
| **Optimizer** | Grid-search strategy parameters with in-sample / out-of-sample split |
| **Paper Trading** | Connect to the simulator or Alpaca **paper** account, preview and submit rebalance orders |
"""
)

st.subheader("Available strategies")
st.table([{"name": k, "description": v.description} for k, v in list_strategies().items()])
