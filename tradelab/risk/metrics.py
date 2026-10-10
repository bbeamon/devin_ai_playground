"""Performance and risk analytics on periodic (default daily) returns."""

from __future__ import annotations

import math
from typing import Any, cast

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _clean(returns: pd.Series) -> pd.Series:
    return pd.Series(returns, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()


def equity_to_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change(fill_method=None).dropna()


def cumulative_returns(returns: pd.Series) -> pd.Series:
    return (1 + _clean(returns)).cumprod() - 1


def total_return(returns: pd.Series) -> float:
    r = _clean(returns)
    return float(np.prod(1 + r.to_numpy()) - 1) if len(r) else 0.0


def cagr(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    r = _clean(returns)
    if len(r) == 0:
        return 0.0
    growth = float(np.prod(1 + r.to_numpy()))
    years = len(r) / periods
    if growth <= 0 or years <= 0:
        return -1.0
    return growth ** (1 / years) - 1


def annualized_volatility(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    r = _clean(returns)
    return float(r.std(ddof=1) * math.sqrt(periods)) if len(r) > 1 else 0.0


def sharpe_ratio(returns: pd.Series, risk_free: float = 0.0, periods: int = TRADING_DAYS) -> float:
    r = _clean(returns) - risk_free / periods
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(r.mean() / sd * math.sqrt(periods)) if sd and sd > 0 else 0.0


def sortino_ratio(returns: pd.Series, risk_free: float = 0.0, periods: int = TRADING_DAYS) -> float:
    r = _clean(returns) - risk_free / periods
    if len(r) < 2:
        return 0.0
    downside = np.sqrt((np.minimum(r, 0.0) ** 2).mean())
    return float(r.mean() / downside * math.sqrt(periods)) if downside > 0 else 0.0


def drawdown_series(returns: pd.Series) -> pd.Series:
    wealth = (1 + _clean(returns)).cumprod()
    return wealth / wealth.cummax().clip(lower=1.0) - 1


def max_drawdown(returns: pd.Series) -> float:
    dd = drawdown_series(returns)
    return float(dd.min()) if len(dd) else 0.0


def max_drawdown_duration(returns: pd.Series) -> int:
    """Longest number of periods spent below a previous equity high."""
    dd = drawdown_series(returns)
    longest = current = 0
    for underwater in (dd < 0).to_numpy():
        current = current + 1 if underwater else 0
        longest = max(longest, current)
    return longest


def calmar_ratio(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    mdd = abs(max_drawdown(returns))
    return cagr(returns, periods) / mdd if mdd > 0 else 0.0


def value_at_risk(returns: pd.Series, level: float = 0.95, method: str = "historical") -> float:
    """One-period VaR as a positive loss fraction (e.g. 0.02 = 2% loss)."""
    r = _clean(returns)
    if len(r) == 0:
        return 0.0
    if method == "historical":
        q = float(np.quantile(r, 1 - level))
    elif method == "parametric":
        from statistics import NormalDist

        q = float(r.mean() + NormalDist().inv_cdf(1 - level) * r.std(ddof=1))
    else:
        raise ValueError("method must be 'historical' or 'parametric'")
    return max(-q, 0.0)


def conditional_var(returns: pd.Series, level: float = 0.95) -> float:
    """Expected shortfall: mean loss on periods at or beyond historical VaR."""
    r = _clean(returns)
    if len(r) == 0:
        return 0.0
    cutoff = np.quantile(r, 1 - level)
    tail = r[r <= cutoff]
    return max(-float(tail.mean()), 0.0) if len(tail) else 0.0


def _aligned(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    df = pd.concat([_clean(a), _clean(b)], axis=1, join="inner").dropna()
    return df.iloc[:, 0], df.iloc[:, 1]


def beta(returns: pd.Series, benchmark: pd.Series) -> float:
    r, b = _aligned(returns, benchmark)
    var = b.var(ddof=1) if len(b) > 1 else 0.0
    return float(r.cov(b) / var) if var and var > 0 else 0.0


def alpha(
    returns: pd.Series, benchmark: pd.Series, risk_free: float = 0.0, periods: int = TRADING_DAYS
) -> float:
    """Annualised Jensen's alpha."""
    r, b = _aligned(returns, benchmark)
    if len(r) < 2:
        return 0.0
    rf = risk_free / periods
    bt = beta(r, b)
    return float(((r - rf).mean() - bt * (b - rf).mean()) * periods)


def tracking_error(returns: pd.Series, benchmark: pd.Series, periods: int = TRADING_DAYS) -> float:
    r, b = _aligned(returns, benchmark)
    return annualized_volatility(r - b, periods)


def information_ratio(
    returns: pd.Series, benchmark: pd.Series, periods: int = TRADING_DAYS
) -> float:
    r, b = _aligned(returns, benchmark)
    active = r - b
    sd = active.std(ddof=1) if len(active) > 1 else 0.0
    return float(active.mean() / sd * math.sqrt(periods)) if sd and sd > 0 else 0.0


def correlation(returns: pd.Series, benchmark: pd.Series) -> float:
    r, b = _aligned(returns, benchmark)
    return float(r.corr(b)) if len(r) > 1 else 0.0


def win_rate(returns: pd.Series) -> float:
    r = _clean(returns)
    r = r[r != 0]
    return float((r > 0).mean()) if len(r) else 0.0


def profit_factor(returns: pd.Series) -> float:
    r = _clean(returns)
    losses = -r[r < 0].sum()
    gains = r[r > 0].sum()
    return float(gains / losses) if losses > 0 else float("inf") if gains > 0 else 0.0


def rolling_volatility(
    returns: pd.Series, window: int = 63, periods: int = TRADING_DAYS
) -> pd.Series:
    return _clean(returns).rolling(window).std() * math.sqrt(periods)


def rolling_sharpe(
    returns: pd.Series, window: int = 63, risk_free: float = 0.0, periods: int = TRADING_DAYS
) -> pd.Series:
    r = _clean(returns) - risk_free / periods
    return r.rolling(window).mean() / r.rolling(window).std() * math.sqrt(periods)


def rolling_beta(returns: pd.Series, benchmark: pd.Series, window: int = 63) -> pd.Series:
    r, b = _aligned(returns, benchmark)
    return r.rolling(window).cov(b) / b.rolling(window).var()


def monthly_returns_table(returns: pd.Series) -> pd.DataFrame:
    """Year x month table of compounded returns, with a full-year column."""
    r = _clean(returns)
    if r.empty:
        return pd.DataFrame()
    idx = pd.DatetimeIndex(r.index)
    monthly = (1 + r).groupby([idx.year, idx.month]).prod() - 1
    table = monthly.unstack(level=1)
    table.columns = [pd.Timestamp(2000, int(m), 1).strftime("%b") for m in table.columns]
    table.index.name = "year"
    table["Year"] = (1 + r).groupby(idx.year).prod() - 1
    return table


def turnover(weights: pd.DataFrame, periods: int = TRADING_DAYS) -> float:
    """Average annualised one-way turnover of a weights frame."""
    if weights is None or len(weights) < 2:
        return 0.0
    return float(weights.diff().iloc[1:].abs().sum(axis=1).mean() * periods / 2)


def exposure(weights: pd.DataFrame) -> float:
    """Fraction of periods with any non-zero position."""
    if weights is None or weights.empty:
        return 0.0
    return float((weights.abs().sum(axis=1) > 1e-9).mean())


def summarize(
    returns: pd.Series,
    benchmark: pd.Series | None = None,
    risk_free: float = 0.0,
    weights: pd.DataFrame | None = None,
    trades: pd.DataFrame | None = None,
    periods: int = TRADING_DAYS,
) -> dict[str, Any]:
    r = _clean(returns)
    out: dict[str, Any] = {
        "total_return": total_return(r),
        "cagr": cagr(r, periods),
        "annual_volatility": annualized_volatility(r, periods),
        "sharpe": sharpe_ratio(r, risk_free, periods),
        "sortino": sortino_ratio(r, risk_free, periods),
        "max_drawdown": max_drawdown(r),
        "max_drawdown_duration": max_drawdown_duration(r),
        "calmar": calmar_ratio(r, periods),
        "var_95": value_at_risk(r, 0.95),
        "cvar_95": conditional_var(r, 0.95),
        "skew": float(cast(float, r.skew())) if len(r) > 2 else 0.0,
        "kurtosis": float(cast(float, r.kurt())) if len(r) > 3 else 0.0,
        "win_rate": win_rate(r),
        "profit_factor": profit_factor(r),
        "best_day": float(r.max()) if len(r) else 0.0,
        "worst_day": float(r.min()) if len(r) else 0.0,
        "periods": len(r),
    }
    if benchmark is not None and len(_clean(benchmark)):
        out.update(
            {
                "benchmark_total_return": total_return(_aligned(r, benchmark)[1]),
                "beta": beta(r, benchmark),
                "alpha": alpha(r, benchmark, risk_free, periods),
                "correlation": correlation(r, benchmark),
                "tracking_error": tracking_error(r, benchmark, periods),
                "information_ratio": information_ratio(r, benchmark, periods),
            }
        )
    if weights is not None:
        out["turnover"] = turnover(weights, periods)
        out["exposure"] = exposure(weights)
    if trades is not None:
        out["num_trades"] = len(trades)
        out["total_costs"] = (
            float(trades[["commission", "slippage_cost"]].sum().sum()) if len(trades) else 0.0
        )
    return out


PERCENT_METRICS = {
    "total_return",
    "cagr",
    "annual_volatility",
    "max_drawdown",
    "var_95",
    "cvar_95",
    "win_rate",
    "best_day",
    "worst_day",
    "benchmark_total_return",
    "alpha",
    "tracking_error",
    "exposure",
    "turnover",
}


def format_metrics(metrics: dict[str, Any]) -> dict[str, str]:
    """Human-readable strings for display."""
    out = {}
    for k, v in metrics.items():
        if isinstance(v, float) and k in PERCENT_METRICS:
            out[k] = f"{v:.2%}"
        elif isinstance(v, float):
            out[k] = "inf" if math.isinf(v) else f"{v:,.2f}"
        else:
            out[k] = f"{v:,}" if isinstance(v, int) else str(v)
    return out
