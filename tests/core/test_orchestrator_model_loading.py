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

    def set(self, key: str, value) -> None:
        self._values[key] = value


class _RecordingEvents:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []
        self.once_callbacks: dict[str, object] = {}

    def on(self, event_name: str, callback, priority=None):
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


def test_lazy_load_unsubscribes_when_provider_switches_to_cloud(monkeypatch) -> None:
    """provider 切到 cloud 后，RECORDING_STARTED 不能再触发本地模型加载（崩溃根因修复）。"""
    monkeypatch.setattr(
        "sonicinput.speech.sherpa_models.SherpaModelManager.is_model_cached",
        lambda self, model_name: True,
    )
    events = _RecordingEvents()
    speech_service = _AsyncSpeechService()
    orchestrator = _build_orchestrator(events, speech_service)

    orchestrator._init_model_loading()
    assert Events.RECORDING_STARTED in events.once_callbacks

    # 模拟 hot_reload 切到 cloud
    orchestrator.config.set(ConfigKeys.TRANSCRIPTION_PROVIDER, "groq")
    orchestrator._on_speech_service_reloaded({"new_provider": "GroqSpeechService"})

    # 旧的 RECORDING_STARTED 订阅必须被清掉，且不应重新注册（因为是 cloud）
    assert Events.RECORDING_STARTED not in events.once_callbacks
    assert orchestrator._lazy_model_load_listener_id is None
    assert speech_service.load_requests == []


def test_lazy_load_resubscribes_when_provider_switches_back_to_local(monkeypatch) -> None:
    """启动时是 cloud → 切回 local 时需要补注册 lazy load 订阅。"""
    monkeypatch.setattr(
        "sonicinput.speech.sherpa_models.SherpaModelManager.is_model_cached",
        lambda self, model_name: True,
    )
    events = _RecordingEvents()
    config = _DummyConfig()
    config.set(ConfigKeys.TRANSCRIPTION_PROVIDER, "groq")
    speech_service = _AsyncSpeechService()
    orchestrator = ApplicationOrchestrator(
        config_service=config,
        event_service=events,
        state_manager=_DummyState(),
    )
    orchestrator.set_services(
        audio_service=None,
        speech_service=speech_service,
        input_service=None,
        hotkey_service=None,
    )

    # 启动时 provider=cloud，没注册订阅
    orchestrator._init_model_loading()
    assert Events.RECORDING_STARTED not in events.once_callbacks

    # 切回 local
    config.set(ConfigKeys.TRANSCRIPTION_PROVIDER, "local")
    orchestrator._on_speech_service_reloaded({"new_provider": "LocalSpeechService"})

    assert Events.RECORDING_STARTED in events.once_callbacks
