"""Shared helpers for Streamlit pages."""

from __future__ import annotations

import base64
import re
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


HEADER_CSS = """
<style>
.tl-page {
  border-radius: 16px; padding: 1.4rem 1.8rem; margin: 0 0 1.2rem; overflow: hidden;
  background: linear-gradient(90deg, rgba(11,16,32,.95) 0%, rgba(11,16,32,.75) 55%,
              rgba(11,16,32,.35) 100%), url("__HERO__") right center / cover no-repeat;
  box-shadow: 0 10px 30px rgba(124,58,237,.15);
}
.tl-page .tl-brand {
  font-size: .8rem; font-weight: 800; letter-spacing: .18em; text-transform: uppercase;
  background: linear-gradient(90deg, #22d3ee, #a78bfa 55%, #f472b6);
  -webkit-background-clip: text !important; background-clip: text !important;
  -webkit-text-fill-color: transparent !important; color: transparent !important;
}
.tl-page .tl-page-title {
  color: #f8fafc; font-size: 2.2rem; font-weight: 800; line-height: 1.15; margin: .2rem 0 0;
}
.tl-page .tl-page-sub { color: #cbd5e1; font-size: 1rem; margin: .35rem 0 0; }
</style>
"""


@st.cache_resource
def _hero_uri() -> str:
    svg = (Path(__file__).parent / "assets" / "hero.svg").read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode()


def page_header(title: str, subtitle: str = "") -> None:
    """Slim TradeLab-branded banner used at the top of every page."""
    sub = f'<p class="tl-page-sub">{subtitle}</p>' if subtitle else ""
    st.markdown(
        HEADER_CSS.replace("__HERO__", _hero_uri())
        + f'<div class="tl-page"><div class="tl-brand">TradeLab</div>'
        f'<div class="tl-page-title">{title}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_settings() -> Settings:
    return load_settings()


TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,14}$")


@st.cache_data(show_spinner="Loading market data...", ttl=3600)
def load_history(
    provider: str, symbols: tuple[str, ...], start: date, end: date
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    base = get_settings().data
    dp = create_data_provider(DataSettings(**{**base.model_dump(), "provider": provider}))
    return dp.get_available(list(symbols), start, end)


def parse_symbols(text: str) -> list[str]:
    return list(
        dict.fromkeys(s.strip().upper() for s in re.split(r"[,\s;]+", text) if s.strip().strip("$"))
    )


def split_valid_tickers(symbols: list[str]) -> tuple[list[str], list[str]]:
    """Split into (well-formed, malformed) ticker strings; a leading ``$`` is allowed."""
    good, bad = [], []
    for s in symbols:
        t = s.lstrip("$")
        if TICKER_RE.match(t):
            good.append(t)
        else:
            bad.append(s)
    return list(dict.fromkeys(good)), bad


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
        st.sidebar.text_area(
            "Symbols (comma separated)",
            default_symbols,
            key=f"{key}_syms",
            help="Type any ticker, e.g. NVDA, RTX, TMUS. Unknown tickers are reported.",
        )
    )
    if provider == "synthetic":
        st.sidebar.caption(
            "Synthetic data generates prices for any ticker, so typos are not detected. "
            "Use 'yahoo' or 'alpaca' for real prices."
        )
    c1, c2 = st.sidebar.columns(2)
    start = c1.date_input("Start", date(2018, 1, 1), key=f"{key}_start")
    end = c2.date_input("End", date.today(), key=f"{key}_end")
    return provider, symbols, start, end


def safe_load(
    provider: str,
    symbols: list[str],
    start: date,
    end: date,
    allow_partial: bool = False,
) -> dict[str, pd.DataFrame] | None:
    """Load bars, reporting invalid tickers in the UI.

    With ``allow_partial`` the valid symbols are returned and the invalid ones listed in a
    warning; otherwise any invalid symbol is an error and ``None`` is returned.
    """
    symbols, malformed = split_valid_tickers(symbols)
    if not symbols and not malformed:
        st.warning("Enter at least one symbol.")
        return None
    try:
        data, errors = load_history(provider, tuple(symbols), start, end) if symbols else ({}, {})
    except (DataError, ValueError, KeyError) as exc:
        st.error(f"Could not load data: {exc}")
        return None
    bad = {s: "not a valid ticker format" for s in malformed} | errors
    if bad:
        details = "\n".join(f"- **{s}**: {why}" for s, why in bad.items())
        msg = f"Invalid or unavailable symbol(s): {', '.join(bad)}. Check the ticker.\n\n{details}"
        if not allow_partial or not data:
            st.error(msg)
            return None
        st.warning(msg)
    return data or None


def metric_cards(metrics: dict, keys: list[tuple[str, str]], cols: int = 4) -> None:
    from tradelab.risk import format_metrics

    fmt = format_metrics(metrics)
    columns = st.columns(cols)
    for i, (k, label) in enumerate(keys):
        if k in fmt:
            columns[i % cols].metric(label, fmt[k])
