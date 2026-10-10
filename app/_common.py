"""Shared helpers for Streamlit pages."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # allow `streamlit run app/Home.py` without `pip install -e .`
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from tradelab.config import DataSettings, Settings, load_settings  # noqa: E402
from tradelab.data import create_data_provider  # noqa: E402
from tradelab.data.base import DataError  # noqa: E402

PROVIDERS = ["yahoo", "synthetic", "alpaca", "csv"]

PAPER_BANNER = (
    "Paper trading only. Live-money trading is disabled in this build; orders can only go "
    "to the in-memory simulator or an Alpaca paper account."
)


@st.cache_resource
def get_settings() -> Settings:
    return load_settings()


@st.cache_data(show_spinner="Loading market data...", ttl=3600)
def load_history(
    provider: str, symbols: tuple[str, ...], start: date, end: date
) -> dict[str, pd.DataFrame]:
    base = get_settings().data
    dp = create_data_provider(DataSettings(**{**base.model_dump(), "provider": provider}))
    return dp.get_many(list(symbols), start, end)


def parse_symbols(text: str) -> list[str]:
    return list(
        dict.fromkeys(s.strip().upper() for s in text.replace("\n", ",").split(",") if s.strip())
    )


def sidebar_data_inputs(
    default_symbols: str = "AAPL, MSFT, NVDA, GOOGL", key: str = "data"
) -> tuple[str, list[str], date, date]:
    st.sidebar.header("Data")
    provider = st.sidebar.selectbox(
        "Provider",
        PROVIDERS,
        index=PROVIDERS.index(get_settings().data.provider),
        key=f"{key}_prov",
        help="'synthetic' works offline; 'alpaca' needs API keys in .env",
    )
    symbols = parse_symbols(
        st.sidebar.text_area("Symbols (comma separated)", default_symbols, key=f"{key}_syms")
    )
    c1, c2 = st.sidebar.columns(2)
    start = c1.date_input("Start", date(2018, 1, 1), key=f"{key}_start")
    end = c2.date_input("End", date.today(), key=f"{key}_end")
    return provider, symbols, start, end


def safe_load(
    provider: str, symbols: list[str], start: date, end: date
) -> dict[str, pd.DataFrame] | None:
    if not symbols:
        st.warning("Enter at least one symbol.")
        return None
    try:
        return load_history(provider, tuple(symbols), start, end)
    except (DataError, ValueError, KeyError) as exc:
        st.error(f"Could not load data: {exc}")
        return None


def metric_cards(metrics: dict, keys: list[tuple[str, str]], cols: int = 4) -> None:
    from tradelab.risk import format_metrics

    fmt = format_metrics(metrics)
    columns = st.columns(cols)
    for i, (k, label) in enumerate(keys):
        if k in fmt:
            columns[i % cols].metric(label, fmt[k])
