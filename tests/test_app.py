"""Smoke tests for the Streamlit pages using streamlit.testing (offline, synthetic data)."""

import pathlib

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def _run(path, **state):
    at = AppTest.from_file(str(path), default_timeout=120)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def test_home():
    at = _run(APP / "Home.py")
    assert not at.exception
    assert "Paper trading only" in at.info[0].value


def test_data_explorer_synthetic():
    at = AppTest.from_file(str(APP / "pages" / "1_Data_Explorer.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("synthetic").run()
    assert not at.exception
    assert any(m.label == "Bars" for m in at.metric)


def test_backtest_page_runs_synthetic():
    at = AppTest.from_file(str(APP / "pages" / "2_Backtest.py"), default_timeout=180).run()
    at.sidebar.selectbox[0].set_value("synthetic").run()
    at.sidebar.button[0].click().run()
    assert not at.exception, at.exception
    assert "last_result" in at.session_state
    assert any(m.label == "Sharpe" for m in at.metric)


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
