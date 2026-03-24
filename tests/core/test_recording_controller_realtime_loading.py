from sonicinput.core.controllers.recording_controller import RecordingController
from sonicinput.core.interfaces.state import AppState, RecordingState
from sonicinput.core.services.config import ConfigKeys
from sonicinput.core.services.events import Events


class _DummyAudioService:
    def __init__(self) -> None:
        self.started_with = []

    def start_recording(self, device_id):
        self.started_with.append(device_id)


class _DummyConfigService:
    def __init__(self, values) -> None:
        self.values = values

    def get_setting(self, key, default=None):
        return self.values.get(key, default)


class _DummyEventService:
    def __init__(self) -> None:
        self.emitted = []

    def emit(self, event_name, data=None):
        self.emitted.append((event_name, data))


class _DummyStateManager:
    def __init__(self) -> None:
        self.app_state = AppState.IDLE
        self.recording_state = RecordingState.IDLE

    def get_app_state(self):
        return self.app_state

    def set_app_state(self, state):
        self.app_state = state

    def get_recording_state(self):
        return self.recording_state

    def set_recording_state(self, state):
        self.recording_state = state

    def is_processing(self):
        return self.app_state == AppState.PROCESSING


class _DummySpeechService:
    def __init__(self, is_model_loaded=False, load_result=True) -> None:
        self._is_model_loaded = is_model_loaded
        self.load_result = load_result
        self.load_calls = []

    @property
    def is_model_loaded(self):
        return self._is_model_loaded

    def load_model(self, model_name=None, download_if_missing=False):
        self.load_calls.append(
            {
                "model_name": model_name,
                "download_if_missing": download_if_missing,
            }
        )
        if self.load_result:
            self._is_model_loaded = True
        return self.load_result


class _DummyHistoryService:
    pass


class _DummyStreamingManager:
    def __init__(self, mode="realtime", start_result=True) -> None:
        self.mode = mode
        self.start_result = start_result
        self.start_calls = 0

    def get_current_mode(self):
        return self.mode

    def start_streaming_session(self):
        self.start_calls += 1
        return self.start_result


class _DummyCallbackRouter:
    def __init__(self) -> None:
        self.realtime_calls = 0

    def register_realtime_callback(self):
        self.realtime_calls += 1

    def register_chunked_callback(self):
        return None

    def register_basic_callback(self):
        return None


def _build_controller(
    *,
    is_model_loaded=False,
    load_result=True,
    streaming_start_result=True,
):
    audio_service = _DummyAudioService()
    config_service = _DummyConfigService(
        {
            ConfigKeys.AUDIO_DEVICE_ID: 7,
            ConfigKeys.TRANSCRIPTION_PROVIDER: "local",
            ConfigKeys.TRANSCRIPTION_LOCAL_STREAMING_MODE: "realtime",
            ConfigKeys.TRANSCRIPTION_LOCAL_MODEL: "paraformer",
        }
    )
    events = _DummyEventService()
    state_manager = _DummyStateManager()
    speech_service = _DummySpeechService(
        is_model_loaded=is_model_loaded, load_result=load_result
    )
    controller = RecordingController(
        audio_service=audio_service,
        config_service=config_service,
        event_service=events,
        state_manager=state_manager,
        speech_service=speech_service,
        history_service=_DummyHistoryService(),
    )
    controller._streaming_manager = _DummyStreamingManager(
        start_result=streaming_start_result
    )
    controller._callback_router = _DummyCallbackRouter()
    return controller, audio_service, events, speech_service


def test_realtime_recording_loads_model_before_starting_session():
    controller, audio_service, events, speech_service = _build_controller()

    controller.start_recording()

    assert speech_service.load_calls == [
        {"model_name": "paraformer", "download_if_missing": True}
    ]
    assert controller._streaming_manager.start_calls == 1
    assert controller._callback_router.realtime_calls == 1
    assert audio_service.started_with == [7]
    assert (Events.RECORDING_STARTED, None) in events.emitted


def test_realtime_recording_aborts_when_model_load_fails():
    controller, audio_service, events, speech_service = _build_controller(
        load_result=False
    )

    controller.start_recording()

    assert speech_service.load_calls == [
        {"model_name": "paraformer", "download_if_missing": True}
    ]
    assert controller._streaming_manager.start_calls == 0
    assert controller._callback_router.realtime_calls == 0
    assert audio_service.started_with == []
    assert (
        Events.RECORDING_ERROR,
        "Failed to load local model for realtime recording",
    ) in events.emitted


def test_realtime_recording_aborts_when_session_start_fails():
    controller, audio_service, events, speech_service = _build_controller(
        is_model_loaded=True,
        streaming_start_result=False,
    )

    controller.start_recording()

    assert speech_service.load_calls == []
    assert controller._streaming_manager.start_calls == 1
    assert controller._callback_router.realtime_calls == 0
    assert audio_service.started_with == []
    assert (
        Events.RECORDING_ERROR,
        "Unable to start streaming transcription session",
    ) in events.emitted
