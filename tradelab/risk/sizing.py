"""Convert per-symbol signals into portfolio target weights."""

from __future__ import annotations

import numpy as np
import pandas as pd


def equal_weight(signals: pd.DataFrame) -> pd.DataFrame:
    """Each symbol gets 1/N of capital scaled by its signal."""
    n = max(signals.shape[1], 1)
    return signals / n


def fixed_fraction(signals: pd.DataFrame, fraction: float) -> pd.DataFrame:
    return signals * fraction


def volatility_target(
    signals: pd.DataFrame,
    closes: pd.DataFrame,
    target_vol: float = 0.10,
    lookback: int = 20,
    max_asset_leverage: float = 1.0,
) -> pd.DataFrame:
    """Scale each symbol so its standalone annualised vol ~= ``target_vol`` / N.

    Uses trailing realised volatility up to and including bar t (no look-ahead).
    """
    rets = closes.pct_change(fill_method=None)
    vol = rets.rolling(lookback, min_periods=lookback).std() * np.sqrt(252)
    scale = (target_vol / vol).clip(upper=max_asset_leverage).replace([np.inf, -np.inf], np.nan)
    n = max(signals.shape[1], 1)
    return (signals * scale.reindex_like(signals)).fillna(0.0) / n


def apply_weight_limits(
    weights: pd.DataFrame,
    max_position_weight: float,
    max_gross_leverage: float,
    allow_short: bool,
) -> pd.DataFrame:
    """Enforce long-only (optional), per-position caps and a gross-leverage cap."""
    w = weights.fillna(0.0)
    if not allow_short:
        w = w.clip(lower=0.0)
    w = w.clip(-max_position_weight, max_position_weight)
    gross = w.abs().sum(axis=1)
    factor = (max_gross_leverage / gross).where(gross > max_gross_leverage, 1.0)
    return w.mul(factor, axis=0)
