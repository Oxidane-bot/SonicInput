from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtWidgets import QDialog

from sonicinput.core.interfaces import HistoryRecord
from sonicinput.ui.settings_tabs.history_detail_dialog import HistoryDetailDialog


def _make_record() -> HistoryRecord:
    return HistoryRecord(
        id="record-1",
        timestamp=datetime(2026, 3, 24, 10, 30, 0),
        audio_file_path="C:/tmp/audio.wav",
        duration=1.2,
        transcription_text="hello world",
        transcription_provider="local",
        transcription_status="success",
        streaming_mode="chunked",
        transcription_duration=0.4,
        used_fallback=False,
        fallback_type="none",
        fallback_reason=None,
        diagnostics_collected=True,
        reprocess_parent_id=None,
        transcription_error=None,
        ai_optimized_text=None,
        ai_provider=None,
        ai_status="skipped",
        ai_error=None,
        final_text="hello world",
    )


@pytest.mark.gui
def test_history_detail_dialog_uses_settings_service_runtime_dependencies(qtbot):
    event_service = MagicMock()
    event_service.on = Mock()

    transcription_service = Mock(name="transcription_service")
    ai_processing_controller = Mock(name="ai_processing_controller")

    settings_service = MagicMock()
    settings_service.get_event_service.return_value = event_service
    settings_service.get_transcription_service.return_value = transcription_service
    settings_service.get_ai_processing_controller.return_value = (
        ai_processing_controller
    )

    history_service = MagicMock()

    dialog = HistoryDetailDialog(
        record=_make_record(),
        parent_window=None,
        settings_service=settings_service,
        history_service=history_service,
    )
    qtbot.addWidget(dialog)

    assert dialog._get_runtime_transcription_service() is transcription_service
    assert dialog._get_runtime_ai_processing_controller() is ai_processing_controller
    assert dialog.retry_button is not None
    assert dialog.delete_button is not None


@pytest.mark.gui
def test_history_detail_dialog_unsubscribes_language_listener_on_done(qtbot):
    event_service = MagicMock()
    event_service.on = Mock(return_value="listener-1")
    event_service.off = Mock()

    settings_service = MagicMock()
    settings_service.get_event_service.return_value = event_service
    settings_service.get_transcription_service.return_value = None
    settings_service.get_ai_processing_controller.return_value = None

    dialog = HistoryDetailDialog(
        record=_make_record(),
        parent_window=None,
        settings_service=settings_service,
        history_service=MagicMock(),
    )
    qtbot.addWidget(dialog)

    dialog.done(QDialog.DialogCode.Rejected)

    event_service.off.assert_called_once_with("ui_language_changed", "listener-1")
