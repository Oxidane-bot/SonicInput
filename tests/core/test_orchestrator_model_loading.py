from __future__ import annotations

from sonicinput.core.services.application_orchestrator import ApplicationOrchestrator
from sonicinput.core.services.config import ConfigKeys
from sonicinput.core.services.events import Events
from sonicinput.speech.null_speech_service import NullSpeechService


class _DummyConfig:
    def __init__(self) -> None:
        self._values = {
            ConfigKeys.TRANSCRIPTION_PROVIDER: "local",
            ConfigKeys.TRANSCRIPTION_LOCAL_AUTO_LOAD: True,
            ConfigKeys.TRANSCRIPTION_LOCAL_MODEL: "paraformer",
        }

    def get_setting(self, key: str, default=None):
        return self._values.get(key, default)


class _RecordingEvents:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []
        self.once_callbacks: dict[str, object] = {}

    def on(self, event_name: str, callback):
        return f"on:{event_name}"

    def once(self, event_name: str, callback):
        self.once_callbacks[event_name] = callback
        return f"once:{event_name}"

    def off(self, event_name: str, listener_id: str):
        self.once_callbacks.pop(event_name, None)
        return True

    def emit(self, event_name: str, data=None):
        self.emitted.append((event_name, data))

    def trigger_once(self, event_name: str, data=None):
        callback = self.once_callbacks.pop(event_name)
        callback(data)


class _DummyState:
    pass


class _AsyncSpeechService(NullSpeechService):
    def __init__(self) -> None:
        super().__init__("test")
        self._is_model_loaded = False
        self.load_requests: list[dict[str, object]] = []
        self.success_callback = None
        self.error_callback = None

    @property
    def is_model_loaded(self) -> bool:
        return self._is_model_loaded

    @property
    def is_running(self) -> bool:
        return True

    def load_model_async(
        self,
        model_name=None,
        timeout: int = 300,
        callback=None,
        error_callback=None,
        download_if_missing: bool = False,
    ) -> str:
        self.load_requests.append(
            {
                "model_name": model_name,
                "timeout": timeout,
                "download_if_missing": download_if_missing,
            }
        )
        self.success_callback = callback
        self.error_callback = error_callback
        return "task-1"


def _build_orchestrator(events: _RecordingEvents, speech_service):
    orchestrator = ApplicationOrchestrator(
        config_service=_DummyConfig(),
        event_service=events,
        state_manager=_DummyState(),
    )
    orchestrator.set_services(
        audio_service=None,
        speech_service=speech_service,
        input_service=None,
        hotkey_service=None,
    )
    return orchestrator


def test_orchestrator_skips_model_loading_when_service_not_running() -> None:
    events = _RecordingEvents()
    orchestrator = _build_orchestrator(events, NullSpeechService("test"))

    orchestrator._init_model_loading()

    emitted_names = [event for event, _ in events.emitted]
    assert Events.MODEL_LOADING_STARTED not in emitted_names


def test_lazy_model_load_retries_after_async_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonicinput.speech.sherpa_models.SherpaModelManager.is_model_cached",
        lambda self, model_name: True,
    )
    events = _RecordingEvents()
    speech_service = _AsyncSpeechService()
    orchestrator = _build_orchestrator(events, speech_service)

    orchestrator._init_model_loading()

    assert Events.RECORDING_STARTED in events.once_callbacks
    events.trigger_once(Events.RECORDING_STARTED)

    assert orchestrator._lazy_model_load_state == "loading"
    assert speech_service.load_requests[-1]["download_if_missing"] is True

    speech_service.error_callback("boom")

    assert orchestrator._lazy_model_load_state == "idle"
    assert Events.RECORDING_STARTED in events.once_callbacks
    assert (Events.MODEL_LOADING_ERROR, "boom") in events.emitted
    assert (
        Events.MODEL_LOADING_FAILED,
        {"model_name": "paraformer", "error": "boom"},
    ) in events.emitted


def test_lazy_model_load_success_false_retries_without_success_events(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "sonicinput.speech.sherpa_models.SherpaModelManager.is_model_cached",
        lambda self, model_name: True,
    )
    events = _RecordingEvents()
    speech_service = _AsyncSpeechService()
    orchestrator = _build_orchestrator(events, speech_service)

    orchestrator._init_model_loading()
    events.trigger_once(Events.RECORDING_STARTED)

    speech_service.success_callback(
        {
            "success": False,
            "model_name": "paraformer",
            "error": "load failed",
        }
    )

    emitted_names = [event for event, _ in events.emitted]
    assert Events.MODEL_LOADING_COMPLETED not in emitted_names
    assert Events.MODEL_LOADED not in emitted_names
    assert orchestrator._lazy_model_load_state == "idle"
    assert Events.RECORDING_STARTED in events.once_callbacks


def test_lazy_model_load_success_emits_loaded_events(monkeypatch) -> None:
    monkeypatch.setattr(
        "sonicinput.speech.sherpa_models.SherpaModelManager.is_model_cached",
        lambda self, model_name: True,
    )
    events = _RecordingEvents()
    speech_service = _AsyncSpeechService()
    orchestrator = _build_orchestrator(events, speech_service)

    orchestrator._init_model_loading()
    events.trigger_once(Events.RECORDING_STARTED)

    model_info = {"model_name": "paraformer", "is_loaded": True}
    speech_service._is_model_loaded = True
    speech_service.success_callback(
        {"success": True, "model_name": "paraformer", "model_info": model_info}
    )

    assert orchestrator._lazy_model_load_state == "loaded"
    assert (Events.MODEL_LOADING_COMPLETED, model_info) in events.emitted
    assert (Events.MODEL_LOADED, model_info) in events.emitted
