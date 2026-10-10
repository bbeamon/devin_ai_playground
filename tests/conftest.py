import numpy as np
import pandas as pd
import pytest

from tradelab.data import SyntheticDataProvider


def make_ohlcv(closes, start="2024-01-01", opens=None) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    idx = pd.bdate_range(start, periods=len(closes), name="date")
    opens = closes if opens is None else np.asarray(opens, dtype=float)
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.01,
            "low": np.minimum(opens, closes) * 0.99,
            "close": closes,
            "volume": 1_000_000.0,
        },
        index=idx,
    )


@pytest.fixture
def synthetic():
    return SyntheticDataProvider(seed=7)


@pytest.fixture
def universe_data(synthetic):
    return synthetic.get_many(["AAA", "BBB", "CCC"], "2019-01-01", "2023-12-31")
