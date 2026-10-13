"""Data provider interface and OHLCV normalisation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import date, datetime

import pandas as pd

OHLCV_COLUMNS: list[str] = ["open", "high", "low", "close", "volume"]

DateLike = str | date | datetime | pd.Timestamp


class DataError(RuntimeError):
    """Raised when market data cannot be loaded or is invalid."""


def to_timestamp(value: DateLike | None) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts.normalize()


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Return a clean OHLCV frame: lowercase columns, tz-naive sorted DatetimeIndex named
    ``date``, float dtype, no duplicate or all-NaN rows."""
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS, index=pd.DatetimeIndex([], name="date"))
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    if "adj_close" in out.columns and "close" not in out.columns:
        out = out.rename(columns={"adj_close": "close"})
    for col in ("date", "datetime", "timestamp"):
        if col in out.columns:
            out = out.set_index(col)
            break
    missing = [c for c in OHLCV_COLUMNS if c not in out.columns]
    if missing:
        raise DataError(f"OHLCV data missing columns: {missing}")
    out = out[OHLCV_COLUMNS].astype(float)
    idx = pd.DatetimeIndex(pd.to_datetime(out.index))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    out.index = idx.rename("date")
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out.dropna(how="all", subset=["open", "high", "low", "close"])
    return out


def validate_ohlcv(df: pd.DataFrame) -> list[str]:
    """Return a list of data-quality warnings (empty list means clean)."""
    issues: list[str] = []
    if df.empty:
        return ["no rows"]
    if df[["open", "high", "low", "close"]].isna().any().any():
        issues.append("NaN prices present")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        issues.append("non-positive prices present")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1) - 1e-9).any():
        issues.append("high below open/close/low on some bars")
    if (df["low"] > df[["open", "close", "high"]].min(axis=1) + 1e-9).any():
        issues.append("low above open/close/high on some bars")
    if (df["volume"] < 0).any():
        issues.append("negative volume")
    return issues


class DataProvider(ABC):
    """Historical OHLCV source. Implementations return daily (or intraday) bars."""

    name: str = "base"

    @abstractmethod
    def fetch(
        self, symbol: str, start: pd.Timestamp | None, end: pd.Timestamp | None, interval: str
    ) -> pd.DataFrame:
        """Fetch raw bars for one symbol. ``end`` is inclusive."""

    def get_history(
        self,
        symbol: str,
        start: DateLike | None = None,
        end: DateLike | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        s, e = to_timestamp(start), to_timestamp(end)
        if s is not None and e is not None and s > e:
            raise DataError(f"start {s.date()} is after end {e.date()}")
        df = normalize_ohlcv(self.fetch(symbol.upper(), s, e, interval))
        if s is not None:
            df = df[df.index >= s]
        if e is not None:
            df = df[df.index <= e + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)]
        return df

    def get_many(
        self,
        symbols: Iterable[str],
        start: DateLike | None = None,
        end: DateLike | None = None,
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        result: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            df = self.get_history(sym, start, end, interval)
            if df.empty:
                raise DataError(f"No data returned for {sym} from provider {self.name!r}")
            result[sym.upper()] = df
        return result

    def get_available(
        self,
        symbols: Iterable[str],
        start: DateLike | None = None,
        end: DateLike | None = None,
        interval: str = "1d",
    ) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
        """Like :meth:`get_many` but never fails on a single bad symbol.

        Returns ``(data, errors)`` where ``errors`` maps each symbol that could not be loaded
        (unknown ticker, no bars in range, provider error) to a reason.
        """
        data: dict[str, pd.DataFrame] = {}
        errors: dict[str, str] = {}
        for sym in symbols:
            key = sym.upper()
            try:
                df = self.get_history(sym, start, end, interval)
            except (DataError, ValueError, KeyError) as exc:
                errors[key] = str(exc)
                continue
            if df.empty:
                errors[key] = "no data returned (unknown ticker or no bars in range)"
            else:
                data[key] = df
        return data, errors
