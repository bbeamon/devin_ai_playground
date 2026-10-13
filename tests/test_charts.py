import pandas as pd

from tradelab.ui import charts


def _closes(universe_data):
    return {k: v["close"] for k, v in universe_data.items()}


def test_growth_chart_starts_at_one(universe_data):
    fig = charts.growth_chart(_closes(universe_data))
    assert len(fig.data) == len(universe_data)
    assert all(abs(t.y[0] - 1.0) < 1e-12 for t in fig.data)


def test_symbol_stats_and_bars(universe_data):
    closes = _closes(universe_data)
    stats = charts.symbol_stats(closes)
    sym = next(iter(closes))
    c = closes[sym]
    assert abs(stats.loc[sym, "total_return"] - (c.iloc[-1] / c.iloc[0] - 1)) < 1e-12
    assert (stats["volatility"] > 0).all() and (stats["max_drawdown"] <= 0).all()
    fig = charts.stat_bars(stats["total_return"], "t")
    assert list(fig.data[0].x) == sorted(stats["total_return"])
    assert charts.stat_bars(stats["volatility"], "v", color="#000").data[0].marker.color == "#000"


def test_allocation_donut_labels_shorts_and_drops_zero():
    fig = charts.allocation_donut(pd.Series({"AAA": 0.5, "BBB": -0.25, "CCC": 0.0, "Cash": 0.25}))
    pie = fig.data[0]
    assert list(pie.labels) == ["AAA", "BBB (short)", "Cash"]
    assert list(pie.values) == [0.5, 0.25, 0.25]


def test_monthly_returns_compounds_daily():
    idx = pd.bdate_range("2024-01-01", "2024-02-29")
    r = pd.Series(0.01, index=idx)
    mr = charts.monthly_returns(r)
    jan = (idx.month == 1).sum()
    assert len(mr) == 2 and abs(mr.iloc[0] - (1.01**jan - 1)) < 1e-12
    assert len(charts.monthly_returns_bar(r).data[0].x) == 2


def test_cost_breakdown_sums_per_symbol():
    trades = pd.DataFrame(
        {"symbol": ["A", "A", "B"], "commission": [1.0, 2.0, 0.5], "slippage_cost": [0.1, 0.2, 3.0]}
    )
    fig = charts.cost_breakdown(trades)
    comm, slip = fig.data
    assert list(comm.x) == ["B", "A"] and list(comm.y) == [0.5, 3.0]
    assert list(slip.y) == [3.0, 0.30000000000000004] or abs(slip.y[1] - 0.3) < 1e-12
    assert len(charts.cost_breakdown(trades.iloc[0:0]).data) == 0
