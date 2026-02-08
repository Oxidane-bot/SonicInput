from __future__ import annotations

from sonicinput.core.di_container import DIContainer


class _StoppableService:
    def __init__(self) -> None:
        self.stop_called = False

    def stop(self) -> None:
        self.stop_called = True


class _CleanableService:
    def __init__(self) -> None:
        self.cleanup_called = False

    def cleanup(self) -> None:
        self.cleanup_called = True


class _FailingStopService:
    def stop(self) -> None:
        raise RuntimeError("expected stop failure")


def test_clear_calls_stop_on_resolved_singleton() -> None:
    container = DIContainer()
    container.register_singleton(_StoppableService, _StoppableService)
    service = container.resolve(_StoppableService)

    container.clear()

    assert service.stop_called is True
    assert container.is_registered(_StoppableService) is False


def test_cleanup_calls_cleanup_when_stop_missing() -> None:
    container = DIContainer()
    container.register_singleton(_CleanableService, _CleanableService)
    service = container.resolve(_CleanableService)

    container.cleanup()

    assert service.cleanup_called is True
    assert container.is_registered(_CleanableService) is False


def test_clear_continues_after_singleton_stop_exception() -> None:
    container = DIContainer()
    container.register_singleton(_FailingStopService, _FailingStopService)
    _ = container.resolve(_FailingStopService)

    container.clear()

    assert container.is_registered(_FailingStopService) is False
