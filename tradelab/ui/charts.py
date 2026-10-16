"""Plotly figure builders used by the Streamlit app (kept UI-framework agnostic)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from tradelab.risk import metrics as m

PALETTE = ["#22d3ee", "#a78bfa", "#f472b6", "#34d399", "#fbbf24", "#60a5fa", "#fb7185", "#94a3b8"]
POS, NEG = "#10b981", "#ef4444"


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
    fig.add_vline(
        x=-var,
        line_dash="dash",
        line_color="orange",
        annotation_text=f"VaR {level:.0%}",
        annotation_position="top right",
    )
    fig.add_vline(
        x=-cvar,
        line_dash="dot",
        line_color="red",
        annotation_text="CVaR",
        annotation_position="top left",
    )
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
            text=[[f"{v * 100:.0f}" if pd.notna(v) else "" for v in row] for row in months.values],
            texttemplate="%{text}",
            textfont={"size": 11},
            hovertemplate="%{y} %{x}: %{z:.2%}<extra></extra>",
            colorbar={"thickness": 10, "tickformat": ".0%"},
            xgap=1,
            ygap=1,
            hoverongaps=False,
        )
    )
    fig.update_layout(
        title="Monthly returns (%)",
        height=34 * len(months) + 120,
        margin={"t": 40, "l": 10, "r": 10},
    )
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


def growth_chart(closes: dict[str, pd.Series]) -> go.Figure:
    """Growth of $1 invested at each symbol's first bar."""
    fig = go.Figure()
    for i, (sym, c) in enumerate(closes.items()):
        c = c.dropna()
        if c.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=c.index, y=c / c.iloc[0], name=sym, line={"color": PALETTE[i % len(PALETTE)]}
            )
        )
    fig.update_layout(
        title="Growth of $1", yaxis_tickprefix="$", height=380, margin={"t": 40}, hovermode="x"
    )
    return fig


def symbol_stats(closes: dict[str, pd.Series]) -> pd.DataFrame:
    """Total return, annualised volatility and max drawdown per symbol."""
    rows = {}
    for sym, c in closes.items():
        c = c.dropna()
        if len(c) < 2:
            continue
        r = c.pct_change().dropna()
        rows[sym] = {
            "total_return": c.iloc[-1] / c.iloc[0] - 1,
            "volatility": m.annualized_volatility(r),
            "max_drawdown": m.max_drawdown(r),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def stat_bars(
    values: pd.Series, title: str, fmt: str = ".0%", color: str | None = None
) -> go.Figure:
    """Horizontal bars; green/red by sign unless a single ``color`` is given."""
    v = values.sort_values()
    fig = go.Figure(
        go.Bar(
            x=v.values,
            y=list(v.index),
            orientation="h",
            marker_color=color or [POS if x >= 0 else NEG for x in v.values],
            text=[f"{x:{fmt}}" for x in v.values],
            textposition="outside",
            cliponaxis=False,
        )
    )
    lo, hi = min(0.0, float(v.min())), max(0.0, float(v.max()))
    pad = 0.3 * (hi - lo or 1.0)
    fig.update_layout(
        title=title,
        xaxis={"tickformat": fmt, "range": [lo - pad if lo < 0 else 0, hi + pad if hi > 0 else 0]},
        height=max(220, 45 * len(v) + 90),
        margin={"t": 40},
    )
    return fig


def allocation_donut(values: pd.Series, title: str = "Allocation") -> go.Figure:
    """Donut of absolute exposure; short positions are labelled ``(short)``."""
    v = values[values.abs() > 1e-9]
    labels = [f"{k} (short)" if x < 0 else str(k) for k, x in v.items()]
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=v.abs().values,
            hole=0.55,
            marker={"colors": PALETTE[: len(v)] if len(v) <= len(PALETTE) else None},
            textinfo="label+percent",
            textposition="inside",
            insidetextorientation="horizontal",
            sort=False,
        )
    )
    fig.update_layout(title=title, height=360, margin={"t": 50, "b": 10}, showlegend=False)
    return fig


def monthly_returns(returns: pd.Series) -> pd.Series:
    r = returns.dropna()
    if r.empty:
        return pd.Series(dtype=float)
    out = (1 + r).groupby(pd.DatetimeIndex(r.index).to_period("M")).prod() - 1
    out.index = pd.PeriodIndex(out.index).to_timestamp()
    return out


def monthly_returns_bar(returns: pd.Series) -> go.Figure:
    mr = monthly_returns(returns)
    fig = go.Figure(
        go.Bar(x=mr.index, y=mr.values, marker_color=[POS if x >= 0 else NEG for x in mr.values])
    )
    fig.update_layout(title="Monthly returns", yaxis_tickformat=".0%", height=320, margin={"t": 40})
    return fig


def cost_breakdown(trades: pd.DataFrame) -> go.Figure:
    """Stacked commission + slippage cost per symbol."""
    fig = go.Figure()
    if trades.empty:
        return fig
    by = trades.groupby("symbol")[["commission", "slippage_cost"]].sum()
    by = by.loc[by.sum(axis=1).sort_values(ascending=False).index]
    fig.add_trace(
        go.Bar(x=by.index, y=by["commission"], name="Commission", marker_color=PALETTE[1])
    )
    fig.add_trace(
        go.Bar(x=by.index, y=by["slippage_cost"], name="Slippage", marker_color=PALETTE[0])
    )
    fig.update_layout(
        title="Trading costs by symbol",
        barmode="stack",
        yaxis_tickprefix="$",
        height=320,
        margin={"t": 40},
    )
    return fig
