from datetime import datetime
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication

from sonicinput.core.interfaces import HistoryRecord
from sonicinput.ui.history_formatters import (
    format_transcription_path_for_display,
)
from sonicinput.ui.qml_bridge import FluentSettingsViewModel, qml_path


def _ensure_app() -> QCoreApplication:
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def _make_record(
    *,
    transcription_path: str = "streaming_chunked",
    diagnostics_collected: bool = True,
) -> HistoryRecord:
    return HistoryRecord(
        id="h-1",
        timestamp=datetime(2026, 5, 12, 10, 30),
        audio_file_path="C:/h-1.wav",
        duration=2.5,
        transcription_text="detail panel",
        transcription_provider="local",
        transcription_status="success",
        streaming_mode="chunked",
        transcription_path=transcription_path,
        transcription_decision_reason="long_cloud_recording_prefer_file",
        transcription_duration=0.2,
        used_fallback=False,
        fallback_type="none",
        fallback_reason=None,
        diagnostics_collected=diagnostics_collected,
        reprocess_parent_id=None,
        transcription_error=None,
        ai_optimized_text="detail panel polished",
        ai_provider="groq",
        ai_status="success",
        ai_error=None,
        final_text="detail panel final",
    )


def test_format_transcription_path_marks_legacy_default() -> None:
    _ensure_app()
    record = _make_record(transcription_path="standard", diagnostics_collected=False)

    assert format_transcription_path_for_display(record) == "Legacy default (standard)"


def test_history_detail_exposes_transcription_path_and_tooltip() -> None:
    _ensure_app()
    record = _make_record(transcription_path="cloud_file_long_recording")
    history_service = Mock()
    history_service.get_records_keyset.return_value = [record]
    history_service.get_aggregate_stats.return_value = (1, 2.5, 1)

    settings_service = Mock()
    settings_service.get_setting = Mock(side_effect=lambda _key, default=None: default)
    settings_service.get_history_service = Mock(return_value=history_service)

    view_model = FluentSettingsViewModel(settings_service)
    view_model.refreshHistory("")
    view_model.openHistoryDetail(0)

    assert "Path: cloud_file_long_recording" in view_model.historyRecords[0]["tooltip"]
    assert (
        view_model.selectedHistoryDetail["transcriptionPath"]
        == "cloud_file_long_recording"
    )
    assert (
        view_model.selectedHistoryDetail["transcriptionDecisionReason"]
        == "long_cloud_recording_prefer_file"
    )
    assert view_model.selectedHistoryDetail["fallbackType"] == "none"


def test_history_detail_qml_declares_transcription_path_field() -> None:
    qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

    assert 'objectName: "historyDetailRecordIdValue"' in qml_source
    assert 'objectName: "historyDetailTranscriptionPathValue"' in qml_source
    assert 'objectName: "historyDetailDecisionReasonValue"' in qml_source
    assert 'objectName: "historyDetailFallbackTypeValue"' in qml_source
    assert 'historyDetailValue("id", "")' in qml_source
    assert 'historyDetailValue("transcriptionPath", "")' in qml_source
    assert 'historyDetailValue("transcriptionDecisionReason", "")' in qml_source
    assert 'historyDetailValue("fallbackType", "")' in qml_source
