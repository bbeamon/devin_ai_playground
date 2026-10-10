import numpy as np
import pandas as pd
import pytest

from tradelab.backtest import Backtester, CostModel, grid_search, run_backtest
from tradelab.config import BacktestSettings, RiskSettings, Settings
from tradelab.strategies import StrategyConfig

from .conftest import make_ohlcv

NO_COSTS = dict(slippage_bps=0, commission_pct=0, commission_per_share=0, rebalance_threshold=0)
RISK = RiskSettings(max_position_weight=1.0, max_gross_leverage=1.0, min_trade_notional=0)


def weights_for(df, value=1.0, sym="A"):
    return pd.DataFrame({sym: value}, index=df.index)


def test_buy_and_hold_close_execution_matches_price():
    df = make_ohlcv([100, 110, 121, 108.9])
    res = Backtester(BacktestSettings(execution="close", **NO_COSTS), RISK).run(
        {"A": df}, weights_for(df)
    )
    np.testing.assert_allclose(res.equity.to_numpy(), [100_000, 110_000, 121_000, 108_900])
    assert len(res.trades) == 1


def test_next_open_execution_has_one_bar_lag():
    df = make_ohlcv([100, 100, 120], opens=[100, 110, 110])
    res = Backtester(BacktestSettings(execution="next_open", **NO_COSTS), RISK).run(
        {"A": df}, weights_for(df)
    )
    # day0: flat. day1: buy at open 110, close 100. day2: close 120
    assert res.equity.iloc[0] == 100_000
    assert res.trades.iloc[0]["date"] == df.index[1]
    shares = 100_000 / 110
    assert res.equity.iloc[1] == pytest.approx(shares * 100)
    assert res.equity.iloc[2] == pytest.approx(shares * 120)


def test_signal_on_last_bar_not_traded_with_next_open():
    df = make_ohlcv([100, 101, 102])
    w = pd.DataFrame({"A": [0.0, 0.0, 1.0]}, index=df.index)
    res = Backtester(BacktestSettings(**NO_COSTS), RISK).run({"A": df}, w)
    assert res.trades.empty and res.equity.eq(100_000).all()


def test_costs_reduce_equity():
    df = make_ohlcv([100] * 5)
    s = BacktestSettings(
        execution="close", slippage_bps=10, commission_per_share=0.01, rebalance_threshold=0
    )
    res = Backtester(s, RISK).run({"A": df}, weights_for(df))
    t = res.trades.iloc[0]
    assert t["fill_price"] == pytest.approx(100.1)
    assert t["commission"] == pytest.approx(t["qty"] * 0.01)
    assert res.equity.iloc[-1] < 100_000
    assert res.metrics["total_costs"] > 0


def test_cost_model():
    c = CostModel(commission_pct=0.001, min_commission=1.0, slippage_bps=50)
    assert c.fill_price(100, 5) == pytest.approx(100.5)
    assert c.fill_price(100, -5) == pytest.approx(99.5)
    assert c.commission(1, 10) == 1.0
    assert c.commission(0, 10) == 0.0


def test_whole_shares():
    df = make_ohlcv([333.0] * 3)
    s = BacktestSettings(execution="close", fractional_shares=False, **NO_COSTS)
    res = Backtester(s, RISK).run({"A": df}, weights_for(df))
    assert res.positions["A"].iloc[-1] == 300
    assert res.cash.iloc[-1] == pytest.approx(100_000 - 300 * 333)


def test_rebalance_threshold_suppresses_drift_trades():
    df = make_ohlcv(np.linspace(100, 130, 30))
    b = make_ohlcv(np.linspace(100, 90, 30))
    w = pd.DataFrame({"A": 0.5, "B": 0.5}, index=df.index)
    base = dict(execution="close", slippage_bps=0)
    many = Backtester(BacktestSettings(**base, rebalance_threshold=0), RISK).run(
        {"A": df, "B": b}, w
    )
    few = Backtester(BacktestSettings(**base, rebalance_threshold=0.05), RISK).run(
        {"A": df, "B": b}, w
    )
    assert len(few.trades) < len(many.trades)


def test_full_exit_always_executes():
    df = make_ohlcv([100] * 4)
    w = pd.DataFrame({"A": [0.005, 0.005, 0.0, 0.0]}, index=df.index)
    res = Backtester(
        BacktestSettings(execution="close", slippage_bps=0, rebalance_threshold=0.01), RISK
    ).run({"A": df}, w)
    assert res.positions["A"].iloc[-1] == 0


