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
