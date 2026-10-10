"""Central live-trading kill switch.

Live-money trading is disabled by design. ``LIVE_TRADING_ENABLED`` is a hard-coded
constant (not read from config or environment) and every broker order path calls
:func:`assert_paper_broker` before anything is sent. Enabling live trading requires a
deliberate code change and review; there is no runtime flag.
"""

from __future__ import annotations

from typing import Any, Final
from urllib.parse import urlparse

LIVE_TRADING_ENABLED: Final[bool] = False

PAPER_MODE: Final[str] = "paper"

ALPACA_PAPER_HOST: Final[str] = "paper-api.alpaca.markets"
ALPACA_LIVE_HOST: Final[str] = "api.alpaca.markets"

IBKR_PAPER_PORTS: Final[frozenset[int]] = frozenset({7497, 4002})
IBKR_LIVE_PORTS: Final[frozenset[int]] = frozenset({7496, 4001})


class LiveTradingDisabledError(RuntimeError):
    """Raised whenever code attempts to use a live-money trading path."""


def assert_paper_mode(mode: str) -> None:
    if mode != PAPER_MODE or LIVE_TRADING_ENABLED:
        raise LiveTradingDisabledError(
            f"Trading mode {mode!r} is not allowed. Only {PAPER_MODE!r} is supported; "
            "live-money trading is disabled in tradelab."
        )


def assert_paper_broker(broker: Any) -> None:
    if not getattr(broker, "is_paper", False):
        raise LiveTradingDisabledError(
            f"Broker {getattr(broker, 'name', broker)!r} is not a paper-trading broker; "
            "live-money trading is disabled in tradelab."
        )


def assert_alpaca_paper_url(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host != ALPACA_PAPER_HOST:
        raise LiveTradingDisabledError(
            f"Alpaca endpoint {url!r} is not the paper endpoint ({ALPACA_PAPER_HOST})."
        )


def check_alpaca_paper_key(api_key: str) -> None:
    """Reject keys that look like Alpaca live keys.

    Alpaca paper keys conventionally start with ``PK`` and live keys with ``AK``. This is a
    defence-in-depth heuristic; the primary guard is that the client is always pinned to
    the paper endpoint.
    """
    if api_key.upper().startswith("AK"):
        raise LiveTradingDisabledError(
            "The supplied Alpaca API key looks like a LIVE key (prefix 'AK'). "
            "Use paper-account keys (prefix 'PK')."
        )


def assert_ibkr_paper_port(port: int) -> None:
    if port in IBKR_LIVE_PORTS or port not in IBKR_PAPER_PORTS:
        raise LiveTradingDisabledError(
            f"IBKR port {port} is not a known paper-trading port {sorted(IBKR_PAPER_PORTS)}."
        )
