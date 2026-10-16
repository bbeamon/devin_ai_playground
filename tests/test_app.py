"""Smoke tests for the Streamlit pages using streamlit.testing (offline, synthetic data)."""

import pathlib
import sys

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
if str(APP) not in sys.path:  # pages import the shared `_common` helper module
    sys.path.insert(0, str(APP))


def _run(path, **state):
    at = AppTest.from_file(str(path), default_timeout=120)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def test_home():
    at = _run(APP / "Home.py")
    assert not at.exception
    assert "Paper trading only" in at.info[0].value
    page = " ".join(m.value for m in at.markdown)
    assert "TradeLab" in page and "Bridget Beamon" in page and "About TradeLab" in page


def test_data_explorer_synthetic():
    at = AppTest.from_file(str(APP / "pages" / "1_Data_Explorer.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("synthetic").run()
    assert not at.exception
    assert any(m.label == "Bars" for m in at.metric)
    assert any("Compare tickers" in s.value for s in at.subheader)
    assert "TradeLab" in " ".join(m.value for m in at.markdown)


def test_data_explorer_any_ticker_and_invalid_symbol_warning():
    at = AppTest.from_file(str(APP / "pages" / "1_Data_Explorer.py"), default_timeout=120).run()
    at.selectbox(key="explorer_prov").set_value("synthetic")
    at.text_area(key="explorer_syms").set_value("rtx, $TMUS nvda, BAD!!").run()
    assert not at.exception, at.exception
    assert "BAD!!" in at.warning[0].value
    assert set(next(s for s in at.selectbox if s.label == "Symbol").options) == {
        "RTX",
        "TMUS",
        "NVDA",
    }


def test_data_explorer_only_invalid_symbols_shows_error():
    at = AppTest.from_file(str(APP / "pages" / "1_Data_Explorer.py"), default_timeout=120).run()
    at.selectbox(key="explorer_prov").set_value("synthetic")
    at.text_area(key="explorer_syms").set_value("???").run()
    assert not at.exception
    assert "???" in at.error[0].value
    assert not any(m.label == "Bars" for m in at.metric)


@pytest.mark.network
def test_data_explorer_yahoo_unknown_ticker():
    at = AppTest.from_file(str(APP / "pages" / "1_Data_Explorer.py"), default_timeout=180).run()
    at.selectbox(key="explorer_prov").set_value("yahoo")
    at.text_area(key="explorer_syms").set_value("NVDA, RTX, TMUS, XYZFAKE1").run()
    assert not at.exception, at.exception
    assert "XYZFAKE1" in at.warning[0].value
    assert any(m.label == "Bars" for m in at.metric)


def test_backtest_page_runs_synthetic():
    at = AppTest.from_file(str(APP / "pages" / "2_Backtest.py"), default_timeout=180).run()
    at.sidebar.selectbox[0].set_value("synthetic").run()
    at.sidebar.button[0].click().run()
    assert not at.exception, at.exception
    assert "last_result" in at.session_state
    assert any(m.label == "Sharpe" for m in at.metric)


def test_backtest_mobile_run_button():
    at = AppTest.from_file(str(APP / "pages" / "2_Backtest.py"), default_timeout=180).run()
    at.sidebar.selectbox[0].set_value("synthetic").run()
    at.button(key="tl_mobile_run").click().run()
    assert not at.exception, at.exception
    assert "last_result" in at.session_state


def test_backtest_failed_run_clears_previous_result():
    at = AppTest.from_file(str(APP / "pages" / "2_Backtest.py"), default_timeout=180).run()
    at.sidebar.selectbox[0].set_value("synthetic").run()
    at.sidebar.button[0].click().run()
    assert "last_result" in at.session_state
    at.sidebar.text_area[0].set_value("AAPL, BAD!!").run()
    at.sidebar.button[0].click().run()
    assert not at.exception, at.exception
    assert any("BAD!!" in e.value for e in at.error)
    assert "last_result" not in at.session_state
    assert not any(m.label == "Sharpe" for m in at.metric)


def test_risk_page_needs_result_then_renders(universe_data):
    at = _run(APP / "pages" / "3_Risk_Analytics.py")
    assert not at.exception and "Run a backtest" in at.info[0].value

    from tradelab.backtest import run_backtest
    from tradelab.strategies import StrategyConfig

    cfg = StrategyConfig(strategy="momentum", params={"lookback": 20}, universe=list(universe_data))
    res = run_backtest(cfg, data=universe_data, benchmark=universe_data["AAA"]["close"])
    at = _run(APP / "pages" / "3_Risk_Analytics.py", last_result=res)
    assert not at.exception, at.exception
    assert any(m.label == "Calmar" for m in at.metric)


def test_paper_trading_simulated():
    at = _run(APP / "pages" / "5_Paper_Trading.py")
    assert not at.exception, at.exception
    assert any(m.label == "Mode" and m.value == "PAPER" for m in at.metric)


def test_paper_trading_stub_broker():
    at = AppTest.from_file(str(APP / "pages" / "5_Paper_Trading.py"), default_timeout=60).run()
    at.sidebar.selectbox[0].set_value("schwab").run()
    assert not at.exception
    assert any("planned integration" in i.value for i in at.info)


def test_optimizer_page_loads():
    at = _run(APP / "pages" / "4_Optimizer.py")
    assert not at.exception, at.exception


def test_optimizer_results_survive_rerun():
    at = AppTest.from_file(str(APP / "pages" / "4_Optimizer.py"), default_timeout=180).run()
    at.selectbox(key="opt_prov").set_value("synthetic").run()
    next(b for b in at.button if b.label == "Run grid search").click().run()
    assert not at.exception, at.exception
    assert len(at.dataframe) == 1
    at.run()  # e.g. the rerun triggered by the download button
    assert len(at.dataframe) == 1


def test_paper_rejected_manual_order_shows_error():
    at = AppTest.from_file(str(APP / "pages" / "5_Paper_Trading.py"), default_timeout=60).run()
    at.session_state["broker_simulated"].set_price("AAPL", 100.0)
    side = next(s for s in at.selectbox if s.label == "Side")
    side.set_value("sell")
    next(b for b in at.button if b.label == "Submit paper order").click().run()
    assert not at.exception, at.exception
    assert any("rejected" in e.value for e in at.error)
    assert not any("rejected" in s.value for s in at.success)


def test_load_history_does_not_cache_failures(monkeypatch):
    from datetime import date

    import _common

    calls = []

    class Flaky:
        def get_available(self, symbols, start, end):
            calls.append(symbols)
            if len(calls) == 1:
                return {}, {"AAPL": "provider timeout"}
            return {"AAPL": "bars"}, {}

    monkeypatch.setattr(_common, "create_data_provider", lambda _settings: Flaky())
    _common._cached_history.clear()
    args = ("synthetic", ("AAPL",), date(2022, 1, 1), date(2022, 2, 1))
    assert _common.load_history(*args)[1] == {"AAPL": "provider timeout"}
    assert _common.load_history(*args) == ({"AAPL": "bars"}, {})
    assert _common.load_history(*args) == ({"AAPL": "bars"}, {})
    assert len(calls) == 2
    _common._cached_history.clear()
