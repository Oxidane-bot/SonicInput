from unittest.mock import Mock

import sonicinput.core.controllers.transcription_controller as transcription_controller_module
from sonicinput.core.controllers.transcription_controller import TranscriptionController
from sonicinput.core.services.events import Events


class _DummyLogger:
    def __init__(self) -> None:
        self.audio_events: list[tuple[str, dict]] = []

    def log_audio_event(self, event, details=None):
        self.audio_events.append((event, dict(details or {})))

    def log_error(self, *_args, **_kwargs):
        return None


def _build_controller(
    streaming_text: str, streaming_mode: str = "chunked"
) -> tuple[TranscriptionController, Mock, Mock]:
    speech_service = Mock()
    speech_service.stop_streaming.return_value = {"text": streaming_text, "stats": {}}

    config_service = Mock()
    config_service.get_setting.side_effect = (
        lambda key, default=None: "local"
        if key == "transcription.provider"
        else default
    )
    event_service = Mock()
    state_manager = Mock()
    history_service = Mock()
    history_service.save_record.return_value = True
    streaming_manager = Mock()
    streaming_manager.get_current_mode.return_value = streaming_mode

    controller = TranscriptionController(
        speech_service=speech_service,
        config_service=config_service,
        event_service=event_service,
        state_manager=state_manager,
        history_service=history_service,
        audio_service=Mock(),
        streaming_manager=streaming_manager,
    )
    controller._current_record_id = "rec-1"
    controller._current_audio_file_path = "C:/audio.wav"
    controller._audio_duration = 42.0
    controller._recording_stop_time = 1700000000.0
    return controller, history_service, event_service


def test_history_record_persists_diagnostics_with_fallback_flag() -> None:
    controller, history_service, _ = _build_controller(streaming_text="   ")
    controller._sync_transcribe_last_audio = Mock(return_value="fallback result")

    controller.process_streaming_transcription()

    saved_record = history_service.save_record.call_args.args[0]
    assert saved_record.transcription_provider == "local"
    assert saved_record.streaming_mode == "chunked"
    assert saved_record.transcription_path == "local_sync_fallback"
    assert saved_record.transcription_decision_reason == "empty_chunked_result"
    assert saved_record.used_fallback is True
    assert saved_record.fallback_type == "local_sync"
    assert saved_record.fallback_reason == "empty_chunked_result"
    assert saved_record.diagnostics_collected is True
    assert saved_record.transcription_duration >= 0.0


def test_history_record_persists_diagnostics_without_fallback() -> None:
    controller, history_service, _ = _build_controller(streaming_text="direct text")
    controller._sync_transcribe_last_audio = Mock(return_value="unused")

    controller.process_streaming_transcription()

    saved_record = history_service.save_record.call_args.args[0]
    assert saved_record.streaming_mode == "chunked"
    assert saved_record.transcription_path == "streaming_chunked"
    assert saved_record.transcription_decision_reason == "streaming_stop_result"
    assert saved_record.used_fallback is False
    assert saved_record.fallback_type == "none"
    assert saved_record.fallback_reason is None
    assert saved_record.diagnostics_collected is True
    assert saved_record.transcription_duration >= 0.0


def test_history_record_persists_low_quality_chunked_fallback_reason() -> None:
    controller, history_service, _ = _build_controller(streaming_text="嗯")
    controller._sync_transcribe_last_audio = Mock(return_value="fallback result")

    controller.process_streaming_transcription()

    saved_record = history_service.save_record.call_args.args[0]
    assert saved_record.used_fallback is True
    assert saved_record.transcription_path == "local_sync_fallback"
    assert saved_record.transcription_decision_reason == "low_quality_chunked_result"
    assert saved_record.fallback_type == "local_sync"
    assert saved_record.fallback_reason == "low_quality_chunked_result"
    assert saved_record.transcription_text == "fallback result"


def test_realtime_transcription_keeps_final_text_for_history_and_events() -> None:
    controller, history_service, event_service = _build_controller(
        streaming_text="live final text",
        streaming_mode="realtime",
    )

    controller.process_streaming_transcription()

    saved_record = history_service.save_record.call_args.args[0]
    assert saved_record.streaming_mode == "realtime"
    assert saved_record.transcription_path == "streaming_realtime"
    assert saved_record.transcription_decision_reason == "streaming_stop_result"
    assert saved_record.transcription_text == "live final text"
    assert saved_record.final_text == "live final text"

    completed_calls = [
        call
        for call in event_service.emit.call_args_list
        if call.args and call.args[0] == Events.TRANSCRIPTION_COMPLETED
    ]
    assert completed_calls
    assert completed_calls[-1].args[1]["text"] == "live final text"


