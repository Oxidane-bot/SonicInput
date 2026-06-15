from unittest.mock import Mock

from sonicinput.core.controllers.transcription_controller import TranscriptionController
from sonicinput.core.services.events import Events


def test_chunked_cloud_empty_text_falls_back_to_file_transcription():
    speech_service = Mock()
    speech_service.stop_streaming.return_value = {"text": "   ", "stats": {}}

    config_service = Mock()
    event_service = Mock()
    state_manager = Mock()
    history_service = Mock()
    streaming_manager = Mock()
    streaming_manager.get_current_mode.return_value = "chunked"

    controller = TranscriptionController(
        speech_service=speech_service,
        config_service=config_service,
        event_service=event_service,
        state_manager=state_manager,
        history_service=history_service,
        audio_service=None,  # Cloud path (no local audio_service fallback)
        streaming_manager=streaming_manager,
    )

    controller._transcribe_from_file_for_cloud = Mock(return_value="fallback text")
    controller.process_streaming_transcription()

    controller._transcribe_from_file_for_cloud.assert_called_once()
    assert any(
        call.args
        and call.args[0] == Events.TRANSCRIPTION_COMPLETED
        and call.args[1].get("text") == "fallback text"
        for call in event_service.emit.call_args_list
    )


def test_chunked_cloud_low_quality_text_falls_back_to_file_transcription():
    speech_service = Mock()
    speech_service.stop_streaming.return_value = {"text": "嗯", "stats": {}}

    config_service = Mock()
    event_service = Mock()
    state_manager = Mock()
    history_service = Mock()
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
    controller._audio_duration = 12.0
    controller._transcribe_from_file_for_cloud = Mock(return_value="fallback text")

    controller.process_streaming_transcription()

    controller._transcribe_from_file_for_cloud.assert_called_once()
    assert any(
        call.args
        and call.args[0] == Events.TRANSCRIPTION_COMPLETED
        and call.args[1].get("text") == "fallback text"
        for call in event_service.emit.call_args_list
    )


def test_chunked_short_low_information_text_does_not_trigger_low_quality_fallback():
    speech_service = Mock()
    speech_service.stop_streaming.return_value = {"text": "嗯", "stats": {}}

    config_service = Mock()
    event_service = Mock()
    state_manager = Mock()
    history_service = Mock()
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
    controller._audio_duration = 2.0
    controller._transcribe_from_file_for_cloud = Mock(return_value="fallback text")

    controller.process_streaming_transcription()

    controller._transcribe_from_file_for_cloud.assert_not_called()


def test_long_chunked_cloud_recording_prefers_file_transcription_path():
    speech_service = Mock()
    speech_service.stop_streaming.return_value = {"text": "chunked text", "stats": {}}
    speech_service.streaming_coordinator = Mock()

    config_service = Mock()
    config_service.get_setting.side_effect = lambda key, default=None: {
        "transcription.provider": "groq",
        "transcription.long_recording.prefer_file_for_cloud": True,
        "transcription.long_recording.file_threshold_seconds": 90.0,
    }.get(key, default)
    event_service = Mock()
    state_manager = Mock()
    history_service = Mock()
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
    controller._audio_duration = 120.0
    controller._current_audio_file_path = "C:/audio.wav"
    controller._transcribe_from_file_for_cloud = Mock(return_value="file path text")

    controller.process_streaming_transcription()

    speech_service.stop_streaming.assert_not_called()
    speech_service.streaming_coordinator.stop_streaming.assert_called_once_with()
    controller._transcribe_from_file_for_cloud.assert_called_once()
    assert any(
        call.args
        and call.args[0] == Events.TRANSCRIPTION_COMPLETED
        and call.args[1].get("text") == "file path text"
        for call in event_service.emit.call_args_list
    )
