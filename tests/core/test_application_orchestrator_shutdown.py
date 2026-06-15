from __future__ import annotations


from sonicinput.core.services.application_orchestrator import ApplicationOrchestrator


class _DummyConfig:
    def get_setting(self, key: str, default=None):
        return default


class _DummyEvents:
    def on(self, event_name: str, callback, priority=None):
        return None

    def emit(self, event_name: str, data=None):
        return None


class _DummyState:
    pass


class _LegacyHotkeyService:
    """Simulates a legacy IHotkeyService impl that exposes stop() but not stop_listening()."""

    def __init__(self) -> None:
        self.stop_called = False
        self.unregister_all_called = False

    def stop(self) -> None:
        self.stop_called = True

    def unregister_all_hotkeys(self) -> None:
        self.unregister_all_called = True

    @property
    def is_listening(self) -> bool:  # pragma: no cover
        return False


def test_orchestrate_shutdown_falls_back_to_stop_when_stop_listening_missing() -> None:
    orchestrator = ApplicationOrchestrator(
        config_service=_DummyConfig(),
        event_service=_DummyEvents(),
        state_manager=_DummyState(),
    )
    hotkey_service = _LegacyHotkeyService()

    orchestrator.set_services(
        audio_service=None,
        speech_service=None,
        input_service=None,
        hotkey_service=hotkey_service,
    )

    orchestrator.orchestrate_shutdown()

    assert hotkey_service.stop_called is True
    assert hotkey_service.unregister_all_called is True
