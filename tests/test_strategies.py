import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from tradelab.config import RiskSettings
from tradelab.strategies import (
    Strategy,
    StrategyConfig,
    StrategyEngine,
    StrategyParams,
    create_strategy,
    get_strategy_class,
    list_strategies,
    register_strategy,
)

from .conftest import make_ohlcv

ALL = list(list_strategies())


def test_builtins_registered():
    for name in [
        "buy_and_hold",
        "sma_crossover",
        "ema_crossover",
        "rsi_mean_reversion",
        "bollinger_reversion",
        "momentum",
        "donchian_breakout",
        "macd",
        "ensemble",
    ]:
        assert name in ALL


@pytest.mark.parametrize("name", [n for n in ALL if n != "ensemble"])
def test_signals_are_bounded_and_aligned(name, synthetic):
    df = synthetic.get_history("AAA", "2020-01-01", "2022-12-31")
    sig = create_strategy(name).generate_signals(df)
    assert sig.index.equals(df.index)
    assert sig.between(-1, 1).all() and not sig.isna().any()


@pytest.mark.parametrize("name", [n for n in ALL if n != "ensemble"])
def test_no_lookahead(name, synthetic):
    """Signals up to t must not change when future bars are appended."""
    df = synthetic.get_history("BBB", "2020-01-01", "2022-12-31")
    cut = len(df) - 100
    strat = create_strategy(name)
    full = strat.generate_signals(df).iloc[:cut]
    partial = strat.generate_signals(df.iloc[:cut])
    pd.testing.assert_series_equal(full, partial)


def test_sma_crossover_logic():
    closes = [10.0] * 5 + [20.0] * 5 + [5.0] * 10
    sig = create_strategy("sma_crossover", fast=2, slow=4).generate_signals(make_ohlcv(closes))
    assert sig.iloc[:3].eq(0).all()
    assert sig.iloc[6] == 1.0
    assert sig.iloc[-1] == 0.0
    short = create_strategy("sma_crossover", fast=2, slow=4, allow_short=True).generate_signals(
        make_ohlcv(closes)
    )
    assert short.iloc[-1] == -1.0


def test_rsi_strategy_holds_until_exit():
    closes = list(np.linspace(100, 60, 20)) + list(np.linspace(60, 120, 30))
    sig = create_strategy("rsi_mean_reversion", period=5).generate_signals(make_ohlcv(closes))
    first_entry = sig[sig == 1].index[0]
    assert sig.loc[first_entry:].iloc[:5].eq(1).all()
    assert sig.iloc[-1] == 0  # exited on overbought


def test_param_validation():
    with pytest.raises(ValidationError):
        create_strategy("sma_crossover", fast=50, slow=20)
    with pytest.raises(ValidationError):
        create_strategy("sma_crossover", unknown=1)
    with pytest.raises(ValidationError):
        create_strategy("rsi_mean_reversion", oversold=80, overbought=20)


def test_unknown_strategy():
    with pytest.raises(KeyError):
        create_strategy("does_not_exist")


def test_dotted_path_and_custom_registration():
    cls = get_strategy_class("tradelab.strategies.builtin:Momentum")
    assert cls.name == "momentum"
    with pytest.raises(TypeError):
        get_strategy_class("tradelab.config:Settings")

    class P(StrategyParams):
        level: float = 0.5

    @register_strategy
    class Half(Strategy):
        name = "test_half"
        Params = P

        def compute(self, df):
            return pd.Series(self.params.level, index=df.index)

    assert create_strategy("test_half", level=2).generate_signals(make_ohlcv([1, 2, 3])).eq(1).all()
    with pytest.raises(ValueError):
        register_strategy(type("Dup", (Half,), {"name": "momentum"}))


def test_ensemble_average(synthetic):
    df = synthetic.get_history("AAA", "2021-01-01", "2021-12-31")
    ens = create_strategy(
        "ensemble",
        components=[
            {"strategy": "buy_and_hold", "weight": 3},
            {"strategy": "sma_crossover", "params": {"fast": 5, "slow": 10}, "weight": 1},
        ],
    )
    sma = create_strategy("sma_crossover", fast=5, slow=10).generate_signals(df)
    expected = (3 + sma) / 4
    np.testing.assert_allclose(ens.generate_signals(df).to_numpy(), expected.to_numpy())
    assert ens.warmup == 10


def test_config_from_yaml_examples():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "config" / "strategies"
    files = sorted(root.glob("*.yaml"))
    assert files
    for f in files:
        cfg = StrategyConfig.from_yaml(f)
        cfg.build_strategy()


def test_config_validation():
    with pytest.raises(ValidationError):
        StrategyConfig(strategy="momentum", universe=[])
    with pytest.raises(ValidationError):
        StrategyConfig(strategy="momentum", universe=["A"], start="2024-01-01", end="2023-01-01")
    cfg = StrategyConfig(strategy="momentum", universe=[" spy", "SPY", "qqq"])
    assert cfg.universe == ["SPY", "QQQ"]


def test_engine_weights_respect_limits(universe_data):
    cfg = StrategyConfig(
        strategy="buy_and_hold",
        universe=list(universe_data),
        sizing={"method": "fixed_fraction", "fraction": 0.9},
    )
    risk = RiskSettings(max_position_weight=0.4, max_gross_leverage=1.0)
    w = StrategyEngine(cfg, risk).target_weights(universe_data)
    assert (w <= 0.4 + 1e-12).all().all()
    assert (w.abs().sum(axis=1) <= 1.0 + 1e-12).all()


def test_engine_long_only_clips_shorts(universe_data):
    cfg = StrategyConfig(
        strategy="momentum",
        params={"lookback": 20, "allow_short": True},
        universe=list(universe_data),
    )
    assert (StrategyEngine(cfg, allow_short=False).target_weights(universe_data) >= 0).all().all()
    assert (StrategyEngine(cfg, allow_short=True).target_weights(universe_data) < 0).any().any()


def test_engine_vol_target(universe_data):
    cfg = StrategyConfig(
        strategy="buy_and_hold",
        universe=list(universe_data),
        sizing={"method": "vol_target", "target_vol": 0.05, "vol_lookback": 20},
    )
    w = StrategyEngine(cfg, RiskSettings(max_position_weight=1.0)).target_weights(universe_data)
    assert w.iloc[:19].eq(0).all().all()
    # ~20% vol assets scaled to 5% target / 3 assets
    assert 0.05 < w.iloc[-1].mean() < 0.15


def test_engine_missing_symbol(universe_data):
    cfg = StrategyConfig(strategy="buy_and_hold", universe=["AAA", "ZZZ"])
    with pytest.raises(KeyError):
        StrategyEngine(cfg).signals(universe_data)
