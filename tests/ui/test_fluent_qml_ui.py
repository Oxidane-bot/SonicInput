"""Tests for the Fluent QML UI layer."""

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
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

    def test_lexicon_bridge_exposes_entries_export_and_clear(self):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        settings_service = Mock()
        settings_service.get_setting = Mock(
            side_effect=lambda _key, default=None: default
        )
        settings_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "sug-1",
                    "old_form": "拍套曲",
                    "new_form": "PyTorch",
                    "detail": "Repeated correction",
                    "evidence_count": 2,
                    "confidence": 0.86,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        settings_service.decide_review_suggestion = Mock(return_value=True)
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
        settings_service.clear_lexicon_entries = Mock(return_value=True)
        settings_service.remove_lexicon_entry = Mock(return_value=True)
        settings_service.export_lexicon_entries = Mock(
            return_value={
                "success": True,
                "path": "quality_audit/lexicon.json",
                "count": 1,
            }
        )

        view_model = FluentSettingsViewModel(settings_service)
        view_model.refreshLexiconEntries()

        settings_service.list_lexicon_entries.assert_called_once_with()
        assert view_model.reviewSuggestionCount == 1
        assert view_model.reviewSuggestions[0]["oldForm"] == "拍套曲"
        assert view_model.reviewSuggestions[0]["newForm"] == "PyTorch"
        assert view_model.lexiconEntryCount == 1
        assert view_model.lexiconEntries[0]["term"] == "SonicInput"
        assert view_model.lexiconEntries[0]["oldForm"] == "Sonic Input"
        assert view_model.lexiconEntries[0]["confidenceText"] == "82%"

        export_result = view_model.exportLexiconEntries()
        assert export_result["success"] is True
        assert view_model.lexiconExportMessage == (
            "Exported 1 lexicon entries to quality_audit/lexicon.json"
        )

        lexicon_refresh_count = settings_service.list_lexicon_entries.call_count
        assert view_model.removeLexiconEntry("lex-1") is True
        settings_service.remove_lexicon_entry.assert_called_once_with("lex-1")
        assert (
            settings_service.list_lexicon_entries.call_count
            == lexicon_refresh_count + 1
        )

        assert view_model.acceptReviewSuggestion("sug-1") is True
        settings_service.decide_review_suggestion.assert_called_once_with(
            "sug-1", "accepted"
        )

        assert view_model.clearLexiconEntries() is True
        settings_service.clear_lexicon_entries.assert_called_once()

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

    def test_selected_history_delete_uses_selected_record_after_refresh_reorders_list(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        selected = _make_history_record("h-selected", "selected")
        newer = _make_history_record("h-newer", "newer")
        history_service = Mock()
        history_service.get_records_keyset.side_effect = [
            [selected],
            [newer, selected],
            [newer],
        ]
        history_service.get_aggregate_stats.return_value = (2, 5.0, 2)
        history_service.delete_record.return_value = True
        mock_config_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("")
        view_model.openHistoryDetail(0)
        view_model.refreshHistory("")

        assert view_model.selectedHistoryDetail["id"] == "h-selected"
        assert view_model.deleteSelectedHistoryRecord() is True
        history_service.delete_record.assert_called_once_with("h-selected")
        assert view_model.historyDetailVisible is False
        assert [item["id"] for item in view_model.historyRecords] == ["h-newer"]

    def test_history_refresh_closes_detail_when_selected_record_is_not_in_page(
        self, mock_config_service
    ):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        selected = _make_history_record("h-selected", "selected")
        replacement = _make_history_record("h-replacement", "replacement")
        history_service = Mock()
        history_service.get_records_keyset.side_effect = [[selected], [replacement]]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        view_model = FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("")
        view_model.openHistoryDetail(0)
        view_model.refreshHistory("")

        assert view_model.historyDetailVisible is False
        assert view_model.selectedHistoryDetail == {}
        assert view_model.deleteSelectedHistoryRecord() is False

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
        import sonicinput.ui.viewmodels.batch_reprocess as batch_reprocess_module

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

        monkeypatch.setattr(
            batch_reprocess_module, "BatchReprocessingWorker", FakeWorker
        )

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
        import sonicinput.ui.viewmodels.history as history_module

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
                self.finished = Mock()
                started_workers.append(self)

            def start(self):
                self.started = True

        monkeypatch.setattr(history_module, "ReprocessingWorker", FakeWorker)

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
            "lexiconMemoryPage",
            "lexiconEntryList",
        ]:
            assert f'objectName: "{object_name}"' in qml_source

    def test_settings_qml_has_lexicon_memory_page_controls(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        for object_name in [
            "lexiconMemoryPage",
            "lexiconMemoryTitle",
            "lexiconTabBar",
            "lexiconTabStack",
            "reviewUseLexiconMemorySwitch",
            "reviewEnabledSwitch",
            "reviewSuggestionCountLabel",
            "runReviewNowButton",
            "reviewRunProgress",
            "reviewRunMessageLabel",
            "reviewEmptyState",
            "reviewSuggestionList",
            "acceptReviewSuggestionButton",
            "rejectReviewSuggestionButton",
            "ignoreReviewSuggestionButton",
            "lexiconEntryCountLabel",
            "lexiconRefreshButton",
            "exportLexiconButton",
            "lexiconExportMessageLabel",
            "clearLexiconButton",
            "removeLexiconEntryButton",
            "lexiconEntryList",
            "lexiconEmptyState",
        ]:
            assert f'objectName: "{object_name}"' in qml_source

        for declaration in [
            "property int lexiconTabIndex:",
            "function activateSection(index)",
        ]:
            assert declaration in qml_source

        for removed_secondary_page_api in [
            "lexiconMemoryOpen",
            "lexiconMemoryEntryButton",
            "lexiconMemoryBackButton",
            "openLexiconMemory",
            "closeLexiconMemory",
            "back_to_ai_processing",
        ]:
            assert removed_secondary_page_api not in qml_source

        assert 'root.t("lexicon_memory", "Lexicon Memory")' in qml_source
        assert 'root.setValue("review.use_lexicon_memory", checked)' in qml_source
        assert "refreshLexiconEntries()" in qml_source
        assert "exportLexiconEntries()" in qml_source
        assert "clearLexiconEntries()" in qml_source
        assert "runReviewNow()" in qml_source
        assert "BusyIndicator" not in qml_source
        assert 'root.setValue("review.enabled", checked)' in qml_source
        assert "exportReviewDebugReportButton" not in qml_source
        assert "reviewJobsFrame" not in qml_source

    def test_lexicon_memory_is_a_primary_page(self, qapp, mock_config_service):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        mock_config_service.list_review_suggestions = Mock(return_value=[])
        mock_config_service.list_lexicon_entries = Mock(return_value=[])
        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)
        lexicon_page = root.findChild(QObject, "lexiconMemoryPage")
        section_titles = root.property("sectionTitles")
        if hasattr(section_titles, "toVariant"):
            section_titles = section_titles.toVariant()

        assert len(section_titles) == 7
        assert root.property("lexiconTabIndex") == 0
        assert callable(root.activateSection)
        assert lexicon_page is not None

        review_loads_before_entry = (
            mock_config_service.list_review_suggestions.call_count
        )
        entry_loads_before_entry = mock_config_service.list_lexicon_entries.call_count
        root.activateSection(6)
        root.setProperty("lexiconTabIndex", 1)
        qapp.processEvents()

        assert root.property("selectedSection") == 6
        assert root.property("lexiconTabIndex") == 1
        assert lexicon_page.property("visible") is True
        assert (
            mock_config_service.list_review_suggestions.call_count
            > review_loads_before_entry
        )
        assert (
            mock_config_service.list_lexicon_entries.call_count
            > entry_loads_before_entry
        )

        review_loads_after_entry = (
            mock_config_service.list_review_suggestions.call_count
        )
        entry_loads_after_entry = mock_config_service.list_lexicon_entries.call_count
        root.activateSection(6)
        qapp.processEvents()

        assert (
            mock_config_service.list_review_suggestions.call_count
            > review_loads_after_entry
        )
        assert (
            mock_config_service.list_lexicon_entries.call_count
            > entry_loads_after_entry
        )

        root.activateSection(3)
        qapp.processEvents()

        assert root.property("selectedSection") == 3
        assert lexicon_page.property("visible") is False

    def test_lexicon_tabs_have_one_visible_list_without_outer_flickable(
        self, qapp, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        mock_config_service.list_review_suggestions = Mock(
            return_value=[
                {
                    "suggestion_id": "sug-1",
                    "old_form": "拍套曲",
                    "new_form": "PyTorch",
                    "detail": "Repeated correction",
                    "evidence_count": 2,
                    "confidence": 0.86,
                    "created_at": "2026-06-09T03:00:00",
                }
            ]
        )
        mock_config_service.list_lexicon_entries = Mock(
            return_value=[
                {
                    "id": "lex-1",
                    "term": "PyTorch",
                    "old_form": "拍套曲",
                    "evidence_count": 3,
                    "confidence": 0.9,
                    "updated_at": "2026-06-09T03:01:00",
                }
            ]
        )

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)
        root.activateSection(6)
        qapp.processEvents()

        lexicon_page = root.findChild(QObject, "lexiconMemoryPage")
        tab_bar = root.findChild(QObject, "lexiconTabBar")
        tab_stack = root.findChild(QObject, "lexiconTabStack")
        suggestion_list = root.findChild(QObject, "reviewSuggestionList")
        entry_list = root.findChild(QObject, "lexiconEntryList")

        assert lexicon_page.metaObject().indexOfProperty("contentY") == -1
        assert tab_bar.property("currentIndex") == 0
        assert tab_stack.property("currentIndex") == 0
        assert suggestion_list.property("visible") is True
        assert entry_list.property("visible") is False

        root.setProperty("lexiconTabIndex", 1)
        qapp.processEvents()

        assert tab_bar.property("currentIndex") == 1
        assert tab_stack.property("currentIndex") == 1
        assert suggestion_list.property("visible") is False
        assert entry_list.property("visible") is True

    def test_saved_lexicon_remove_preserves_scroll_position(
        self, qapp, qtbot, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        entries = [
            {
                "id": f"lex-{index}",
                "term": f"Term {index}",
                "old_form": f"Old form {index}",
                "evidence_count": 2,
                "confidence": 0.9,
                "updated_at": "2026-06-09T03:01:00",
            }
            for index in range(30)
        ]
        mock_config_service.list_review_suggestions = Mock(return_value=[])
        mock_config_service.list_lexicon_entries = Mock(
            side_effect=lambda: list(entries)
        )

        def remove_entry(entry_id):
            entries[:] = [item for item in entries if item["id"] != entry_id]
            return True

        mock_config_service.remove_lexicon_entry = Mock(side_effect=remove_entry)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)
        root.activateSection(6)
        root.setProperty("lexiconTabIndex", 1)
        qapp.processEvents()

        entry_list = root.findChild(QObject, "lexiconEntryList")
        assert entry_list.property("count") == 30
        assert entry_list.property("contentHeight") > entry_list.property("height")

        previous_content_y = min(
            500.0,
            entry_list.property("contentHeight") - entry_list.property("height") - 1,
        )
        assert previous_content_y > 0
        entry_list.setProperty("contentY", previous_content_y)
        qapp.processEvents()

        assert root.removeLexiconEntry(entry_list, "lex-29") is True
        qtbot.waitUntil(
            lambda: entry_list.property("count") == 29
            and abs(entry_list.property("contentY") - previous_content_y) < 1,
            timeout=1000,
        )

        mock_config_service.remove_lexicon_entry.assert_called_once_with("lex-29")
        assert entry_list.property("contentY") == pytest.approx(
            previous_content_y, abs=1
        )

    def test_lexicon_clear_dialog_does_not_survive_window_reopen(
        self, qapp, qtbot, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        mock_config_service.list_review_suggestions = Mock(return_value=[])
        mock_config_service.list_lexicon_entries = Mock(
            return_value=[
                {
                    "id": "lex-1",
                    "term": "PyTorch",
                    "old_form": "拍套曲",
                    "evidence_count": 2,
                    "confidence": 0.9,
                    "updated_at": "2026-06-09T03:01:00",
                }
            ]
        )

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)
        root.activateSection(6)
        root.setProperty("lexiconTabIndex", 1)
        qapp.processEvents()

        clear_button = root.findChild(QObject, "clearLexiconButton")
        clear_dialog = root.findChild(QObject, "lexiconClearConfirmDialog")
        clear_button.clicked.emit()
        qtbot.waitUntil(lambda: clear_dialog.property("visible"), timeout=1000)

        root.setProperty("visible", False)
        qtbot.waitUntil(lambda: not clear_dialog.property("visible"), timeout=1000)
        root.setProperty("visible", True)
        qapp.processEvents()

        assert root.property("visible") is True
        assert clear_dialog.property("visible") is False

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

        root.activateSection(5)
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

        root.activateSection(5)
        qapp.processEvents()

        history_list = root.findChild(QObject, "historyList")
        empty_state = root.findChild(QObject, "historyEmptyState")

        assert history_list.property("count") == 0
        assert empty_state.property("visible") is True

    def test_settings_qml_reentering_history_refreshes_records(
        self, qapp, mock_config_service
    ):
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        history_service = Mock()
        history_service.get_records_keyset.side_effect = [
            [_make_history_record("h-1", "first visit")],
            [_make_history_record("h-2", "second visit")],
        ]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)

        root.activateSection(5)
        qapp.processEvents()
        assert view_model.historyRecords[0]["id"] == "h-1"

        root.activateSection(3)
        root.activateSection(5)
        qapp.processEvents()

        assert view_model.historyRecords[0]["id"] == "h-2"
        assert history_service.get_records_keyset.call_count == 2

    def test_settings_qml_reactivating_history_refreshes_records(
        self, qapp, mock_config_service
    ):
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        history_service = Mock()
        history_service.get_records_keyset.side_effect = [
            [_make_history_record("h-1", "first activation")],
            [_make_history_record("h-2", "repeated activation")],
        ]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)

        root.activateSection(5)
        root.activateSection(5)
        qapp.processEvents()

        assert view_model.historyRecords[0]["id"] == "h-2"
        assert history_service.get_records_keyset.call_count == 2

    def test_settings_qml_history_append_preserves_scroll_position(
        self, qapp, qtbot, mock_config_service
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        first_page = [
            _make_history_record(f"h-{index}", f"record {index}") for index in range(10)
        ]
        second_page = [
            _make_history_record(f"h-{index}", f"record {index}")
            for index in range(10, 20)
        ]
        history_service = Mock()
        history_service.get_records_keyset.side_effect = [first_page, second_page]
        history_service.get_aggregate_stats.return_value = (20, 50.0, 20)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        view_model._history_page_size = 10
        _engine, root = _load_settings_qml(qapp, view_model)
        root.activateSection(5)
        qapp.processEvents()

        history_list = root.findChild(QObject, "historyList")
        assert history_list.property("count") == 10
        assert history_list.property("contentHeight") > history_list.property("height")

        previous_content_y = history_list.property(
            "contentHeight"
        ) - history_list.property("height")
        assert previous_content_y > 0
        history_list.setProperty("contentY", previous_content_y)

        qtbot.waitUntil(
            lambda: history_list.property("count") == 20
            and not history_list.property("pageAppendInProgress"),
            timeout=1000,
        )

        assert history_service.get_records_keyset.call_count == 2
        assert history_list.property("contentY") == pytest.approx(
            previous_content_y, abs=1
        )
        assert history_list.property("contentY") > 0

    @pytest.mark.parametrize("explicit_action", ["refresh", "enter"])
    def test_settings_qml_explicit_history_search_cancels_pending_debounce(
        self, qapp, mock_config_service, explicit_action
    ):
        from PySide6.QtCore import QObject
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        history_service = Mock()
        history_service.get_records_keyset.return_value = []
        history_service.search_records_keyset.return_value = []
        history_service.get_aggregate_stats.return_value = (0, 0.0, 0)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        _engine, root = _load_settings_qml(qapp, view_model)
        root.activateSection(5)
        qapp.processEvents()

        history_service.search_records_keyset.reset_mock()
        history_service.get_aggregate_stats.reset_mock()
        search_field = root.findChild(QObject, "historySearchField")
        refresh_button = root.findChild(QObject, "historyRefreshButton")
        search_field.setProperty("text", "needle")

        if explicit_action == "refresh":
            refresh_button.clicked.emit()
        else:
            search_field.accepted.emit()
        qapp.processEvents()

        assert history_service.search_records_keyset.call_count == 1
        QTest.qWait(300)
        qapp.processEvents()

        history_service.search_records_keyset.assert_called_once()
        history_service.get_aggregate_stats.assert_called_once_with(query="needle")

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
        root.activateSection(5)
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
        root.activateSection(5)
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
        root.activateSection(5)
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
class TestMainWindowLexiconReviewAutoTimer:
    def test_main_window_starts_lexicon_review_timer(self, qtbot):
        from sonicinput.ui.main_window import MainWindow

        settings_service = Mock()

        window = MainWindow(ui_settings_service=settings_service)
        qtbot.addWidget(window)

        assert hasattr(window, "_review_auto_timer")
        assert hasattr(window, "_on_review_auto_timer")


@pytest.mark.gui
class TestLexiconUiSyntheticFlow:
    def test_existing_lexicon_entries_surface_in_view_model(self, tmp_path):
        import sqlite3

        from sonicinput.core.services.storage import ReviewStorageService
        from sonicinput.core.services.ui_services import UISettingsService
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        db_path = tmp_path / "test_lexicon_ui_flow.db"
        review_storage = ReviewStorageService(db_path)
        review_storage.initialize()
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO local_lexicon_entries (
                    id, term, old_form, source_suggestion_id, evidence_count,
                    confidence, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    "lex-1",
                    "PyTorch",
                    "拍套曲",
                    "test-suggestion",
                    2,
                    0.8,
                    "2026-06-09T02:00:00",
                    "2026-06-09T03:00:00",
                ),
            )
            conn.commit()

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

        view_model.refreshLexiconEntries()

        assert view_model.reviewSuggestionCount == 0
        assert view_model.lexiconEntryCount == 1
        assert view_model.lexiconEntries[0]["term"] == "PyTorch"
        assert view_model.lexiconEntries[0]["oldForm"] == "拍套曲"


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
