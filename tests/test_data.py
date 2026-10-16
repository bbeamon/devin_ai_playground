import pandas as pd
import pytest

from tradelab.config import DataSettings
from tradelab.data import (
    CachedDataProvider,
    CSVDataProvider,
    DataError,
    SyntheticDataProvider,
    YahooDataProvider,
    create_data_provider,
    normalize_ohlcv,
    validate_ohlcv,
)
from tradelab.data.base import DataProvider


def test_normalize_handles_capitalised_and_tz_columns():
    idx = pd.date_range("2024-01-01", periods=3, tz="America/New_York")
    raw = pd.DataFrame(
        {
            "Open": [1, 2, 3],
            "High": [2, 3, 4],
            "Low": [0.5, 1, 2],
            "Close": [1.5, 2.5, 3.5],
            "Volume": [10, 20, 30],
        },
        index=idx,
    )
    out = normalize_ohlcv(raw)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out.index.tz is None and out.index.name == "date"
    assert out.dtypes.eq(float).all()


def test_normalize_dedupes_and_sorts():
    idx = pd.to_datetime(["2024-01-03", "2024-01-02", "2024-01-03"])
    raw = pd.DataFrame(
        {c: [1.0, 2.0, 3.0] for c in ["open", "high", "low", "close", "volume"]}, index=idx
    )
    out = normalize_ohlcv(raw)
    assert list(out.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert out.loc["2024-01-03", "close"] == 3.0


def test_normalize_missing_columns():
    with pytest.raises(DataError):
        normalize_ohlcv(pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2024-01-01"])))


def test_validate_flags_bad_bars():
    df = pd.DataFrame(
        {"open": [10, 10], "high": [9, 11], "low": [8, 9], "close": [9.5, -1], "volume": [1, -5]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    ).astype(float)
    issues = validate_ohlcv(df)
    assert any("non-positive" in i for i in issues)
    assert any("high below" in i for i in issues)
    assert any("negative volume" in i for i in issues)


def test_synthetic_is_deterministic_and_window_independent():
    p = SyntheticDataProvider(seed=1)
    a = p.get_history("XYZ", "2020-01-01", "2020-12-31")
    b = p.get_history("XYZ", "2020-06-01", "2020-12-31")
    pd.testing.assert_series_equal(a.loc["2020-06-01":, "close"], b["close"])
    assert validate_ohlcv(a) == []
    assert not p.get_history("ABC", "2020-01-01", "2020-12-31")["close"].equals(a["close"])


def test_start_after_end_raises(synthetic):
    with pytest.raises(DataError):
        synthetic.get_history("X", "2021-01-01", "2020-01-01")


def test_csv_provider(tmp_path, synthetic):
    df = synthetic.get_history("AAA", "2022-01-01", "2022-03-31")
    df.reset_index().rename(columns={"date": "Date"}).to_csv(tmp_path / "AAA.csv", index=False)
    out = CSVDataProvider(tmp_path).get_history("aaa", "2022-02-01", "2022-02-28")
    assert out.index.min() >= pd.Timestamp("2022-02-01")
    assert out.index.max() <= pd.Timestamp("2022-02-28")
    with pytest.raises(DataError):
        CSVDataProvider(tmp_path).get_history("MISSING")


class CountingProvider(DataProvider):
    name = "counting"

    def __init__(self):
        self.calls = 0
        self.inner = SyntheticDataProvider()

    def fetch(self, symbol, start, end, interval):
        self.calls += 1
        return self.inner.fetch(symbol, start, end, interval)


def test_cache_hits_disk(tmp_path):
    inner = CountingProvider()
    cached = CachedDataProvider(inner, tmp_path)
    a = cached.get_history("AAA", "2021-01-01", "2021-06-30")
    b = cached.get_history("AAA", "2021-01-01", "2021-06-30")
    assert inner.calls == 1
    pd.testing.assert_frame_equal(a, b, check_freq=False)
    assert cached.clear() == 1


def test_cache_skips_open_ended_requests(tmp_path):
    inner = CountingProvider()
    cached = CachedDataProvider(inner, tmp_path)
    cached.get_history("AAA", "2024-01-01", None)
    cached.get_history("AAA", "2024-01-01", None)
    assert inner.calls == 2


def test_get_many_raises_on_empty():
    class Empty(DataProvider):
        name = "empty"

        def fetch(self, symbol, start, end, interval):
            return pd.DataFrame()

    with pytest.raises(DataError):
        Empty().get_many(["X"])


def test_get_available_reports_bad_symbols():
    class Partial(DataProvider):
        name = "partial"

        def fetch(self, symbol, start, end, interval):
            if symbol == "BAD":
                return pd.DataFrame()
            if symbol == "ERR":
                raise DataError("boom")
            return SyntheticDataProvider().fetch(symbol, start, end, interval)

    data, errors = Partial().get_available(["good", "BAD", "ERR"], "2022-01-01", "2022-03-01")
    assert list(data) == ["GOOD"] and not data["GOOD"].empty
    assert set(errors) == {"BAD", "ERR"} and errors["ERR"] == "boom"


def test_factory(tmp_path):
    assert isinstance(
        create_data_provider(DataSettings(provider="synthetic")), SyntheticDataProvider
    )
    p = create_data_provider(DataSettings(provider="yahoo", cache_dir=str(tmp_path)))
    assert isinstance(p, CachedDataProvider) and isinstance(p.inner, YahooDataProvider)
    p = create_data_provider(DataSettings(provider="yahoo", cache_enabled=False))
    assert isinstance(p, YahooDataProvider)


def test_yahoo_flattens_multiindex(monkeypatch):
    import yfinance

    cols = pd.MultiIndex.from_product([["Close", "High", "Low", "Open", "Volume"], ["SPY"]])
    fake = pd.DataFrame([[1, 2, 0.5, 1, 100]], columns=cols, index=pd.to_datetime(["2024-01-02"]))
    captured = {}

    def fake_download(symbol, **kw):
        captured.update(kw)
        return fake

    monkeypatch.setattr(yfinance, "download", fake_download)
    out = YahooDataProvider().get_history("SPY", "2024-01-02", "2024-01-02")
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert captured["end"] == "2024-01-03"  # yfinance end is exclusive


@pytest.mark.network
def test_yahoo_live_download():
    df = YahooDataProvider().get_history("SPY", "2024-01-02", "2024-01-31")
    assert len(df) > 15 and validate_ohlcv(df) == []


def test_get_available_rejects_reversed_dates():
    with pytest.raises(DataError, match="after end"):
        SyntheticDataProvider().get_available(["AAPL"], "2023-01-01", "2022-01-01")
