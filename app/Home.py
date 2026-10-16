import base64
import pathlib

import _common  # noqa: F401  (path setup)
import streamlit as st

from tradelab import LIVE_TRADING_ENABLED, __version__
from tradelab.strategies import list_strategies

st.set_page_config(page_title="TradeLab", page_icon=":chart_with_upwards_trend:", layout="wide")
assert LIVE_TRADING_ENABLED is False

HERO = pathlib.Path(__file__).parent / "assets" / "hero.svg"
hero_uri = "data:image/svg+xml;base64," + base64.b64encode(HERO.read_bytes()).decode()

st.markdown(
    f"""
<style>
.tl-hero {{
  position: relative; border-radius: 22px; overflow: hidden; padding: 4.5rem 3rem 3.5rem;
  background: linear-gradient(90deg, rgba(11,16,32,.92) 0%, rgba(11,16,32,.45) 50%,
              rgba(11,16,32,.05) 100%), url("{hero_uri}") center / cover no-repeat;
  box-shadow: 0 18px 50px rgba(34,211,238,.18); margin-bottom: 1.5rem;
}}
.tl-hero .tl-title {{
  font-size: clamp(3rem, 7vw, 5.5rem); font-weight: 900; letter-spacing: -.03em; line-height: 1;
  margin: 0; background: linear-gradient(90deg, #22d3ee, #a78bfa 55%, #f472b6);
  -webkit-background-clip: text !important; background-clip: text !important;
  -webkit-text-fill-color: transparent !important; color: transparent !important; padding: 0;
  font-family: inherit;
}}
.tl-tagline {{ color: #e2e8f0; font-size: 1.35rem; font-weight: 600; margin: 1rem 0 .4rem; }}
.tl-credit {{ color: #94a3b8; font-size: 1.05rem; margin: 0; }}
.tl-credit b {{ color: #f8fafc; }}
.tl-pills {{ margin-top: 1.6rem; display: flex; gap: .6rem; flex-wrap: wrap; }}
.tl-pill {{
  padding: .35rem .9rem; border-radius: 999px; font-size: .85rem; font-weight: 600; color: #e2e8f0;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.18);
  backdrop-filter: blur(4px);
}}
.tl-pill.paper {{ color: #34d399; border-color: rgba(52,211,153,.5); }}
.tl-card {{
  border-radius: 16px; padding: 1.2rem 1.3rem; height: 100%;
  background: linear-gradient(160deg, rgba(34,211,238,.08), rgba(167,139,250,.08));
  border: 1px solid rgba(148,163,184,.25);
}}
.tl-badge {{
  display: inline-block; font-weight: 800; font-size: .9rem; color: #fff; padding: .2rem .55rem;
  border-radius: 8px; background: linear-gradient(90deg, #22d3ee, #a78bfa);
}}
.tl-card h4 {{ margin: .2rem 0 .4rem; overflow-wrap: normal; word-break: normal; hyphens: manual; }}
@media (min-width: 1100px) {{ .tl-card {{ min-height: 230px; }} }}
@media (min-width: 641px) and (max-width: 1099px) {{
  [data-testid="stHorizontalBlock"]:has(.tl-card) {{ flex-wrap: wrap !important; }}
  [data-testid="stHorizontalBlock"]:has(.tl-card) > [data-testid="stColumn"] {{
    flex: 1 1 calc(33% - 1rem) !important; min-width: calc(33% - 1rem) !important;
  }}
}}
.tl-card p {{ margin: 0; opacity: .85; font-size: .95rem; }}
</style>
<div class="tl-hero">
  <div class="tl-title">TradeLab</div>
  <p class="tl-tagline">Algorithmic trading research &middot; backtesting &middot; risk analytics</p>
  <p class="tl-credit">Created by <b>Bridget Beamon</b> in collaboration with <b>Devin AI</b></p>
  <div class="tl-pills">
    <span class="tl-pill paper">&#9679; Paper trading only</span>
    <span class="tl-pill">v{__version__}</span>
    <span class="tl-pill">{len(list_strategies())} strategies</span>
    <span class="tl-pill">Alpaca paper &middot; Simulator</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)
st.info(_common.PAPER_BANNER)

FEATURES = [
    (
        "01",
        "Data Explorer",
        "Load historical OHLCV, check data quality, chart candles and indicators.",
    ),
    ("02", "Backtest", "Configure a strategy in the UI or YAML and run a cost-aware backtest."),
    ("03", "Risk Analytics", "Drawdowns, VaR/CVaR, rolling Sharpe and volatility, benchmark beta."),
    ("04", "Optimizer", "Grid-search parameters with an in-sample / out-of-sample split."),
    (
        "05",
        "Paper Trading",
        "Preview and submit rebalance orders to the simulator or Alpaca paper.",
    ),
]
for col, (num, title, desc) in zip(st.columns(len(FEATURES)), FEATURES, strict=True):
    col.markdown(
        f'<div class="tl-card"><span class="tl-badge">{num}</span>'
        f"<h4>{title}</h4><p>{desc}</p></div>",
        unsafe_allow_html=True,
    )

st.markdown("## About TradeLab")
about, how = st.columns([3, 2], gap="large")
about.markdown(
    """
**TradeLab** is a research workbench for designing, testing and stress-testing systematic
equity strategies before any capital is involved. It brings the full research loop into one
place: get the data, define a strategy, backtest it with realistic costs, measure the risk,
tune the parameters without fooling yourself, and then rehearse execution on a paper account.

**Built for safety.** Live-money trading is disabled in code, not by a setting. Orders can
only go to the built-in simulator or an Alpaca *paper* account, and every rebalance needs an
explicit confirmation. Interactive Brokers, Schwab and Fidelity adapters are planned.

**Who it's for:** anyone learning quantitative trading, or evaluating an idea, who wants honest
numbers: no look-ahead fills, transaction costs included, and out-of-sample results shown next
to in-sample ones.
"""
)
how.markdown(
    """
#### How to use it
1. **Data Explorer** – pick a provider (*synthetic* works offline) and symbols.
2. **Backtest** – choose a strategy and costs, then run it.
3. **Risk Analytics** – review drawdowns, VaR and rolling metrics of the last backtest.
4. **Optimizer** – search parameter ranges; judge results on the out-of-sample columns.
5. **Paper Trading** – preview target orders and submit them to a paper account.

Research and education only; not investment advice.
"""
)

with st.expander(f"Available strategies ({len(list_strategies())})"):
    st.table([{"name": k, "description": v.description} for k, v in list_strategies().items()])
