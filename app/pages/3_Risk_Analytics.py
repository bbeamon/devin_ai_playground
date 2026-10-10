import _common
import streamlit as st

from tradelab.risk import format_metrics
from tradelab.risk import metrics as m
from tradelab.ui import charts

st.set_page_config(page_title="Risk Analytics", layout="wide")
st.title("Risk Analytics")

result = st.session_state.get("last_result")
if result is None:
    st.info("Run a backtest on the **Backtest** page first.")
    st.stop()

rets = result.returns.iloc[1:]
rf = result.risk_free_rate
window = st.sidebar.slider("Rolling window (days)", 21, 252, 63, 21)
level = st.sidebar.select_slider("VaR confidence", [0.90, 0.95, 0.975, 0.99], value=0.95)

met = result.metrics
_common.metric_cards(
    met,
    [
        ("sharpe", "Sharpe"),
        ("sortino", "Sortino"),
        ("calmar", "Calmar"),
        ("max_drawdown", "Max drawdown"),
        ("beta", "Beta"),
        ("alpha", "Alpha (ann.)"),
        ("information_ratio", "Info ratio"),
        ("max_drawdown_duration", "Max DD days"),
    ],
)
c1, c2, c3 = st.columns(3)
c1.metric(f"Historical VaR {level:.1%}", f"{m.value_at_risk(rets, level):.2%}")
c2.metric(f"Parametric VaR {level:.1%}", f"{m.value_at_risk(rets, level, 'parametric'):.2%}")
c3.metric(f"CVaR {level:.1%}", f"{m.conditional_var(rets, level):.2%}")

st.plotly_chart(charts.drawdown_chart(rets), use_container_width=True)
st.plotly_chart(charts.rolling_chart(rets, window, rf), use_container_width=True)
if result.benchmark_returns is not None:
    st.line_chart(
        m.rolling_beta(rets, result.benchmark_returns, window).rename(f"Rolling beta ({window}d)"),
        height=250,
    )
left, right = st.columns(2)
left.plotly_chart(charts.returns_histogram(rets, level), use_container_width=True)
right.plotly_chart(charts.monthly_heatmap(rets), use_container_width=True)
with st.expander("All metrics"):
    st.table(format_metrics(met))
