import math

import numpy as np
import pandas as pd
import pytest

from tradelab.risk import format_metrics, summarize
from tradelab.risk import metrics as m


@pytest.fixture
def rets():
    idx = pd.bdate_range("2020-01-01", periods=504)
    return pd.Series(np.random.default_rng(3).normal(0.0005, 0.01, 504), index=idx)


def test_total_return_and_cagr():
    r = pd.Series([0.1, -0.1])
    assert m.total_return(r) == pytest.approx(1.1 * 0.9 - 1)
    daily = pd.Series([0.0003] * 252)
    assert m.cagr(daily) == pytest.approx(1.0003**252 - 1)


def test_sharpe_matches_formula(rets):
    expected = rets.mean() / rets.std() * math.sqrt(252)
    assert m.sharpe_ratio(rets) == pytest.approx(expected)
    rf = 0.02
    adj = rets - rf / 252
    assert m.sharpe_ratio(rets, rf) == pytest.approx(adj.mean() / adj.std() * math.sqrt(252))


def test_zero_vol_edge_cases():
    flat = pd.Series([0.0] * 10)
    assert m.sharpe_ratio(flat) == 0.0
    assert m.sortino_ratio(flat) == 0.0
    assert m.max_drawdown(flat) == 0.0
    assert m.total_return(pd.Series(dtype=float)) == 0.0


def test_max_drawdown_known_path():
    r = pd.Series([0.10, -0.50, 0.20, 1.0])
    # wealth 1.1 -> 0.55 -> 0.66 -> 1.32; peak 1.1, trough 0.55
    assert m.max_drawdown(r) == pytest.approx(-0.5)
    assert m.max_drawdown_duration(r) == 2


def test_drawdown_starting_with_loss():
    assert m.max_drawdown(pd.Series([-0.2, 0.1])) == pytest.approx(-0.2)


def test_var_cvar(rets):
    var = m.value_at_risk(rets, 0.95)
    cvar = m.conditional_var(rets, 0.95)
    assert var > 0 and cvar >= var
    assert m.value_at_risk(rets, 0.99) >= var
    pvar = m.value_at_risk(rets, 0.95, "parametric")
    assert pvar == pytest.approx(-(rets.mean() - 1.6448536 * rets.std()), rel=1e-4)
    with pytest.raises(ValueError):
        m.value_at_risk(rets, method="bogus")


def test_beta_alpha(rets):
    bench = rets.copy()
    strat = 2 * bench + 0.0001
    assert m.beta(strat, bench) == pytest.approx(2.0)
    assert m.alpha(strat, bench) == pytest.approx(0.0001 * 252)
    assert m.correlation(strat, bench) == pytest.approx(1.0)
    assert m.tracking_error(bench, bench) == 0.0


def test_win_rate_profit_factor():
    r = pd.Series([0.01, -0.02, 0.03, 0.0])
    assert m.win_rate(r) == pytest.approx(2 / 3)
    assert m.profit_factor(r) == pytest.approx(0.04 / 0.02)
    assert math.isinf(m.profit_factor(pd.Series([0.01])))


def test_monthly_table(rets):
    table = m.monthly_returns_table(rets)
    assert list(table.index) == [2020, 2021]
    jan = rets["2020-01"]
    assert table.loc[2020, "Jan"] == pytest.approx((1 + jan).prod() - 1)
    assert table.loc[2020, "Year"] == pytest.approx((1 + rets["2020"]).prod() - 1)


def test_rolling_lengths(rets):
    assert len(m.rolling_sharpe(rets, 21)) == len(rets)
    assert m.rolling_volatility(rets, 21).iloc[:20].isna().all()


def test_turnover_exposure():
    w = pd.DataFrame({"A": [0, 1, 1, 0], "B": [0, 0, 0, 0]}, dtype=float)
    assert m.exposure(w) == 0.5
    assert m.turnover(w, periods=1) == pytest.approx((0 + 1 + 0 + 1) / 3 / 2)


def test_summarize_and_format(rets):
    s = summarize(rets, benchmark=rets * 0.5, risk_free=0.01)
    for k in ["sharpe", "cagr", "max_drawdown", "beta", "alpha", "var_95"]:
        assert k in s
    f = format_metrics(s)
    assert f["cagr"].endswith("%")
    assert f["periods"] == "504"
