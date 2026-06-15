"""Tests for the Fluent QML UI layer."""

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from unittest.mock import Mock
from datetime import datetime

from sonicinput.core.interfaces import HistoryRecord


def _make_history_record(record_id: str, text: str) -> HistoryRecord:
    return HistoryRecord(
        id=record_id,
        timestamp=datetime(2026, 5, 12, 10, 30),
        audio_file_path=f"C:/{record_id}.wav",
        duration=2.5,
        transcription_text=text,
        transcription_provider="local",
        transcription_status="success",
        streaming_mode="chunked",
        transcription_path="streaming_chunked",
        transcription_decision_reason="streaming_stop_result",
        transcription_duration=0.2,
        used_fallback=False,
        fallback_type="none",
        fallback_reason=None,
        diagnostics_collected=True,
        reprocess_parent_id=None,
        transcription_error=None,
        ai_optimized_text=f"{text} polished",
        ai_provider="groq",
        ai_status="success",
        ai_error=None,
        final_text=f"{text} final",
    )


def _load_settings_qml(qapp, view_model):
    from sonicinput.ui.qml_bridge import qml_path

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("settingsViewModel", view_model)
    engine.rootContext().setContextProperty("settingsHost", None)
    engine.load(QUrl.fromLocalFile(str(qml_path("FluentSettingsWindow.qml"))))
    root = engine.rootObjects()[0]
    root.setProperty("visible", True)
    root.setProperty("selectedSection", 5)
    qapp.processEvents()
    qapp.processEvents()
    return engine, root


