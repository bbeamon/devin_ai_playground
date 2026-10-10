"""tradelab: modular algorithmic trading research platform.

Live-money trading is intentionally disabled. See ``tradelab.safety``.
"""

from tradelab.safety import LIVE_TRADING_ENABLED, LiveTradingDisabledError

__version__ = "0.1.0"

__all__ = ["LIVE_TRADING_ENABLED", "LiveTradingDisabledError", "__version__"]