def test_long_cloud_recording_primary_file_path_does_not_mark_fallback() -> None:
    speech_service = Mock()
    speech_service.stop_streaming.return_value = {"text": "chunked text", "stats": {}}
    speech_service.streaming_coordinator = Mock()

    config_service = Mock()
    config_service.get_setting.side_effect = (
        lambda key, default=None: {
            "transcription.provider": "groq",
            "transcription.long_recording.prefer_file_for_cloud": True,
            "transcription.long_recording.file_threshold_seconds": 90.0,
        }.get(key, default)
    )
    event_service = Mock()
    state_manager = Mock()
    history_service = Mock()
    history_service.save_record.return_value = True
    streaming_manager = Mock()
    streaming_manager.get_current_mode.return_value = "chunked"

    controller = TranscriptionController(
        speech_service=speech_service,
        config_service=config_service,
        event_service=event_service,
        state_manager=state_manager,
        history_service=history_service,
        audio_service=None,
        streaming_manager=streaming_manager,
    )
    controller._current_record_id = "rec-1"
    controller._current_audio_file_path = "C:/audio.wav"
    controller._audio_duration = 120.0
    controller._recording_stop_time = 1700000000.0
    controller._transcribe_from_file_for_cloud = Mock(return_value="file path text")

    controller.process_streaming_transcription()

    saved_record = history_service.save_record.call_args.args[0]
    assert saved_record.transcription_provider == "groq"
    assert saved_record.streaming_mode == "chunked"
    assert saved_record.transcription_path == "cloud_file_long_recording"
    assert (
        saved_record.transcription_decision_reason
        == "long_cloud_recording_prefer_file"
    )
    assert saved_record.used_fallback is False
    assert saved_record.fallback_type == "none"
    assert saved_record.fallback_reason is None
    assert saved_record.transcription_text == "file path text"


def test_transcription_path_decision_log_includes_long_recording_context(
    monkeypatch,
) -> None:
    logger = _DummyLogger()
    monkeypatch.setattr(
        transcription_controller_module,
        "app_logger",
        logger,
        raising=False,
    )

    speech_service = Mock()
    speech_service.stop_streaming.return_value = {"text": "chunked text", "stats": {}}
    speech_service.streaming_coordinator = Mock()

    config_service = Mock()
    config_service.get_setting.side_effect = (
        lambda key, default=None: {
            "transcription.provider": "groq",
            "transcription.long_recording.prefer_file_for_cloud": True,
            "transcription.long_recording.file_threshold_seconds": 90.0,
        }.get(key, default)
    )
    event_service = Mock()
    state_manager = Mock()
    history_service = Mock()
    history_service.save_record.return_value = True
    streaming_manager = Mock()
    streaming_manager.get_current_mode.return_value = "chunked"

    controller = TranscriptionController(
        speech_service=speech_service,
        config_service=config_service,
        event_service=event_service,
        state_manager=state_manager,
        history_service=history_service,
        audio_service=None,
        streaming_manager=streaming_manager,
    )
    controller._current_record_id = "rec-1"
    controller._current_audio_file_path = "C:/audio.wav"
    controller._audio_duration = 120.0
    controller._recording_stop_time = 1700000000.0
    controller._transcribe_from_file_for_cloud = Mock(return_value="file path text")

    controller.process_streaming_transcription()

    decision_events = [
        details
        for event, details in logger.audio_events
        if event == "Transcription path decision"
    ]
    assert decision_events
    assert decision_events[0]["provider"] == "groq"
    assert decision_events[0]["streaming_mode"] == "chunked"
    assert decision_events[0]["selected_path"] == "cloud_file_long_recording"
    assert decision_events[0]["decision_reason"] == "long_cloud_recording_prefer_file"
    assert decision_events[0]["prefer_file_for_long_cloud_recording"] is True
    assert decision_events[0]["long_recording_file_threshold_seconds"] == 90.0
    assert decision_events[0]["audio_file_path_present"] is True


def test_transcription_path_decision_log_includes_streaming_chunked_path(
    monkeypatch,
) -> None:
    logger = _DummyLogger()
    monkeypatch.setattr(
        transcription_controller_module,
        "app_logger",
        logger,
        raising=False,
    )

    controller, history_service, _ = _build_controller(streaming_text="direct text")
    history_service.save_record.return_value = True

    controller.process_streaming_transcription()

    decision_events = [
        details
        for event, details in logger.audio_events
        if event == "Transcription path decision"
    ]
    assert decision_events
    assert decision_events[0]["selected_path"] == "streaming_chunked"
    assert decision_events[0]["decision_reason"] == "streaming_stop_result"
    assert decision_events[0]["provider"] == "local"
