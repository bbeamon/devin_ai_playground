import pytest

from tradelab.config import AlpacaCredentials, Settings, load_settings, load_yaml


def test_default_yaml_loads():
    s = load_settings()
    assert s.broker.trading_mode == "paper"
    assert s.backtest.execution == "next_open"


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "nope.yaml") == Settings()


def test_invalid_values(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("backtest:\n  initial_cash: -5\n")
    with pytest.raises(ValueError):
        load_settings(p)
    p.write_text("- a\n- b\n")
    with pytest.raises(ValueError):
        load_yaml(p)


def test_alpaca_credentials_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALPACA_API_KEY", "PKX")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    c = AlpacaCredentials()
    assert c.configured and c.api_key == "PKX"
    monkeypatch.delenv("ALPACA_API_KEY")
    assert not AlpacaCredentials().configured