def test_shorts_clipped_when_disabled():
    df = make_ohlcv([100, 90, 80])
    res = Backtester(BacktestSettings(execution="close", **NO_COSTS), RISK).run(
        {"A": df}, weights_for(df, -1.0)
    )
    assert res.trades.empty


def test_short_profit_when_enabled():
    df = make_ohlcv([100, 90, 80])
    s = BacktestSettings(execution="close", allow_short=True, **NO_COSTS)
    res = Backtester(s, RISK).run({"A": df}, weights_for(df, -1.0))
    # daily re-balanced to -100%: 100k -> 110k, then short 110k more at 90 -> 80
    assert res.equity.iloc[-1] == pytest.approx(110_000 * (1 + 10 / 90))


def test_missing_prices_handled():
    a = make_ohlcv([100] * 6)
    b = make_ohlcv([50] * 3, start=str(a.index[3].date()))
    w = pd.DataFrame({"A": 0.5, "B": 0.5}, index=a.index)
    res = Backtester(BacktestSettings(execution="close", **NO_COSTS), RISK).run({"A": a, "B": b}, w)
    assert not res.equity.isna().any()
    assert res.positions["B"].iloc[:3].eq(0).all() and res.positions["B"].iloc[-1] > 0


def test_missing_symbol_raises():
    df = make_ohlcv([1, 2])
    with pytest.raises(KeyError):
        Backtester().run({}, weights_for(df))


def test_benchmark_and_weights(universe_data):
    cfg = StrategyConfig(
        strategy="sma_crossover", params={"fast": 10, "slow": 30}, universe=list(universe_data)
    )
    res = run_backtest(cfg, Settings(), data=universe_data, benchmark=universe_data["AAA"]["close"])
    assert res.benchmark_returns is not None and len(res.benchmark_returns) == len(res.equity)
    assert (res.weights.abs().sum(axis=1) <= 1.05).all()
    m = res.metrics
    assert {"sharpe", "beta", "num_trades", "turnover"} <= set(m)
    assert m["num_trades"] == len(res.trades) > 0


def test_run_backtest_with_provider(synthetic):
    cfg = StrategyConfig(
        strategy="momentum",
        params={"lookback": 60},
        universe=["AAA", "BBB"],
        start="2020-01-01",
        end="2021-12-31",
        benchmark="SPY",
    )
    res = run_backtest(cfg, provider=synthetic)
    assert res.equity.index[0] >= pd.Timestamp("2020-01-01")
    assert res.metadata["strategy"]["strategy"] == "momentum"
    with pytest.raises(ValueError):
        run_backtest(cfg)


def test_grid_search(universe_data):
    cfg = StrategyConfig(strategy="sma_crossover", universe=list(universe_data), benchmark=None)
    df = grid_search(cfg, {"fast": [5, 10, 40], "slow": [20, 50]}, universe_data)
    assert len(df) == 6
    assert df.loc[(df.fast == 40) & (df.slow == 20), "error"].notna().all()
    assert df["sharpe"].notna().sum() == 5
    split = grid_search(cfg, {"fast": [5]}, universe_data, split_date="2022-01-01")
    assert {"is_sharpe", "oos_sharpe"} <= set(split.columns)


def test_costs_never_drive_cash_negative_without_leverage(universe_data):
    s = BacktestSettings(commission_per_share=0.01, min_commission=1.0, slippage_bps=20)
    risk = RiskSettings(max_position_weight=0.5, max_gross_leverage=1.0)
    w = pd.DataFrame(0.5, index=universe_data["AAA"].index, columns=["AAA", "BBB"])
    res = Backtester(s, risk).run({k: universe_data[k] for k in w.columns}, w)
    assert res.cash.min() >= -1e-9
    assert res.weights.abs().sum(axis=1).max() <= 1.0 + 1e-9


def test_day_zero_costs_included_in_returns():
    df = make_ohlcv([100, 100, 100])
    s = BacktestSettings(execution="close", commission_pct=0.01, min_commission=0.0)
    res = Backtester(s, RISK).run({"A": df}, weights_for(df, 1.0))
    assert res.returns.iloc[0] < 0
    assert (1 + res.returns).prod() * s.initial_cash == pytest.approx(res.equity.iloc[-1])
