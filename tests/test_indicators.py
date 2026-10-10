import numpy as np
import pandas as pd
import pytest

from tradelab.strategies import indicators as ind

from .conftest import make_ohlcv


def test_sma_and_ema():
    s = pd.Series([1.0, 2, 3, 4, 5])
    assert ind.sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    assert ind.sma(s, 3).isna().sum() == 2
    e = ind.ema(s, 2)
    assert e.iloc[1] == pytest.approx(1 + (2 - 1) * 2 / 3)


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert ind.rsi(up, 14).dropna().eq(100).all()
    down = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert ind.rsi(down, 14).dropna().lt(1e-9).all()
    rng = np.random.default_rng(0)
    r = ind.rsi(pd.Series(100 + rng.normal(0, 1, 300).cumsum()), 14).dropna()
    assert r.between(0, 100).all()


def test_bollinger_symmetry():
    s = pd.Series(np.random.default_rng(1).normal(100, 2, 100))
    lo, mid, hi = ind.bollinger_bands(s, 20, 2)
    pd.testing.assert_series_equal(hi - mid, mid - lo)


def test_macd_histogram_identity():
    s = pd.Series(np.linspace(1, 50, 100))
    line, sig, hist = ind.macd(s)
    pd.testing.assert_series_equal(hist, line - sig)


def test_atr_constant_range():
    df = make_ohlcv([100.0] * 30)
    assert ind.atr(df, 14).iloc[-1] == pytest.approx(2.0)


def test_donchian_excludes_current_bar():
    df = make_ohlcv([1, 2, 3, 4, 10])
    upper, _ = ind.donchian(df, 3)
    assert upper.iloc[-1] == pytest.approx(df["high"].iloc[1:4].max())
