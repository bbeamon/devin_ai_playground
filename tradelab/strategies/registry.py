"""Strategy registry with support for third-party strategies by dotted path."""

from __future__ import annotations

import importlib
from typing import Any, TypeVar

from tradelab.strategies.base import Strategy

_REGISTRY: dict[str, type[Strategy]] = {}

S = TypeVar("S", bound=type[Strategy])


def register_strategy(cls: S) -> S:
    key = cls.name
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise ValueError(f"Strategy name {key!r} already registered by {_REGISTRY[key]}")
    _REGISTRY[key] = cls
    return cls


def get_strategy_class(name: str) -> type[Strategy]:
    """Resolve a registered name or a ``"package.module:ClassName"`` path."""
    if name in _REGISTRY:
        return _REGISTRY[name]
    if ":" in name:
        module_name, cls_name = name.split(":", 1)
        cls = getattr(importlib.import_module(module_name), cls_name)
        if not (isinstance(cls, type) and issubclass(cls, Strategy)):
            raise TypeError(f"{name} is not a Strategy subclass")
        return cls
    raise KeyError(f"Unknown strategy {name!r}. Available: {sorted(_REGISTRY)}")


def create_strategy(name: str, **params: Any) -> Strategy:
    return get_strategy_class(name)(**params)


def list_strategies() -> dict[str, type[Strategy]]:
    return dict(sorted(_REGISTRY.items()))
