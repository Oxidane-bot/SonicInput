from unittest.mock import Mock

from sonicinput.core.controllers.transcription_controller import TranscriptionController
from sonicinput.core.services.events import Events


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
    assert saved_record.used_fallback is False
    assert saved_record.fallback_type == "none"
    assert saved_record.fallback_reason is None
    assert saved_record.diagnostics_collected is True
    assert saved_record.transcription_duration >= 0.0


def test_realtime_transcription_keeps_final_text_for_history_and_events() -> None:
    controller, history_service, event_service = _build_controller(
        streaming_text="live final text",
        streaming_mode="realtime",
    )

    controller.process_streaming_transcription()

    saved_record = history_service.save_record.call_args.args[0]
    assert saved_record.streaming_mode == "realtime"
    assert saved_record.transcription_text == "live final text"
    assert saved_record.final_text == "live final text"

    completed_calls = [
        call
        for call in event_service.emit.call_args_list
        if call.args and call.args[0] == Events.TRANSCRIPTION_COMPLETED
    ]
    assert completed_calls
    assert completed_calls[-1].args[1]["text"] == "live final text"
