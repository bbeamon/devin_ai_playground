"""Typed configuration loaded from YAML, with secrets from environment / .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tradelab.safety import LiveTradingDisabledError, assert_paper_mode

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


class DataSettings(BaseModel):
    provider: Literal["yahoo", "alpaca", "csv", "synthetic"] = "yahoo"
    cache_enabled: bool = True
    cache_dir: str = ".cache/data"
    csv_dir: str = "data/csv"


class BacktestSettings(BaseModel):
    initial_cash: float = Field(100_000.0, gt=0)
    commission_per_share: float = Field(0.0, ge=0)
    commission_pct: float = Field(0.0, ge=0, lt=1)
    min_commission: float = Field(0.0, ge=0)
    slippage_bps: float = Field(5.0, ge=0)
    execution: Literal["next_open", "close"] = "next_open"
    allow_short: bool = False
    fractional_shares: bool = True
    # Skip trades when |target weight - current weight| is below this (avoids daily drift
    # re-balancing). Full exits are always executed.
    rebalance_threshold: float = Field(0.01, ge=0, lt=1)


class RiskSettings(BaseModel):
    risk_free_rate: float = 0.02
    max_position_weight: float = Field(0.25, gt=0, le=10)
    max_gross_leverage: float = Field(1.0, gt=0, le=10)
    max_order_notional: float = Field(25_000.0, gt=0)
    max_orders_per_run: int = Field(50, gt=0)
    min_trade_notional: float = Field(1.0, ge=0)


class BrokerSettings(BaseModel):
    name: Literal["simulated", "alpaca_paper", "ibkr", "schwab", "fidelity"] = "simulated"
    trading_mode: str = "paper"

    @field_validator("trading_mode")
    @classmethod
    def _paper_only(cls, v: str) -> str:
        try:
            assert_paper_mode(v)
        except LiveTradingDisabledError as exc:
            raise ValueError(str(exc)) from exc
        return v


class Settings(BaseModel):
    data: DataSettings = DataSettings()
    backtest: BacktestSettings = BacktestSettings()
    risk: RiskSettings = RiskSettings()
    broker: BrokerSettings = BrokerSettings()


class AlpacaCredentials(BaseSettings):
    """Alpaca paper credentials from env vars ALPACA_API_KEY / ALPACA_SECRET_KEY or .env."""

    model_config = SettingsConfigDict(env_prefix="ALPACA_", env_file=".env", extra="ignore")

    api_key: str = ""
    secret_key: str = ""
    data_feed: str = "iex"

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret_key)


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a mapping at the top level")
    return data


def load_settings(path: str | Path | None = None) -> Settings:
    cfg_path = Path(path or os.environ.get("TRADELAB_CONFIG") or DEFAULT_CONFIG_PATH)
    if not cfg_path.exists():
        return Settings()
    return Settings.model_validate(load_yaml(cfg_path))
