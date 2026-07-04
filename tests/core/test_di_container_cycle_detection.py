"""Circular dependency detection in DIContainer.resolve()."""

from __future__ import annotations

import pytest

from sonicinput.core.di_container import DIContainer


class _ServiceA:
    def __init__(self, b: object) -> None:
        self.b = b


class _ServiceB:
    def __init__(self, a: object) -> None:
        self.a = a


class _ServiceC:
    def __init__(self, a: object) -> None:
        self.a = a


class _Leaf:
    pass


class _Consumer:
    def __init__(self, leaf: _Leaf) -> None:
        self.leaf = leaf


def test_direct_cycle_raises_with_chain() -> None:
    """A -> B -> A dies with a diagnosable RuntimeError, not RecursionError."""
    container = DIContainer()
    container.register_singleton(
        _ServiceA, factory=lambda: _ServiceA(container.resolve(_ServiceB))
    )
    container.register_singleton(
        _ServiceB, factory=lambda: _ServiceB(container.resolve(_ServiceA))
    )

    with pytest.raises(RuntimeError, match="Circular dependency detected") as exc:
        container.resolve(_ServiceA)

    # The full chain is reported for diagnosis
    assert "_ServiceA -> _ServiceB -> _ServiceA" in str(exc.value)


def test_self_cycle_raises() -> None:
    container = DIContainer()
    container.register_singleton(
        _ServiceA, factory=lambda: _ServiceA(container.resolve(_ServiceA))
    )

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        container.resolve(_ServiceA)


def test_indirect_cycle_raises() -> None:
    """A -> B -> C -> A is detected across three factories."""
    container = DIContainer()
    container.register_singleton(
        _ServiceA, factory=lambda: _ServiceA(container.resolve(_ServiceB))
    )
    container.register_singleton(
        _ServiceB, factory=lambda: _ServiceB(container.resolve(_ServiceC))
    )
    container.register_singleton(
        _ServiceC, factory=lambda: _ServiceC(container.resolve(_ServiceA))
    )

    with pytest.raises(RuntimeError, match="Circular dependency detected") as exc:
        container.resolve(_ServiceA)

    assert "_ServiceA -> _ServiceB -> _ServiceC -> _ServiceA" in str(exc.value)


def test_diamond_dependency_is_not_a_cycle() -> None:
    """A -> Leaf and B -> Leaf sharing one dependency is legal."""
    container = DIContainer()
    container.register_singleton(_Leaf, _Leaf)
    container.register_singleton(
        _ServiceA, factory=lambda: _ServiceA(container.resolve(_Leaf))
    )
    container.register_singleton(
        _ServiceB, factory=lambda: _ServiceB(container.resolve(_ServiceA))
    )

    b = container.resolve(_ServiceB)

    assert isinstance(b.a, _ServiceA)


def test_repeated_resolve_of_cached_singleton_from_factory() -> None:
    """A factory resolving an already-created singleton is not a cycle."""
    container = DIContainer()
    container.register_singleton(_Leaf, _Leaf)
    leaf = container.resolve(_Leaf)  # created before _Consumer's factory runs
    container.register_singleton(
        _Consumer, factory=lambda: _Consumer(container.resolve(_Leaf))
    )

    consumer = container.resolve(_Consumer)

    assert consumer.leaf is leaf


def test_failed_resolution_leaves_container_usable() -> None:
    """After a cycle error, the resolution chain unwinds cleanly."""
    container = DIContainer()
    container.register_singleton(
        _ServiceA, factory=lambda: _ServiceA(container.resolve(_ServiceB))
    )
    container.register_singleton(
        _ServiceB, factory=lambda: _ServiceB(container.resolve(_ServiceA))
    )
    container.register_singleton(_Leaf, _Leaf)

    with pytest.raises(RuntimeError):
        container.resolve(_ServiceA)

    # Other services still resolve; the failed ones were not cached
    assert isinstance(container.resolve(_Leaf), _Leaf)
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        container.resolve(_ServiceA)


def test_transient_cycle_also_detected() -> None:
    container = DIContainer()
    container.register_transient(
        _ServiceA, factory=lambda: _ServiceA(container.resolve(_ServiceB))
    )
    container.register_transient(
        _ServiceB, factory=lambda: _ServiceB(container.resolve(_ServiceA))
    )

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        container.resolve(_ServiceB)
