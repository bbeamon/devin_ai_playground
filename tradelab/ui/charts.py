"""Plotly figure builders used by the Streamlit app (kept UI-framework agnostic)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from tradelab.risk import metrics as m


def price_chart(
    df: pd.DataFrame,
    symbol: str,
    overlays: dict[str, pd.Series] | None = None,
    signals: pd.Series | None = None,
) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=symbol,
        ),
        row=1,
        col=1,
    )
    for name, series in (overlays or {}).items():
        fig.add_trace(
            go.Scatter(x=series.index, y=series, name=name, line={"width": 1.2}), row=1, col=1
        )
    if signals is not None:
        change = signals.diff().fillna(signals)
        buys, sells = change[change > 0].index, change[change < 0].index
        fig.add_trace(
            go.Scatter(
                x=buys,
                y=df.loc[buys, "low"] * 0.98,
                mode="markers",
                name="entry",
                marker={"symbol": "triangle-up", "size": 9, "color": "green"},
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=sells,
                y=df.loc[sells, "high"] * 1.02,
                mode="markers",
                name="exit",
                marker={"symbol": "triangle-down", "size": 9, "color": "red"},
            ),
            row=1,
            col=1,
        )
    fig.add_trace(
        go.Bar(x=df.index, y=df["volume"], name="volume", marker_color="#888"), row=2, col=1
    )
    fig.update_layout(height=600, xaxis_rangeslider_visible=False, margin={"t": 30, "b": 10})
    return fig


def equity_chart(equity: pd.Series, benchmark_returns: pd.Series | None = None) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity.index, y=equity, name="Strategy"))
    if benchmark_returns is not None and len(benchmark_returns):
        bench_eq = (1 + benchmark_returns).cumprod() * equity.iloc[0]
        fig.add_trace(
            go.Scatter(x=bench_eq.index, y=bench_eq, name="Benchmark", line={"dash": "dot"})
        )
    fig.update_layout(
        title="Equity curve", yaxis_title="Portfolio value ($)", height=420, margin={"t": 40}
    )
    return fig


def drawdown_chart(returns: pd.Series) -> go.Figure:
    dd = m.drawdown_series(returns)
    fig = go.Figure(
        go.Scatter(x=dd.index, y=dd, fill="tozeroy", name="Drawdown", line={"color": "crimson"})
    )
    fig.update_layout(title="Drawdown", yaxis_tickformat=".0%", height=300, margin={"t": 40})
    return fig


def rolling_chart(returns: pd.Series, window: int = 63, risk_free: float = 0.0) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=returns.index,
            y=m.rolling_sharpe(returns, window, risk_free),
            name=f"Rolling Sharpe ({window})",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=returns.index, y=m.rolling_volatility(returns, window), name=f"Rolling vol ({window})"
        ),
        secondary_y=True,
    )
    fig.update_yaxes(title_text="Sharpe", secondary_y=False)
    fig.update_yaxes(title_text="Volatility", tickformat=".0%", secondary_y=True)
    fig.update_layout(title="Rolling risk", height=350, margin={"t": 40})
    return fig


def returns_histogram(returns: pd.Series, level: float = 0.95) -> go.Figure:
    r = returns[returns != 0]
    var = m.value_at_risk(r, level)
    cvar = m.conditional_var(r, level)
    fig = go.Figure(go.Histogram(x=r, nbinsx=80, name="Daily returns"))
    fig.add_vline(x=-var, line_dash="dash", line_color="orange", annotation_text=f"VaR {level:.0%}")
    fig.add_vline(x=-cvar, line_dash="dot", line_color="red", annotation_text="CVaR")
    fig.update_layout(
        title="Return distribution", xaxis_tickformat=".1%", height=350, margin={"t": 40}
    )
    return fig


def monthly_heatmap(returns: pd.Series) -> go.Figure:
    table = m.monthly_returns_table(returns)
    if table.empty:
        return go.Figure()
    months = table.drop(columns="Year")
    fig = go.Figure(
        go.Heatmap(
            z=months.values,
            x=list(months.columns),
            y=[str(y) for y in months.index],
            colorscale="RdYlGn",
            zmid=0,
            text=[[f"{v:.1%}" if pd.notna(v) else "" for v in row] for row in months.values],
            texttemplate="%{text}",
            hoverongaps=False,
        )
    )
    fig.update_layout(title="Monthly returns", height=40 * len(months) + 120, margin={"t": 40})
    return fig


def weights_chart(weights: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for col in weights.columns:
        fig.add_trace(go.Scatter(x=weights.index, y=weights[col], name=col, stackgroup="one"))
    fig.update_layout(
        title="Portfolio weights", yaxis_tickformat=".0%", height=350, margin={"t": 40}
    )
    return fig


def correlation_heatmap(returns: pd.DataFrame) -> go.Figure:
    corr = returns.corr()
    fig = go.Figure(
        go.Heatmap(
            z=corr.values,
            x=corr.columns,
            y=corr.index,
            colorscale="RdBu",
            zmin=-1,
            zmax=1,
            text=corr.round(2).values,
            texttemplate="%{text}",
        )
    )
    fig.update_layout(title="Return correlation", height=400, margin={"t": 40})
    return fig
