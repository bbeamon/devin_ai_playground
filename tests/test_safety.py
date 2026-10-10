import pathlib
import re

import pytest

import tradelab
from tradelab import safety
from tradelab.brokers import SimulatedBroker, create_broker
from tradelab.brokers.alpaca_paper import AlpacaPaperBroker
from tradelab.brokers.base import Broker
from tradelab.brokers.models import OrderRequest, OrderSide
from tradelab.brokers.stubs import FidelityBroker, InteractiveBrokersBroker, SchwabBroker
from tradelab.config import BrokerSettings, Settings
from tradelab.execution import Rebalancer
from tradelab.safety import LiveTradingDisabledError

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_live_trading_constant_is_false():
    assert safety.LIVE_TRADING_ENABLED is False
    assert tradelab.LIVE_TRADING_ENABLED is False


def test_env_var_cannot_enable_live():
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "TRADELAB_LIVE": "1",
        "TRADELAB_ENABLE_LIVE": "1",
        "LIVE_TRADING_ENABLED": "1",
    }
    out = subprocess.run(
        [sys.executable, "-c", "import tradelab.safety as s; print(s.LIVE_TRADING_ENABLED)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    assert out.stdout.strip() == "False"


@pytest.mark.parametrize("mode", ["live", "LIVE", "production", "", "Paper"])
def test_non_paper_modes_rejected(mode):
    with pytest.raises(LiveTradingDisabledError):
        safety.assert_paper_mode(mode)
    with pytest.raises(ValueError):
        BrokerSettings(trading_mode=mode)


def test_settings_reject_live_mode_from_yaml_dict():
    with pytest.raises(ValueError):
        Settings.model_validate({"broker": {"trading_mode": "live"}})


def test_alpaca_live_url_rejected():
    with pytest.raises(LiveTradingDisabledError):
        safety.assert_alpaca_paper_url("https://api.alpaca.markets")
    safety.assert_alpaca_paper_url("https://paper-api.alpaca.markets")


def test_alpaca_live_key_rejected():
    with pytest.raises(LiveTradingDisabledError):
        AlpacaPaperBroker(api_key="AKLIVEKEY", secret_key="x")


def test_alpaca_client_with_live_base_url_rejected():
    class FakeClient:
        _base_url = "https://api.alpaca.markets"

    with pytest.raises(LiveTradingDisabledError):
        AlpacaPaperBroker(trading_client=FakeClient())


def test_alpaca_real_client_is_pinned_to_paper():
    broker = AlpacaPaperBroker(api_key="PKTEST", secret_key="secret")
    assert "paper-api" in str(broker._client._base_url.value)
    assert broker.is_paper


@pytest.mark.parametrize("port", [7496, 4001, 1234])
def test_ibkr_live_ports_rejected(port):
    with pytest.raises(LiveTradingDisabledError):
        InteractiveBrokersBroker(port=port)


def test_ibkr_paper_port_accepted_but_stubbed():
    b = InteractiveBrokersBroker(port=7497)
    with pytest.raises(NotImplementedError):
        b.get_account()


@pytest.mark.parametrize("cls", [SchwabBroker, FidelityBroker])
def test_brokers_without_paper_cannot_submit(cls):
    with pytest.raises(LiveTradingDisabledError):
        cls().submit_order(OrderRequest("AAPL", 1, OrderSide.BUY))


def test_non_paper_broker_blocked_by_base_template_and_rebalancer():
    class LiveLike(SimulatedBroker):
        @property
        def is_paper(self) -> bool:
            return False

    b = LiveLike(prices={"AAPL": 100})
    with pytest.raises(LiveTradingDisabledError):
        b.submit_order(OrderRequest("AAPL", 1, OrderSide.BUY))
    with pytest.raises(LiveTradingDisabledError):
        b.close_position("AAPL")
    with pytest.raises(LiveTradingDisabledError):
        Rebalancer(b)


def test_factory_only_returns_paper_or_stub():
    assert create_broker("simulated").is_paper
    for name in ("schwab", "fidelity"):
        assert not create_broker(name).capabilities.implemented


def test_base_broker_defaults_to_not_paper():
    assert Broker.is_paper.fget(object()) is False  # type: ignore[attr-defined]


def test_source_never_requests_live_alpaca_client():
    offenders = []
    for path in list((ROOT / "tradelab").rglob("*.py")) + list((ROOT / "app").rglob("*.py")):
        text = path.read_text()
        if re.search(r"paper\s*=\s*False", text) or "LIVE_TRADING_ENABLED = True" in text:
            offenders.append(str(path))
    assert offenders == []
