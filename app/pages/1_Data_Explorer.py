import _common
import pandas as pd
import streamlit as st

from tradelab.data import validate_ohlcv
from tradelab.strategies import indicators as ind
from tradelab.ui import charts

st.set_page_config(page_title="Data Explorer", layout="wide")
st.title("Data Explorer")

provider, symbols, start, end = _common.sidebar_data_inputs(key="explorer")
data = _common.safe_load(provider, symbols, start, end)
if data:
    sym = st.selectbox("Symbol", list(data))
    df = data[sym]
    issues = validate_ohlcv(df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bars", f"{len(df):,}")
    c2.metric("First", str(df.index[0].date()))
    c3.metric("Last", str(df.index[-1].date()))
    c4.metric("Last close", f"{df['close'].iloc[-1]:,.2f}")
    if issues:
        st.warning("Data quality: " + "; ".join(issues))
    else:
        st.success("Data quality checks passed")

    with st.expander("Indicators", expanded=True):
        a, b, c = st.columns(3)
        sma_n = a.multiselect("SMA windows", [10, 20, 50, 100, 200], default=[50, 200])
        show_bb = b.checkbox("Bollinger bands (20, 2)")
        show_rsi = c.checkbox("RSI(14) panel", value=True)
    overlays = {f"SMA {n}": ind.sma(df["close"], n) for n in sma_n}
    if show_bb:
        lo, mid, hi = ind.bollinger_bands(df["close"])
        overlays.update({"BB lower": lo, "BB upper": hi})
    st.plotly_chart(charts.price_chart(df, sym, overlays), use_container_width=True)
    if show_rsi:
        st.line_chart(ind.rsi(df["close"]).rename("RSI(14)"), height=200)

    if len(data) > 1:
        rets = pd.DataFrame({k: v["close"] for k, v in data.items()}).pct_change().dropna(how="all")
        st.plotly_chart(charts.correlation_heatmap(rets), use_container_width=True)
    st.subheader("Raw data")
    st.dataframe(df.tail(250), use_container_width=True)
    st.download_button("Download CSV", df.to_csv().encode(), f"{sym}.csv", "text/csv")