@pytest.mark.gui
class TestFluentSettingsViewModel:
    def test_reads_and_applies_application_settings(self, mock_config_service):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        view_model = FluentSettingsViewModel(mock_config_service)

        assert view_model.startMinimized is False
        assert view_model.trayNotifications is True

        view_model.setStartMinimized(True)
        view_model.setTrayNotifications(False)
        view_model.apply()

        assert mock_config_service.get_setting("ui.start_minimized") is True
        assert mock_config_service.get_setting("ui.tray_notifications") is False

    def test_section_model_exposes_quality_review_section(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )

        view_model = FluentSettingsViewModel(settings_service)

        assert view_model.sectionCount == 7
        assert view_model.sectionLabel(0) == "Application"
        assert view_model.sectionLabel(3) == "AI Processing"
        assert view_model.sectionLabel(6) == "Local Quality Review"

    def test_review_bridge_exposes_suggestions_and_decisions(
        self,
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "s-1",
                    "suggestion_type": "lexicon_candidate",
                    "confidence": 0.82,
                    "risk_level": "low",
                    "source_record_ids": ["h-1"],
                    "title": "Prefer SonicInput",
                    "detail": "ASR often writes Sonic Input.",
                    "evidence_count": 3,
                    "old_form": "Sonic Input",
                    "new_form": "SonicInput",
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        history_service = Mock()
        history_service.get_record_by_id = Mock(
            return_value=_make_history_record("h-1", "raw source example")
        )
        settings_service.get_history_service = Mock(return_value=history_service)
        settings_service.list_lexicon_entries = Mock(
            return_value=[
                {
                    "id": "lex-1",
                    "term": "SonicInput",
                    "old_form": "Sonic Input",
                    "evidence_count": 3,
                    "confidence": 0.82,
                    "updated_at": "2026-06-09T03:01:00",
                }
            ]
        )
        settings_service.list_review_jobs = Mock(
            return_value=[
                {
                    "id": "job-1",
                    "created_at": "2026-06-09T03:02:00",
                    "status": "completed",
                    "record_limit": 20,
                    "reviewed_count": 8,
                    "suggestion_count": 1,
                }
            ]
        )
        settings_service.decide_review_suggestion = Mock(return_value=True)
        settings_service.clear_lexicon_entries = Mock(return_value=True)
        settings_service.clear_review_learning_data = Mock(return_value=True)
        settings_service.run_review_now = Mock(
            return_value={
                "ran": True,
                "reason": "completed",
                "jobId": "job-1",
                "reviewedRecordCount": 8,
                "suggestionCount": 1,
            }
        )
        settings_service.run_idle_review_once = Mock(
            return_value={
                "ran": True,
                "reason": "completed",
                "jobId": "job-1",
                "reviewedRecordCount": 8,
                "suggestionCount": 1,
            }
        )

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestionCount == 1
        assert view_model.reviewSuggestions[0]["id"] == "s-1"
        assert view_model.reviewSuggestions[0]["confidenceText"] == "82%"
        assert view_model.reviewSuggestions[0]["typeLabel"] == "Lexicon Candidate"
        assert view_model.reviewSuggestions[0]["category"] == "lexicon_learning"
        assert view_model.reviewSuggestions[0]["categoryLabel"] == "Lexicon Learning"
        assert view_model.reviewSuggestions[0]["categoryPriorityLevel"] == "low"
        assert (
            view_model.reviewSuggestions[0]["categoryPriorityLabel"] == "Review Later"
        )
        assert view_model.reviewCategorySummaries[0]["category"] == "lexicon_learning"
        assert view_model.reviewCategorySummaries[0]["totalCount"] == 1
        assert view_model.reviewCategorySummaries[0]["priorityLevel"] == "low"
        assert view_model.reviewSuggestionGroups[0]["category"] == "lexicon_learning"
        assert view_model.reviewSuggestionGroups[0]["shownCount"] == 1
        assert view_model.reviewSuggestionGroups[0]["defaultExpanded"] is False
        assert view_model.reviewSuggestionGroups[0]["isExpanded"] is False
        assert view_model.reviewSuggestionGroups[0]["priorityLabel"] == "Review Later"
        assert view_model.reviewSuggestionGroups[0]["items"][0]["id"] == "s-1"
        assert view_model.reviewSuggestions[0]["canReprocessSample"] is False
        assert view_model.reviewSuggestions[0]["canRevertToRaw"] is False
        assert view_model.reviewSuggestions[0]["riskLabel"] == "Low Risk"
        assert "local lexicon memory" in view_model.reviewSuggestions[0]["actionHint"]
        assert view_model.reviewSuggestions[0]["sourceRecordLabel"] == "Local Example"
        assert (
            view_model.reviewSuggestions[0]["sourceRecordText"]
            == "raw source example final"
        )
        assert (
            view_model.reviewSuggestions[0]["sourceRecordPreviewText"]
            == "raw source example final"
        )
        assert view_model.reviewSuggestions[0]["canOpenSourceRecord"] is True
        assert (
            view_model.reviewSuggestions[0]["sourceRecordActionLabel"]
            == "Open Source Record"
        )
        assert (
            "suppresses future similar suggestions" in view_model.reviewIgnoreScopeHint
        )
        assert view_model.reviewSelectedCategory == "all"
        assert view_model.reviewSelectedCategoryLabel == "All Categories"
        assert view_model.reviewEmptyStateText == "No pending review suggestions"
        assert view_model.reviewSuggestionOverflowText == ""
        assert view_model.lexiconEntryCount == 1
        assert view_model.lexiconEntries[0]["term"] == "SonicInput"
        assert view_model.reviewJobCount == 1
        assert view_model.reviewJobs[0]["summaryText"] == "8 records, 1 suggestions"

        assert view_model.acceptReviewSuggestion("s-1") is True
        settings_service.decide_review_suggestion.assert_called_with("s-1", "accepted")

        assert view_model.clearLexiconEntries() is True
        settings_service.clear_lexicon_entries.assert_called_once()

        assert view_model.clearReviewLearningData() is True
        settings_service.clear_review_learning_data.assert_called_once()
        assert (
            view_model.reviewLearningDataMessage
            == "Local learning data has been cleared."
        )

        settings_service.export_lexicon_entries = Mock(
            return_value={
                "success": True,
                "path": "quality_audit/lexicon.json",
                "count": 1,
            }
        )
        export_result = view_model.exportLexiconEntries()
        assert export_result["success"] is True
        assert view_model.lexiconExportMessage == (
            "Exported 1 lexicon entries to quality_audit/lexicon.json"
        )

        settings_service.export_review_debug_report = Mock(
            return_value={
                "success": True,
                "path": "quality_audit/review_debug.json",
                "count": 1,
            }
        )
        debug_export_result = view_model.exportReviewDebugReport()
        assert debug_export_result["success"] is True
        assert view_model.reviewDebugExportMessage == (
            "Exported 1 prompt/validator debug suggestions to quality_audit/review_debug.json"
        )

        assert view_model.runReviewNow()["ran"] is True
        assert view_model.reviewRunMessage == (
            "Local rule review completed: 8 records, 1 suggestions"
        )
        settings_service.run_review_now.assert_called_once()
        assert view_model.archiveReviewSuggestion("s-1") is True
        settings_service.decide_review_suggestion.assert_called_with("s-1", "archived")

    def test_review_bridge_falls_back_to_source_record_ids_without_local_examples(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "s-1",
                    "suggestion_type": "bad_ai_output_alert",
                    "confidence": 0.91,
                    "risk_level": "high",
                    "source_record_ids": ["h-1", "h-2"],
                    "title": "Alert",
                    "detail": "validator hit",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        settings_service.get_history_service = Mock(return_value=None)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestions[0]["sourceRecordLabel"] == "Source Records"
        assert view_model.reviewSuggestions[0]["sourceRecordText"] == "h-1, h-2"
        assert view_model.reviewSuggestions[0]["sourceRecordPreviewText"] == ""
        assert view_model.reviewSuggestions[0]["canOpenSourceRecord"] is False

    def test_review_bridge_formats_prompt_failure_pattern_for_debug_export(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "prompt-1",
                    "suggestion_type": "prompt_failure_pattern",
                    "confidence": 0.74,
                    "risk_level": "medium",
                    "source_record_ids": ["h-1", "h-2"],
                    "title": "Prompt issue",
                    "detail": "Repeated assistant-style replies.",
                    "evidence_count": 2,
                    "old_form": "assistant_response_tone",
                    "created_at": "2026-06-09T04:00:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        history_service = Mock()
        history_service.get_record_by_id = Mock(
            side_effect=[
                _make_history_record("h-1", "first raw example"),
                _make_history_record("h-2", "second raw example"),
            ]
        )
        settings_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestions[0]["typeLabel"] == "Prompt Failure Pattern"
        assert view_model.reviewSuggestions[0]["category"] == "prompt_quality"
        assert view_model.reviewSuggestions[0]["categoryLabel"] == "Prompt Issue"
        assert view_model.reviewSuggestions[0]["categoryPriorityLevel"] == "medium"
        assert (
            "does not change the live prompt automatically"
            in view_model.reviewSuggestions[0]["actionHint"]
        )
        assert view_model.reviewSuggestions[0]["sourceRecordLabel"] == "Local Examples"
        assert view_model.reviewCategorySummaries[0]["category"] == "prompt_quality"
        assert view_model.reviewSuggestionGroups[0]["category"] == "prompt_quality"

    def test_review_bridge_formats_chunk_boundary_repeat_as_diagnostic(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "diag-1",
                    "suggestion_type": "chunk_boundary_repeat_alert",
                    "confidence": 0.81,
                    "risk_level": "medium",
                    "source_record_ids": ["h-1"],
                    "title": "Chunk repeat",
                    "detail": "Repeated chunk boundary fragment.",
                    "evidence_count": 1,
                    "old_form": "review agent 的边界",
                    "created_at": "2026-06-09T04:10:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        history_service = Mock()
        history_service.get_record_by_id = Mock(
            return_value=_make_history_record("h-1", "chunk repeat sample")
        )
        settings_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestions[0]["typeLabel"] == "Chunk Boundary Repeat"
        assert view_model.reviewSuggestions[0]["category"] == "diagnostics"
        assert view_model.reviewSuggestions[0]["categoryLabel"] == "Diagnostic Sample"
        assert (
            "chunk overlap or boundary dedup issues"
            in view_model.reviewSuggestions[0]["actionHint"]
        )

    def test_review_bridge_shows_multiple_local_examples_for_multi_source_suggestions(
        self,
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "s-1",
                    "suggestion_type": "bad_ai_output_alert",
                    "confidence": 0.91,
                    "risk_level": "high",
                    "source_record_ids": ["h-1", "h-2", "h-3"],
                    "title": "Alert",
                    "detail": "validator hit",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        history_service = Mock()
        history_service.get_record_by_id = Mock(
            side_effect=lambda record_id: _make_history_record(
                record_id,
                {
                    "h-1": "alpha example",
                    "h-2": "beta example",
                    "h-3": "gamma example",
                }[record_id],
            )
        )
        settings_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestions[0]["sourceRecordLabel"] == "Local Examples"
        assert (
            "alpha example final" in view_model.reviewSuggestions[0]["sourceRecordText"]
        )
        assert (
            "beta example final" in view_model.reviewSuggestions[0]["sourceRecordText"]
        )
        assert "(+1 more)" in view_model.reviewSuggestions[0]["sourceRecordText"]
        assert view_model.reviewSuggestions[0]["canOpenSourceRecord"] is True
        assert (
            view_model.reviewSuggestions[0]["sourceRecordActionLabel"]
            == "Open Example Record"
        )

    def test_review_bridge_formats_collapsed_fragment_alert_for_review_ui(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "frag-1",
                    "suggestion_type": "collapsed_to_fragment_alert",
                    "confidence": 0.96,
                    "risk_level": "high",
                    "source_record_ids": ["h-1"],
                    "title": "Fragment alert",
                    "detail": "long input collapsed to tiny fragment",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        history_service = Mock()
        history_service.get_record_by_id = Mock(
            return_value=_make_history_record("h-1", "very long source text")
        )
        settings_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestions[0]["typeLabel"] == "Collapsed to Fragment"
        assert view_model.reviewSuggestions[0]["category"] == "content_distortion"
        assert "tiny fragment" in view_model.reviewSuggestions[0]["actionHint"]

    def test_review_source_record_button_opens_history_detail_for_suggestion(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "alert-1",
                    "suggestion_type": "bad_ai_output_alert",
                    "confidence": 0.9,
                    "risk_level": "high",
                    "source_record_ids": ["a-1"],
                    "title": "Alert 1",
                    "detail": "validator hit",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        history_service = Mock()
        history_service.get_record_by_id = Mock(
            return_value=_make_history_record("a-1", "detail source")
        )
        settings_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.openReviewSourceRecord("alert-1") is True
        assert view_model.historyDetailVisible is True
        assert view_model.selectedHistoryDetail["id"] == "a-1"
        assert view_model.selectedHistoryDetail["primaryText"] == "detail source final"

    def test_review_source_record_button_returns_false_without_viewable_record(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "alert-1",
                    "suggestion_type": "bad_ai_output_alert",
                    "confidence": 0.9,
                    "risk_level": "high",
                    "source_record_ids": ["a-1"],
                    "title": "Alert 1",
                    "detail": "validator hit",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        settings_service.get_history_service = Mock(return_value=None)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.openReviewSourceRecord("alert-1") is False
        assert view_model.historyDetailVisible is False

    def test_review_bridge_falls_back_safely_without_storage(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        class SettingsWithoutReviewStorage:
            def get_setting(self, _key, default=None):
                return default

        settings_service = SettingsWithoutReviewStorage()

        view_model = FluentSettingsViewModel(settings_service)

        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestions == []
        assert view_model.lexiconEntries == []
        assert view_model.rejectReviewSuggestion("missing") is False
        assert view_model.ignoreReviewSuggestion("") is False
        assert view_model.archiveReviewSuggestion("") is False
        assert view_model.exportLexiconEntries()["success"] is False
        assert view_model.exportReviewDebugReport()["success"] is False
        assert view_model.clearLexiconEntries() is False
        assert view_model.clearReviewLearningData() is False

    def test_review_bridge_prioritizes_alerts_and_limits_lexicon_candidates(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        suggestions = []
        for index in range(10):
            suggestions.append(
                {
                    "suggestion_id": f"alert-{index}",
                    "suggestion_type": "bad_ai_output_alert",
                    "confidence": 0.9,
                    "risk_level": "high",
                    "source_record_ids": [f"a-{index}"],
                    "title": f"Alert {index}",
                    "detail": "validator hit",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            )
        for index in range(20):
            suggestions.append(
                {
                    "suggestion_id": f"lex-{index}",
                    "suggestion_type": "lexicon_candidate",
                    "confidence": 0.8,
                    "risk_level": "medium",
                    "source_record_ids": [f"l-{index}"],
                    "title": f"Lexicon {index}",
                    "detail": "term candidate",
                    "evidence_count": 2,
                    "new_form": f"Term{index}",
                    "created_at": "2026-06-09T03:00:00",
                }
            )
        settings_service.list_review_suggestions = Mock(return_value=suggestions)
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        history_service = Mock()
        history_service.get_record_by_id = Mock(
            side_effect=lambda record_id: _make_history_record(
                record_id, f"raw {record_id}"
            )
        )
        settings_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestionCount == 18
        assert all(
            item["type"] == "bad_ai_output_alert"
            for item in view_model.reviewSuggestions[:10]
        )
        assert all(
            item["category"] == "boundary_violation"
            for item in view_model.reviewSuggestions[:10]
        )
        assert all(
            item["type"] == "lexicon_candidate"
            for item in view_model.reviewSuggestions[10:]
        )
        summaries = {
            item["category"]: item for item in view_model.reviewCategorySummaries
        }
        assert summaries["boundary_violation"]["totalCount"] == 10
        assert summaries["boundary_violation"]["shownCount"] == 10
        assert summaries["boundary_violation"]["priorityLevel"] == "high"
        assert summaries["lexicon_learning"]["totalCount"] == 20
        assert summaries["lexicon_learning"]["shownCount"] == 8
        assert summaries["lexicon_learning"]["hiddenCount"] == 12
        groups = {item["category"]: item for item in view_model.reviewSuggestionGroups}
        assert groups["boundary_violation"]["shownCount"] == 10
        assert groups["boundary_violation"]["defaultExpanded"] is True
        assert groups["boundary_violation"]["isExpanded"] is True
        assert groups["boundary_violation"]["priorityLabel"] == "Review First"
        assert len(groups["boundary_violation"]["items"]) == 10
        assert all(
            item["canReprocessSample"] is True
            for item in groups["boundary_violation"]["items"]
        )
        assert all(
            item["canRevertToRaw"] is True
            for item in groups["boundary_violation"]["items"]
        )
        assert groups["lexicon_learning"]["hiddenCount"] == 12
        assert groups["lexicon_learning"]["defaultExpanded"] is False
        assert groups["lexicon_learning"]["isExpanded"] is False
        assert groups["lexicon_learning"]["priorityLabel"] == "Review Later"
        assert len(groups["lexicon_learning"]["items"]) == 8
        assert view_model.reviewSuggestionOverflowText == (
            "Showing 18/30 pending suggestions. High-risk issues are prioritized "
            "and extra lexicon candidates are temporarily hidden."
        )

    def test_review_bridge_can_filter_to_category_and_reveal_hidden_items(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        suggestions = []
        for index in range(10):
            suggestions.append(
                {
                    "suggestion_id": f"alert-{index}",
                    "suggestion_type": "bad_ai_output_alert",
                    "confidence": 0.9,
                    "risk_level": "high",
                    "source_record_ids": [f"a-{index}"],
                    "title": f"Alert {index}",
                    "detail": "validator hit",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            )
        for index in range(20):
            suggestions.append(
                {
                    "suggestion_id": f"lex-{index}",
                    "suggestion_type": "lexicon_candidate",
                    "confidence": 0.8,
                    "risk_level": "medium",
                    "source_record_ids": [f"l-{index}"],
                    "title": f"Lexicon {index}",
                    "detail": "term candidate",
                    "evidence_count": 2,
                    "new_form": f"Term{index}",
                    "created_at": "2026-06-09T03:00:00",
                }
            )
        settings_service.list_review_suggestions = Mock(return_value=suggestions)
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.setReviewCategoryFilter("lexicon_learning") is True
        assert view_model.reviewSelectedCategory == "lexicon_learning"
        assert view_model.reviewSelectedCategoryLabel == "Lexicon Learning"
        assert view_model.reviewCategoryFilterActive is True
        assert view_model.reviewSuggestionCount == 20
        assert all(
            item["category"] == "lexicon_learning"
            for item in view_model.reviewSuggestions
        )
        summaries = {
            item["category"]: item for item in view_model.reviewCategorySummaries
        }
        groups = {item["category"]: item for item in view_model.reviewSuggestionGroups}
        assert summaries["boundary_violation"]["shownCount"] == 0
        assert summaries["lexicon_learning"]["shownCount"] == 20
        assert summaries["lexicon_learning"]["isSelected"] is True
        assert list(groups) == ["lexicon_learning"]
        assert groups["lexicon_learning"]["defaultExpanded"] is True
        assert groups["lexicon_learning"]["isExpanded"] is True
        assert len(groups["lexicon_learning"]["items"]) == 20
        assert all(
            item["canReprocessSample"] is False
            for item in groups["lexicon_learning"]["items"]
        )
        assert all(
            item["canRevertToRaw"] is False
            for item in groups["lexicon_learning"]["items"]
        )
        assert view_model.reviewSuggestionOverflowText == ""

        settings_service.list_review_suggestions.return_value = suggestions[:10]
        view_model.refreshReviewSuggestions()
        assert view_model.reviewSelectedCategory == "lexicon_learning"
        assert view_model.reviewCategoryFilterActive is True
        assert view_model.reviewSuggestionCount == 0
        assert view_model.reviewEmptyStateText == (
            "No pending review suggestions in Lexicon Learning."
        )

        assert view_model.setReviewCategoryFilter("all") is True
        assert view_model.reviewSelectedCategory == "all"
        assert view_model.reviewCategoryFilterActive is False

        assert view_model.setReviewCategoryFilter("not-a-real-category") is False
        assert view_model.reviewSelectedCategory == "all"
        assert view_model.reviewCategoryFilterActive is False

    def test_review_group_expanded_state_persists_within_view_model_session(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        suggestions = [
            {
                "suggestion_id": "alert-1",
                "suggestion_type": "bad_ai_output_alert",
                "confidence": 0.9,
                "risk_level": "high",
                "source_record_ids": ["a-1"],
                "title": "Alert 1",
                "detail": "validator hit",
                "evidence_count": 1,
                "created_at": "2026-06-09T03:00:00",
            },
            {
                "suggestion_id": "lex-1",
                "suggestion_type": "lexicon_candidate",
                "confidence": 0.8,
                "risk_level": "medium",
                "source_record_ids": ["l-1"],
                "title": "Lexicon 1",
                "detail": "term candidate",
                "evidence_count": 2,
                "new_form": "Term1",
                "created_at": "2026-06-09T03:00:00",
            },
        ]
        settings_service.list_review_suggestions = Mock(return_value=suggestions)
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        groups = {item["category"]: item for item in view_model.reviewSuggestionGroups}
        assert groups["boundary_violation"]["isExpanded"] is True
        assert groups["lexicon_learning"]["isExpanded"] is False

        assert view_model.toggleReviewSuggestionGroup("boundary_violation") is True
        groups = {item["category"]: item for item in view_model.reviewSuggestionGroups}
        assert groups["boundary_violation"]["isExpanded"] is False

        view_model.refreshReviewSuggestions()
        groups = {item["category"]: item for item in view_model.reviewSuggestionGroups}
        assert groups["boundary_violation"]["isExpanded"] is False

        assert (
            view_model.setReviewSuggestionGroupExpanded("lexicon_learning", True)
            is True
        )
        groups = {item["category"]: item for item in view_model.reviewSuggestionGroups}
        assert groups["lexicon_learning"]["isExpanded"] is True

        assert view_model.setReviewCategoryFilter("lexicon_learning") is True
        groups = {item["category"]: item for item in view_model.reviewSuggestionGroups}
        assert groups["lexicon_learning"]["isExpanded"] is True

        assert view_model.setReviewSuggestionGroupExpanded("missing", True) is False

    def test_review_suggestion_can_trigger_reprocess_for_single_source_alert(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "alert-1",
                    "suggestion_type": "bad_ai_output_alert",
                    "confidence": 0.9,
                    "risk_level": "high",
                    "source_record_ids": ["a-1"],
                    "title": "Alert 1",
                    "detail": "validator hit",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        history_service = Mock()
        source_record = Mock()
        history_service.get_record_by_id = Mock(return_value=source_record)
        settings_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()
        view_model._retry_history_record = Mock()

        assert view_model.reprocessReviewSuggestion("alert-1") is True
        history_service.get_record_by_id.assert_any_call("a-1")
        view_model._retry_history_record.assert_called_once_with(source_record)
        assert view_model.reprocessReviewSuggestion("missing") is False

    def test_review_reprocess_completion_archives_processed_suggestion(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(return_value=[])
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        settings_service.decide_review_suggestion = Mock(return_value=True)
        history_service = Mock()
        history_service.get_records_keyset = Mock(return_value=[])
        history_service.get_aggregate_stats = Mock(return_value=(0, 0.0, 0))
        settings_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(settings_service)
        view_model._pending_review_reprocess_suggestion_id = "alert-1"

        view_model._on_retry_reprocessing_completed({})

        settings_service.decide_review_suggestion.assert_called_with(
            "alert-1", "archived"
        )
        assert view_model.historyActionStage == "complete"
        assert view_model._pending_review_reprocess_suggestion_id == ""

    def test_review_suggestion_can_revert_single_source_alert_to_raw(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "alert-1",
                    "suggestion_type": "bad_ai_output_alert",
                    "confidence": 0.9,
                    "risk_level": "high",
                    "source_record_ids": ["a-1"],
                    "title": "Alert 1",
                    "detail": "validator hit",
                    "evidence_count": 1,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        settings_service.list_lexicon_entries = Mock(return_value=[])
        settings_service.list_review_jobs = Mock(return_value=[])
        history_service = Mock()
        source_record = _make_history_record("a-1", "raw text")
        source_record.final_text = "ai text final"
        history_service.get_record_by_id = Mock(return_value=source_record)
        history_service.get_records_keyset = Mock(return_value=[])
        history_service.get_aggregate_stats = Mock(return_value=(0, 0.0, 0))
        history_service.update_record = Mock(return_value=True)
        settings_service.get_history_service = Mock(return_value=history_service)
        settings_service.decide_review_suggestion = Mock(return_value=True)

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshReviewSuggestions()

        assert view_model.reviewSuggestions[0]["canRevertToRaw"] is True
        assert view_model.revertReviewSuggestionToRaw("alert-1") is True
        assert source_record.final_text == "raw text"
        history_service.update_record.assert_called_once_with(source_record)
        settings_service.decide_review_suggestion.assert_called_with(
            "alert-1", "archived"
        )
        assert view_model.historyActionStage == "complete"
        assert "reverted" in view_model.historyActionMessage.lower()
        assert view_model.revertReviewSuggestionToRaw("missing") is False

    def test_history_refresh_uses_history_service_and_updates_stats(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        records = [_make_history_record("h-1", "hello history")]
        history_service = Mock()
        history_service.get_records_keyset.return_value = records
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("")

        mock_config_service.get_history_service.assert_called_once()
        history_service.get_records_keyset.assert_called_once()
        assert view_model.historyRecords[0]["id"] == "h-1"
        assert view_model.historyRecords[0]["primaryText"] == "hello history final"
        assert "Path: streaming_chunked" in view_model.historyRecords[0]["tooltip"]
        assert view_model.historyTotalText == "Total Records: 1"
        assert view_model.historyDurationText == "Total Duration: 2.5s"
        assert view_model.historySuccessRateText == "Success Rate: 100.0%"

    def test_history_search_uses_keyset_search_and_query_stats(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        history_service = Mock()
        history_service.search_records_keyset.return_value = [
            _make_history_record("h-2", "needle")
        ]
        history_service.get_aggregate_stats.return_value = (3, 7.5, 2)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("needle")

        history_service.search_records_keyset.assert_called_once()
        assert history_service.search_records_keyset.call_args.kwargs["query"] == (
            "needle"
        )
        history_service.get_aggregate_stats.assert_called_once_with(query="needle")
        assert len(view_model.historyRecords) == 1
        assert view_model.historySuccessRateText == "Success Rate: 66.7%"

    def test_history_load_more_appends_next_keyset_page(self, mock_config_service):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        first = _make_history_record("h-1", "first")
        second = _make_history_record("h-2", "second")
        history_service = Mock()
        history_service.get_records_keyset.side_effect = [[first], [second]]
        history_service.get_aggregate_stats.return_value = (2, 5.0, 2)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(mock_config_service)
        view_model._history_page_size = 1
        view_model.refreshHistory("")
        view_model.loadMoreHistory()

        assert [item["id"] for item in view_model.historyRecords] == ["h-1", "h-2"]
        second_call = history_service.get_records_keyset.call_args_list[1]
        assert second_call.kwargs["cursor_timestamp"] == first.timestamp
        assert second_call.kwargs["cursor_id"] == "h-1"

    def test_history_detail_opens_qml_panel_without_widget_dialog(
        self, mock_config_service, monkeypatch
    ):
        import sonicinput.ui.qml_bridge as qml_bridge

        record = _make_history_record("h-1", "detail")
        history_service = Mock()
        history_service.get_records_keyset.return_value = [record]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        class FakeDialog:
            def __init__(self, **_kwargs):
                raise AssertionError("Fluent history must use the QML detail panel")

        monkeypatch.setattr(
            qml_bridge, "HistoryDetailDialog", FakeDialog, raising=False
        )

        view_model = qml_bridge.FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("")
        view_model.openHistoryDetail(0)

        assert view_model.historyDetailVisible is True
        assert view_model.selectedHistoryDetail["id"] == "h-1"
        assert view_model.selectedHistoryDetail["primaryText"] == "detail final"
        assert (
            view_model.selectedHistoryDetail["transcriptionPath"] == "streaming_chunked"
        )
        assert (
            view_model.selectedHistoryDetail["transcriptionDecisionReason"]
            == "streaming_stop_result"
        )
        assert view_model.selectedHistoryDetail["fallbackType"] == "none"
        history_service.get_records_keyset.assert_called_once()

    def test_history_delete_refreshes_model(self, mock_config_service):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        record = _make_history_record("h-1", "delete me")
        history_service = Mock()
        history_service.get_records_keyset.side_effect = [[record], []]
        history_service.get_aggregate_stats.return_value = (0, 0.0, 0)
        history_service.delete_record.return_value = True
        mock_config_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("")

        assert view_model.deleteHistoryRecord(0) is True
        history_service.delete_record.assert_called_once_with("h-1")
        assert view_model.historyRecords == []

    def test_selected_history_delete_refreshes_and_closes_detail(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        record = _make_history_record("h-1", "selected delete")
        history_service = Mock()
        history_service.get_records_keyset.side_effect = [[record], []]
        history_service.get_aggregate_stats.return_value = (0, 0.0, 0)
        history_service.delete_record.return_value = True
        mock_config_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("")
        view_model.openHistoryDetail(0)

        assert view_model.deleteSelectedHistoryRecord() is True
        history_service.delete_record.assert_called_once_with("h-1")
        assert view_model.historyDetailVisible is False
        assert view_model.historyRecords == []

    def test_history_batch_reprocess_opens_qml_confirmation_without_widget_dialogs(
        self, mock_config_service
    ):
        history_service = Mock()
        history_service.get_total_count.return_value = 12
        mock_config_service.get_history_service = Mock(return_value=history_service)

        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        view_model = FluentSettingsViewModel(mock_config_service)
        view_model.startBatchReprocess()

        assert view_model.batchReprocessVisible is True
        assert view_model.batchReprocessStage == "confirm"
        assert view_model.batchReprocessTotal == 12
        assert view_model.batchReprocessProgressValue == 0

    def test_history_batch_reprocess_confirm_starts_worker_with_qml_progress(
        self, mock_config_service, monkeypatch
    ):
        import sonicinput.ui.qml_bridge as qml_bridge

        history_service = Mock()
        history_service.get_total_count.return_value = 2
        mock_config_service.get_history_service = Mock(return_value=history_service)
        mock_config_service.get_transcription_service = Mock(return_value=object())
        mock_config_service.get_ai_processing_controller = Mock(return_value=None)

        started_workers = []

        class FakeWorker:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.progress_updated = Mock()
                self.batch_completed = Mock()
                started_workers.append(self)

            def start(self):
                self.started = True

        monkeypatch.setattr(qml_bridge, "BatchReprocessingWorker", FakeWorker)

        view_model = qml_bridge.FluentSettingsViewModel(mock_config_service)
        view_model.startBatchReprocess()
        view_model.confirmBatchReprocess(3)

        assert view_model.batchReprocessStage == "running"
        assert view_model.batchReprocessRunning is True
        assert view_model.batchReprocessProgressTotal == 2
        assert started_workers[0].kwargs["cd_seconds"] == 3

    def test_retry_history_record_uses_qml_action_state(
        self, mock_config_service, monkeypatch
    ):
        import sonicinput.ui.qml_bridge as qml_bridge

        record = _make_history_record("h-1", "retry me")
        history_service = Mock()
        history_service.get_records_keyset.return_value = [record]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        history_service.get_record_by_id.return_value = record
        mock_config_service.get_history_service = Mock(return_value=history_service)
        mock_config_service.get_transcription_service = Mock(return_value=object())
        mock_config_service.get_ai_processing_controller = Mock(return_value=None)

        started_workers = []

        class FakeWorker:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.progress_updated = Mock()
                self.reprocessing_completed = Mock()
                self.reprocessing_failed = Mock()
                started_workers.append(self)

            def start(self):
                self.started = True

        monkeypatch.setattr(qml_bridge, "ReprocessingWorker", FakeWorker)

        view_model = qml_bridge.FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("")
        view_model.retryHistoryRecord(0)

        assert view_model.historyActionBusy is True
        assert view_model.historyActionStage == "running"
        assert started_workers[0].kwargs["record_id"] == "h-1"


@pytest.mark.gui
class TestFluentSettingsParity:
    def test_full_settings_draft_applies_old_window_config_surface(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        view_model = FluentSettingsViewModel(mock_config_service)

        view_model.setValue("ui.language", "zh-CN")
        view_model.setValue("hotkeys.keys", ["f12", "ctrl+shift+v"])
        view_model.setValue("hotkeys.backend", "pynput")
        view_model.setValue("transcription.provider", "qwen")
        view_model.setValue("transcription.qwen.api_key", "qwen-key")
        view_model.setValue("transcription.qwen.model", "qwen3-asr-flash")
        view_model.setValue(
            "transcription.qwen.base_url", "https://dashscope.aliyuncs.com"
        )
        view_model.setValue("transcription.qwen.enable_itn", False)
        view_model.setValue("transcription.qwen.timeout", 45)
        view_model.setValue("transcription.qwen.max_retries", 4)
        view_model.setValue("ai.provider", "openai_compatible")
        view_model.setValue("ai.openai_compatible.base_url", "https://llm.example/v1")
        view_model.setValue("ai.openai_compatible.api_key", "ai-key")
        view_model.setValue("ai.openai_compatible.model_id", "model-x")
        view_model.setValue("ai.prompt", "Clean this transcript")
        view_model.setValue("ai.first_chunk_output.enabled", True)
        view_model.setValue("audio.streaming.chunk_duration", 7.5)
        view_model.setValue("input.preferred_method", "sendinput")
        view_model.setValue("input.typing_delay", 0.03)
        view_model.apply()

        assert mock_config_service.get_setting("ui.language") == "zh-CN"
        assert mock_config_service.get_setting("hotkeys.keys") == [
            "f12",
            "ctrl+shift+v",
        ]
        assert mock_config_service.get_setting("hotkeys.backend") == "pynput"
        assert mock_config_service.get_setting("transcription.provider") == "qwen"
        assert (
            mock_config_service.get_setting("transcription.qwen.api_key") == "qwen-key"
        )
        assert mock_config_service.get_setting("transcription.qwen.enable_itn") is False
        assert mock_config_service.get_setting("ai.provider") == "openai_compatible"
        assert (
            mock_config_service.get_setting("ai.openai_compatible.base_url")
            == "https://llm.example/v1"
        )
        assert mock_config_service.get_setting("ai.prompt") == "Clean this transcript"
        assert mock_config_service.get_setting("ai.first_chunk_output.enabled") is True
        assert mock_config_service.get_setting("audio.streaming.chunk_duration") == 7.5
        assert mock_config_service.get_setting("input.preferred_method") == "sendinput"
        assert mock_config_service.get_setting("input.typing_delay") == 0.03

    def test_apply_language_invokes_runtime_localization_service(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        localization_service = Mock()
        mock_config_service.get_localization_service = Mock(
            return_value=localization_service
        )
        view_model = FluentSettingsViewModel(mock_config_service)

        view_model.setValue("ui.language", "zh-CN")
        view_model.apply()

        assert mock_config_service.get_setting("ui.language") == "zh-CN"
        localization_service.apply_language.assert_called_once()

    def test_view_model_translates_qml_labels_from_selected_language(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        view_model = FluentSettingsViewModel(mock_config_service)

        assert view_model.translate("application", "Application") == "Application"

        view_model.setValue("ui.language", "zh-CN")

        assert view_model.uiLanguage == "zh-CN"
        assert view_model.translate("application", "Application") == "应用"
        assert view_model.translate("apply", "Apply") == "应用"
        assert view_model.translate("filter_thinking_tags", "Filter thinking tags") == (
            "过滤思考标签"
        )
        assert view_model.translate("system_prompt", "System Prompt") == "系统提示词"

    def test_hotkey_management_adds_replaces_and_removes_shortcuts(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        view_model = FluentSettingsViewModel(mock_config_service)

        assert view_model.hotkeyList == ["f12"]
        assert view_model.hotkeyCount == 1

        added = view_model.addHotkey("Ctrl+Shift+V")
        assert added["success"] is True
        assert view_model.hotkeyList == ["f12", "ctrl+shift+v"]

        duplicate = view_model.addHotkey("ctrl+shift+v")
        assert duplicate["success"] is False
        assert "exists" in duplicate["message"] or "存在" in duplicate["message"]

        replaced = view_model.replaceHotkey("Alt+F9", 0)
        assert replaced["success"] is True
        assert view_model.hotkeyList == ["alt+f9", "ctrl+shift+v"]

        removed = view_model.removeHotkeyAt(0)
        assert removed["success"] is True
        assert view_model.hotkeyList == ["ctrl+shift+v"]

        blocked = view_model.removeHotkeyAt(0)
        assert blocked["success"] is False
        assert (
            "at least one" in blocked["message"].lower() or "至少" in blocked["message"]
        )

    def test_hotkey_normalization_keeps_modifiers_ordered(self, mock_config_service):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        view_model = FluentSettingsViewModel(mock_config_service)

        assert view_model.normalizeHotkey("Command + Shift + V") == "shift+win+v"

    def test_settings_host_exposes_model_management_signals(
        self, qtbot, mock_config_service
    ):
        from sonicinput.ui.fluent_settings_window import FluentSettingsWindow

        settings = FluentSettingsWindow(mock_config_service)
        assert hasattr(settings, "model_load_requested")
        assert hasattr(settings, "model_unload_requested")
        assert hasattr(settings, "model_test_requested")

        with qtbot.waitSignal(settings.model_load_requested, timeout=1000) as blocker:
            settings.requestModelLoad("paraformer")
        assert blocker.args == ["paraformer"]

        with qtbot.waitSignal(settings.model_unload_requested, timeout=1000):
            settings.requestModelUnload()

        with qtbot.waitSignal(settings.model_test_requested, timeout=1000):
            settings.requestModelTest()

    def test_settings_qml_exposes_editable_controls_without_migration_copy(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        assert "widget fallback" not in qml_source
        assert "during QML migration" not in qml_source

        for object_name in [
            "languageCombo",
            "hotkeyCaptureButton",
            "hotkeysListView",
            "hotkeyBackendCombo",
            "transcriptionProviderCombo",
            "qwenApiKeyField",
            "aiProviderCombo",
            "openAiCompatibleBaseUrlField",
            "aiPromptField",
            "audioDeviceField",
            "inputMethodCombo",
            "historySearchField",
            "qualityReviewPage",
            "reviewSuggestionList",
            "lexiconEntryList",
        ]:
            assert f'objectName: "{object_name}"' in qml_source

    def test_settings_qml_has_quality_review_page_controls(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        for object_name in [
            "qualityReviewPage",
            "reviewRefreshButton",
            "runReviewNowButton",
            "reviewRunMessageLabel",
            "exportReviewDebugReportButton",
            "reviewDebugExportHelpLabel",
            "reviewDebugExportMessageLabel",
            "reviewJobsFrame",
            "reviewJobsRepeater",
            "reviewJobCreatedAtLabel",
            "reviewJobSummaryLabel",
            "reviewEnabledSwitch",
            "reviewUseLexiconMemorySwitch",
            "reviewIdleSecondsSpin",
            "reviewMaxRecordsSpin",
            "reviewEmptyState",
            "reviewEmptyStateLabel",
            "reviewBackToOverviewButton",
            "reviewSuggestionList",
            "reviewSuggestionGroupRepeater",
            "reviewSuggestionGroupFrame",
            "reviewSuggestionGroupLabel",
            "reviewSuggestionGroupCount",
            "reviewSuggestionGroupPriorityBadge",
            "reviewSuggestionGroupPriorityLabel",
            "reviewSuggestionGroupHiddenLabel",
            "reviewSuggestionGroupToggleButton",
            "reviewSuggestionGroupBody",
            "reviewSuggestionGroupDescription",
            "reviewSuggestionItemRepeater",
            "reviewSuggestionCard",
            "reviewSuggestionTypeLabel",
            "reviewSuggestionRiskLabel",
            "reviewSuggestionRiskDescriptionLabel",
            "reviewSuggestionEvidenceLabel",
            "reviewSuggestionSourceLabel",
            "reviewOpenSourceRecordButton",
            "reviewSuggestionOverflowLabel",
            "reviewCategoryAllButton",
            "reviewSelectedCategoryLabel",
            "reviewCategorySummaryPriorityBadge",
            "reviewCategorySummaryPriorityLabel",
            "reviewCategoryFilterButton",
            "reviewSuggestionActionHintLabel",
            "reviewAcceptButton",
            "reviewRejectButton",
            "reviewIgnoreOnceButton",
            "reviewIgnoreButton",
            "reviewIgnoreScopeHintLabel",
            "reviewReprocessButton",
            "reviewRevertToRawButton",
            "lexiconEntryList",
            "exportLexiconButton",
            "lexiconExportMessageLabel",
            "clearLexiconButton",
            "clearReviewLearningDataButton",
            "reviewLearningDataMessageLabel",
        ]:
            assert f'objectName: "{object_name}"' in qml_source

        assert 'root.t("quality_review", "Local Quality Review")' in qml_source
        assert 'root.setValue("review.enabled", checked)' in qml_source
        assert 'root.setValue("review.use_lexicon_memory", checked)' in qml_source
        assert "refreshReviewSuggestions()" in qml_source
        assert "runReviewNow()" in qml_source
        assert "exportReviewDebugReport()" in qml_source
        assert 'setReviewCategoryFilter("all")' in qml_source
        assert "setReviewCategoryFilter(modelData.category)" in qml_source
        assert "reviewEmptyStateText" in qml_source
        assert "openReviewSourceRecord(modelData.id)" in qml_source
        assert "reviewIgnoreScopeHint" in qml_source
        assert "clearReviewLearningData()" in qml_source
        assert 'root.t("review_back_to_overview", "Back to Overview")' in qml_source
        assert "toggleReviewSuggestionGroup(modelData.category)" in qml_source
        assert 'modelData.priorityLevel === "high"' in qml_source
        assert 'root.t("review_group_expand", "Expand")' in qml_source
        assert 'root.t("review_group_collapse", "Collapse")' in qml_source
        assert 'root.t("ignore_once", "Ignore Once")' in qml_source
        assert 'root.t("always_ignore_similar", "Always Ignore Similar")' in qml_source
        assert "archiveReviewSuggestion(modelData.id)" in qml_source
        assert 'root.t("export_lexicon", "Export Lexicon")' in qml_source
        assert "exportLexiconEntries()" in qml_source
        assert (
            'root.t("review_export_debug_report", "Export Debug Report")' in qml_source
        )
        assert 'root.t("reprocess_sample", "Reprocess Sample")' in qml_source
        assert "reprocessReviewSuggestion(modelData.id)" in qml_source
        assert 'root.t("revert_to_raw", "Revert to Raw Transcript")' in qml_source
        assert "revertReviewSuggestionToRaw(modelData.id)" in qml_source
        assert "acceptReviewSuggestion(modelData.id)" in qml_source
        assert "clearLexiconEntries()" in qml_source

    def test_hotkeys_section_uses_standard_shortcut_management_ui(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        assert 'objectName: "hotkeysToolbar"' in qml_source
        assert 'objectName: "hotkeysListView"' in qml_source
        assert 'objectName: "hotkeyCaptureButton"' in qml_source
        assert 'objectName: "hotkeyCapturePanel"' in qml_source
        assert 'objectName: "hotkeyRecorderSurface"' in qml_source
        assert 'objectName: "hotkeyStatusLabel"' in qml_source
        assert 'objectName: "hotkeyDelegateChangeButton"' in qml_source
        assert 'objectName: "hotkeyDelegateRemoveButton"' in qml_source
        assert "function hotkeyLabelText" in qml_source
        assert 'root.t("active_hotkeys", "Active hotkeys")' in qml_source
        assert 'root.t("add_shortcut", "Add shortcut")' in qml_source
        assert 'root.t("capture_cancel_hint", "Press Esc to cancel")' in qml_source
        assert 'root.t("remove", "Remove")' in qml_source
        assert "color: palette.base" in qml_source
        assert "color: palette.alternateBase" not in qml_source
        assert "border.color: palette.highlight" not in qml_source
        assert "border.color: palette.mid" in qml_source
        assert 'objectName: "hotkeysField"' not in qml_source
        assert "one_hotkey_per_line" not in qml_source

    def test_provider_settings_are_progressively_disclosed(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        for expected in [
            'visible: root.selectedTranscriptionProvider === "local"',
            'visible: root.selectedTranscriptionProvider === "groq"',
            'visible: root.selectedTranscriptionProvider === "siliconflow"',
            'visible: root.selectedTranscriptionProvider === "qwen"',
            'visible: root.selectedAiProvider === "openrouter"',
            'visible: root.selectedAiProvider === "groq"',
            'visible: root.selectedAiProvider === "nvidia"',
            'visible: root.selectedAiProvider === "openai_compatible"',
        ]:
            assert expected in qml_source

        assert 'title: root.t("provider_credentials", "Provider Credentials")' not in (
            qml_source
        )
        assert 'ListElement { value: "qwen"; label: "Qwen ASR (Alibaba Cloud)" }' in (
            qml_source
        )
        assert (
            'ListElement { value: "openai_compatible"; label: "OpenAI Compatible" }'
            in qml_source
        )

    def test_ai_behavior_and_prompt_copy_are_translated(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        for token in [
            "filter_thinking_tags",
            "enable_sentence_split",
            "start_ai_after_first_chunk",
            "enable_ai_streaming_output",
            "system_prompt",
            "system_prompt_help",
            "system_prompt_placeholder",
        ]:
            assert f'root.t("{token}"' in qml_source

        assert 'placeholderText: "System prompt"' not in qml_source

    def test_ai_prompt_editor_uses_fixed_scrollable_editor(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        assert 'objectName: "aiPromptScrollView"' in qml_source
        assert 'objectName: "aiPromptField"' in qml_source
        assert "ScrollView {" in qml_source
        assert "Layout.preferredHeight: 170" in qml_source
        assert "Math.max(220, aiPromptField.contentHeight + 28)" not in qml_source
        assert "wrapMode: TextEdit.WordWrap" in qml_source
        assert "verticalAlignment: TextEdit.AlignTop" in qml_source
        assert "ScrollBar.vertical.policy: ScrollBar.AsNeeded" in qml_source
        assert "ScrollBar.horizontal.policy: ScrollBar.AlwaysOff" in qml_source

    def test_settings_qml_updates_language_without_reopen(
        self, qapp, mock_config_service
    ):
        from PySide6.QtCore import QObject, QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel, qml_path

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("settingsViewModel", view_model)
        engine.rootContext().setContextProperty("settingsHost", None)
        engine.load(QUrl.fromLocalFile(str(qml_path("FluentSettingsWindow.qml"))))
        root = engine.rootObjects()[0]
        apply_button = root.findChild(QObject, "applyButton")

        assert apply_button.property("text") == "Apply"

        view_model.setValue("ui.language", "zh-CN")
        qapp.processEvents()

        assert apply_button.property("text") == "应用"

    def test_settings_qml_shows_only_selected_provider_cards(
        self, qapp, mock_config_service
    ):
        from PySide6.QtCore import QObject, QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel, qml_path

        # provider 校验要求 api_key 已配置，先写入 key 再切换 provider
        mock_config_service.set_setting("transcription.qwen.api_key", "test-key")
        mock_config_service.set_setting("transcription.provider", "qwen")
        mock_config_service.set_setting("ai.provider", "openai_compatible")

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("settingsViewModel", view_model)
        engine.rootContext().setContextProperty("settingsHost", None)
        engine.load(QUrl.fromLocalFile(str(qml_path("FluentSettingsWindow.qml"))))
        root = engine.rootObjects()[0]

        root.setProperty("selectedSection", 2)
        qapp.processEvents()
        transcription_visible_cards = {
            name: root.findChild(QObject, name).property("visible")
            for name in [
                "localTranscriptionCard",
                "groqTranscriptionCard",
                "siliconflowTranscriptionCard",
                "qwenTranscriptionCard",
            ]
        }

        root.setProperty("selectedSection", 3)
        qapp.processEvents()
        ai_visible_cards = {
            name: root.findChild(QObject, name).property("visible")
            for name in [
                "openrouterAiCard",
                "groqAiCard",
                "nvidiaAiCard",
                "openAiCompatibleAiCard",
            ]
        }

        assert transcription_visible_cards == {
            "localTranscriptionCard": False,
            "groqTranscriptionCard": False,
            "siliconflowTranscriptionCard": False,
            "qwenTranscriptionCard": True,
        }
        assert ai_visible_cards == {
            "openrouterAiCard": False,
            "groqAiCard": False,
            "nvidiaAiCard": False,
            "openAiCompatibleAiCard": True,
        }

    def test_settings_qml_binds_history_page_to_view_model(
        self, qapp, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        history_service = Mock()
        history_service.get_records_keyset.return_value = [
            _make_history_record("h-1", "qml record")
        ]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)

        view_model.refreshHistory("")
        qapp.processEvents()

        history_list = root.findChild(QObject, "historyList")
        empty_state = root.findChild(QObject, "historyEmptyState")
        total_label = root.findChild(QObject, "historyTotalLabel")

        assert history_list.property("count") == 1
        assert empty_state.property("visible") is False
        assert total_label.property("text") == "Total Records: 1"

    def test_settings_qml_shows_history_empty_state_only_without_records(
        self, qapp, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        history_service = Mock()
        history_service.get_records_keyset.return_value = []
        history_service.get_aggregate_stats.return_value = (0, 0.0, 0)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)

        view_model.refreshHistory("")
        qapp.processEvents()

        history_list = root.findChild(QObject, "historyList")
        empty_state = root.findChild(QObject, "historyEmptyState")

        assert history_list.property("count") == 0
        assert empty_state.property("visible") is True

    def test_settings_qml_history_list_fills_available_panel_height(
        self, qapp, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        history_service = Mock()
        history_service.get_records_keyset.return_value = [
            _make_history_record("h-1", "adaptive record")
        ]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)
        root.setHeight(820)
        view_model.refreshHistory("")
        qapp.processEvents()

        history_list_frame = root.findChild(QObject, "historyListFrame")

        assert history_list_frame is not None
        assert history_list_frame.property("height") >= 520

    def test_settings_qml_history_long_text_does_not_crowd_actions(
        self, qapp, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        long_text = " ".join(["very-long-history-transcription-segment"] * 30)
        history_service = Mock()
        history_service.get_records_keyset.return_value = [
            _make_history_record("h-1", long_text)
        ]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)
        root.setWidth(900)
        view_model.refreshHistory("")
        qapp.processEvents()

        history_list = root.findChild(QObject, "historyList")

        reserved_width = (
            history_list.property("delegateTimeWidth")
            + history_list.property("delegateTextMinimumWidth")
            + history_list.property("delegateStatusWidth")
            + history_list.property("delegateActionWidth")
        )

        assert history_list.property("count") == 1
        assert history_list.property("delegateTextMinimumWidth") >= 120
        assert reserved_width < history_list.property("width")

    def test_settings_qml_history_labels_are_forced_to_single_line_elide(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        for object_name in [
            "historyDelegatePrimaryLabel",
            "historyDelegateTimestampLabel",
            "historyDelegateStatusLabel",
        ]:
            assert f'objectName: "{object_name}"' in qml_source

        assert 'objectName: "historyDelegateTranscriptionLabel"' not in qml_source
        assert qml_source.count("wrapMode: Text.NoWrap") >= 5
        assert qml_source.count("maximumLineCount: 1") >= 5

    def test_settings_qml_history_detail_button_matches_status_height(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        assert "property int delegateControlHeight:" in qml_source
        assert "height: historyList.delegateControlHeight" in qml_source
        assert "anchors.verticalCenter: parent.verticalCenter" in qml_source

    def test_settings_qml_history_detail_panel_uses_fluent_surface(
        self, qapp, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        history_service = Mock()
        history_service.get_records_keyset.return_value = [
            _make_history_record("h-1", "detail panel")
        ]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)
        view_model.refreshHistory("")
        view_model.openHistoryDetail(0)
        qapp.processEvents()

        panel = root.findChild(QObject, "historyDetailPanel")
        final_text = root.findChild(QObject, "historyDetailFinalText")
        diagnostics = root.findChild(QObject, "historyDetailDiagnosticsCard")
        record_id = root.findChild(QObject, "historyDetailRecordIdValue")
        transcription_path = root.findChild(
            QObject, "historyDetailTranscriptionPathValue"
        )
        decision_reason = root.findChild(QObject, "historyDetailDecisionReasonValue")
        fallback_type = root.findChild(QObject, "historyDetailFallbackTypeValue")

        assert panel is not None
        assert panel.property("visible") is True
        assert final_text.property("text") == "detail panel final"
        assert diagnostics.property("visible") is True
        assert record_id.property("text") == "h-1"
        assert transcription_path.property("text") == "streaming_chunked"
        assert decision_reason.property("text") == "streaming_stop_result"
        assert fallback_type.property("text") == "none"

    def test_settings_qml_history_has_batch_confirm_and_progress_surfaces(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        for object_name in [
            "historyBatchConfirmDialog",
            "historyBatchCooldownSpin",
            "historyBatchProgressDialog",
            "historyBatchProgressBar",
            "historyBatchProgressLabel",
        ]:
            assert f'objectName: "{object_name}"' in qml_source


@pytest.mark.gui
class TestFluentOverlayViewModel:
    def test_overlay_state_and_stop_signal(self, qtbot):
        from sonicinput.ui.qml_bridge import FluentOverlayViewModel

        view_model = FluentOverlayViewModel()
        view_model.showRecording()
        view_model.updateAudioLevel(0.42)

        assert view_model.statusText == "Recording"
        assert view_model.audioLevel == pytest.approx(0.42)
        assert view_model.visible is True

        with qtbot.waitSignal(view_model.stopRecordingRequested, timeout=1000):
            view_model.requestStop()


@pytest.mark.gui
class TestFluentRecordingOverlayHost:
    def test_overlay_qml_uses_waveform_meter_without_status_copy(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentRecordingOverlay.qml").read_text(encoding="utf-8")

        assert (
            'text: root.viewModel ? root.viewModel.statusText : "Ready"'
            not in qml_source
        )
        assert "root.viewModel.statusText" not in qml_source
        assert "function visualLevel" in qml_source
        assert 'objectName: "waveformMeter"' in qml_source
        assert "model: 11" in qml_source
        assert "width: 232" in qml_source
        assert "height: 52" in qml_source
        assert "Qt.WindowStaysOnTopHint" in qml_source
        assert "Qt.WindowDoesNotAcceptFocus" in qml_source
        assert "anchors.leftMargin: 7" in qml_source
        assert "anchors.rightMargin: 7" in qml_source
        assert "Layout.preferredWidth: 48" in qml_source
        assert "Layout.preferredWidth: 42" in qml_source
        assert "Layout.leftMargin: 4" in qml_source

    def test_settings_qml_uses_consistent_windows_ui_font(self):
        from sonicinput.ui.qml_bridge import qml_path

        settings_source = qml_path("FluentSettingsWindow.qml").read_text(
            encoding="utf-8"
        )
        card_source = qml_path("SettingsCard.qml").read_text(encoding="utf-8")

        assert 'font.family: "Microsoft YaHei UI"' in settings_source
        assert card_source.count('font.family: "Microsoft YaHei UI"') >= 2
        assert "font.weight: Font.Medium" in card_source

    def test_public_methods_are_queued_to_qt_thread(self, qtbot):
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication
        from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay

        overlay = FluentRecordingOverlay()
        calls = []

        def record_call():
            calls.append(QThread.currentThread())

        overlay.show_recording_requested.connect(record_call)

        worker = QThread()
        worker.started.connect(overlay.show_recording)
        worker.started.connect(worker.quit)
        worker.start()

        qtbot.waitUntil(lambda: bool(calls), timeout=2000)
        worker.wait(1000)

        assert calls == [QApplication.instance().thread()]
        overlay.hide_recording()

    def test_show_recording_reasserts_topmost_window_state(
        self, qapp, mock_config_service, monkeypatch
    ):
        from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay

        overlay = FluentRecordingOverlay()
        overlay.set_config_service(mock_config_service)

        calls = {"set_flag": [], "raise": 0, "activate": 0}

        def record_set_flag(flag, enabled=True):
            calls["set_flag"].append((flag, enabled))

        def record_raise():
            calls["raise"] += 1

        def record_activate():
            calls["activate"] += 1

        monkeypatch.setattr(overlay.root, "setFlag", record_set_flag, raising=False)
        monkeypatch.setattr(overlay.root, "raise_", record_raise, raising=False)
        monkeypatch.setattr(
            overlay.root, "requestActivate", record_activate, raising=False
        )

        overlay.show_recording()

        assert calls["set_flag"] == [
            (Qt.WindowType.WindowStaysOnTopHint, True),
            (Qt.WindowType.WindowDoesNotAcceptFocus, True),
        ]
        assert calls["raise"] == 1
        assert calls["activate"] == 0

    def test_overlay_drag_position_is_persisted(self, qapp, mock_config_service):
        from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay

        overlay = FluentRecordingOverlay()
        overlay.set_config_service(mock_config_service)

        overlay.save_position(321, 234)

        assert mock_config_service.get_setting("ui.overlay_position.mode") == "custom"
        assert mock_config_service.get_setting("ui.overlay_position.custom.x") == 321
        assert mock_config_service.get_setting("ui.overlay_position.custom.y") == 234

        overlay.root.setX(0)
        overlay.root.setY(0)
        overlay.restore_position()

        assert int(overlay.root.x()) == 321
        assert int(overlay.root.y()) == 234

    def test_overlay_position_respects_auto_save_setting(
        self, qapp, mock_config_service
    ):
        from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay

        overlay = FluentRecordingOverlay()
        overlay.set_config_service(mock_config_service)
        mock_config_service.set_setting("ui.overlay_position.auto_save", False)

        overlay.save_position(321, 234)

        assert mock_config_service.get_setting("ui.overlay_position.mode") != "custom"
        assert mock_config_service.get_setting("ui.overlay_position.custom.x") != 321
        assert mock_config_service.get_setting("ui.overlay_position.custom.y") != 234

    def test_overlay_position_persists_screen_metadata(self, qapp, mock_config_service):
        from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay

        overlay = FluentRecordingOverlay()
        overlay.set_config_service(mock_config_service)

        overlay.save_position(321, 234)

        last_screen = mock_config_service.get_setting(
            "ui.overlay_position.last_screen", {}
        )
        assert isinstance(last_screen, dict)
        assert "name" in last_screen
        assert "geometry" in last_screen
        assert "device_pixel_ratio" in last_screen


@pytest.mark.gui
class TestMainWindowReviewAutoTimer:
    def test_main_window_review_timer_uses_settings_service(self, qtbot):
        from sonicinput.ui.main_window import MainWindow

        settings_service = Mock()
        settings_service.run_idle_review_once = Mock(
            return_value={"ran": False, "reason": "review_disabled"}
        )

        window = MainWindow(ui_settings_service=settings_service)
        qtbot.addWidget(window)

        timer = getattr(window, "_review_auto_timer", None)
        assert timer is not None
        assert timer.isActive() is True

        window._on_review_auto_timer()

        settings_service.run_idle_review_once.assert_called_once()

    def test_main_window_review_timer_refreshes_open_settings_after_run(self, qtbot):
        from sonicinput.ui.main_window import MainWindow

        settings_service = Mock()
        settings_service.run_idle_review_once = Mock(
            return_value={
                "ran": True,
                "reason": "completed",
                "jobId": "job-1",
                "reviewedRecordCount": 4,
                "suggestionCount": 1,
            }
        )
        refresh = Mock()
        settings_window = Mock()
        settings_window.view_model.refreshReviewSuggestions = refresh

        window = MainWindow(ui_settings_service=settings_service)
        window._settings_window = settings_window
        qtbot.addWidget(window)

        window._on_review_auto_timer()

        refresh.assert_called_once()


@pytest.mark.gui
class TestReviewUiSyntheticFlow:
    def test_synthetic_review_run_surfaces_in_view_model(self):
        from pathlib import Path
        from uuid import uuid4

        from sonicinput.core.quality import HistoryReviewAgent
        from sonicinput.core.services.storage import ReviewStorageService
        from sonicinput.core.services.ui_services import UISettingsService
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        db_path = Path("quality_audit") / f"test_review_ui_flow_{uuid4().hex}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        records = [
            {
                "id": "synthetic-low-info",
                "transcription_status": "success",
                "transcription_text": "嗯",
                "ai_status": "success",
                "ai_optimized_text": "请提供需要优化的文本，我可以帮你整理并生成完整说明。",
                "final_text": "请提供需要优化的文本，我可以帮你整理并生成完整说明。",
            }
        ]
        suggestions = HistoryReviewAgent().analyze_records(records)
        review_storage = ReviewStorageService(db_path)
        job_id = review_storage.save_review_run(
            suggestions,
            record_limit=20,
            reviewed_count=len(records),
        )

        config = Mock()
        config.get_setting = Mock(side_effect=lambda _key, default=None: default)
        config.get_all_settings = Mock(return_value={})
        service = UISettingsService(
            config_service=config,
            event_service=Mock(),
            history_service=Mock(),
            review_storage_service=review_storage,
        )
        view_model = FluentSettingsViewModel(service)

        view_model.refreshReviewSuggestions()

        assert job_id.startswith("review_job_")
        assert view_model.reviewSuggestionCount >= 1
        assert view_model.reviewJobCount == 1
        assert view_model.reviewJobs[0]["reviewedRecordCount"] == 1
        assert view_model.reviewJobs[0]["suggestionCount"] == len(suggestions)
        assert any(
            item["type"] == "low_information_expansion_alert"
            for item in view_model.reviewSuggestions
        )


@pytest.mark.gui
class TestFluentQmlLoading:
    def test_settings_qml_loads_with_fluent_style(self, qapp, mock_config_service):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel, qml_path

        QQuickStyle.setStyle("FluentWinUI3")
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty(
            "settingsViewModel", FluentSettingsViewModel(mock_config_service)
        )
        engine.load(QUrl.fromLocalFile(str(qml_path("FluentSettingsWindow.qml"))))

        assert QQuickStyle.name() == "FluentWinUI3"
        assert engine.rootObjects()

    def test_overlay_qml_loads_with_fluent_style(self, qapp):
        from sonicinput.ui.qml_bridge import FluentOverlayViewModel, qml_path

        QQuickStyle.setStyle("FluentWinUI3")
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty(
            "overlayViewModel", FluentOverlayViewModel()
        )
        engine.load(QUrl.fromLocalFile(str(qml_path("FluentRecordingOverlay.qml"))))

        assert QQuickStyle.name() == "FluentWinUI3"
        assert engine.rootObjects()
