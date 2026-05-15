"""Strategy registry for declarative sub-agent building."""

from artipivot.agents.strategies.base import Strategy

_strategies: dict[str, type[Strategy]] = {}


def register_strategy(name: str, strategy_cls: type[Strategy]) -> None:
    _strategies[name] = strategy_cls


def get_strategy(name: str) -> Strategy:
    cls = _strategies.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}, available: {list(_strategies)}")
    return cls()


def available_strategies() -> list[str]:
    return list(_strategies)
