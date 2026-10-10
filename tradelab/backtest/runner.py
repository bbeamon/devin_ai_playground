"""High-level helpers: run a StrategyConfig end-to-end, and grid-search parameters."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pandas as pd

from tradelab.backtest.engine import Backtester, BacktestResult
from tradelab.config import Settings
from tradelab.data.base import DataProvider
from tradelab.strategies.engine import StrategyConfig, StrategyEngine


def load_data(
    config: StrategyConfig, provider: DataProvider
) -> tuple[dict[str, pd.DataFrame], pd.Series | None]:
    data = provider.get_many(config.universe, config.start, config.end)
    bench = None
    if config.benchmark:
        bench_df = data.get(config.benchmark)
        if bench_df is None:
            bench_df = provider.get_history(config.benchmark, config.start, config.end)
        bench = bench_df["close"] if not bench_df.empty else None
    return data, bench


def run_backtest(
    config: StrategyConfig,
    settings: Settings | None = None,
    provider: DataProvider | None = None,
    data: dict[str, pd.DataFrame] | None = None,
    benchmark: pd.Series | None = None,
) -> BacktestResult:
    settings = settings or Settings()
    if data is None:
        if provider is None:
            raise ValueError("Provide either `provider` or `data`")
        data, benchmark = load_data(config, provider)
    engine = StrategyEngine(config, settings.risk, allow_short=settings.backtest.allow_short)
    signals = engine.signals(data)
    weights = engine.target_weights(data, signals)
    result = Backtester(settings.backtest, settings.risk).run(data, weights, benchmark, signals)
    result.metadata["strategy"] = config.model_dump(mode="json")
    return result


def grid_search(
    config: StrategyConfig,
    param_grid: Mapping[str, Sequence[Any]],
    data: dict[str, pd.DataFrame],
    settings: Settings | None = None,
    benchmark: pd.Series | None = None,
    split_date: str | pd.Timestamp | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Backtest every parameter combination.

    If ``split_date`` is given, metrics are reported separately for the in-sample
    (before) and out-of-sample (on/after) periods to help detect over-fitting.
    """
    keys = list(param_grid)
    combos = list(itertools.product(*(param_grid[k] for k in keys)))
    rows: list[dict[str, Any]] = []
    split = pd.Timestamp(split_date) if split_date is not None else None
    for i, values in enumerate(combos, 1):
        params = {**config.params, **dict(zip(keys, values, strict=True))}
        row: dict[str, Any] = dict(zip(keys, values, strict=True))
        try:
            cfg = config.model_copy(update={"params": params})
            res = run_backtest(cfg, settings, data=data, benchmark=benchmark)
            if split is None:
                row.update(res.metrics)
            else:
                from tradelab.risk.metrics import summarize

                rf = res.risk_free_rate
                ins, oos = (
                    res.returns[res.returns.index < split],
                    res.returns[res.returns.index >= split],
                )
                row.update({f"is_{k}": v for k, v in summarize(ins, risk_free=rf).items()})
                row.update({f"oos_{k}": v for k, v in summarize(oos, risk_free=rf).items()})
        except (ValueError, TypeError) as exc:
            row["error"] = str(exc)
        rows.append(row)
        if on_progress:
            on_progress(i, len(combos))
    return pd.DataFrame(rows)
