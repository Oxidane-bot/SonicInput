"""Tests for the Fluent QML UI layer."""

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog
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

    def test_section_model_exposes_six_sections(self, mock_config_service):
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel

        view_model = FluentSettingsViewModel(mock_config_service)

        assert view_model.sectionCount == 6
        assert view_model.sectionLabel(0) == "Application"
        assert view_model.sectionLabel(3) == "AI Processing"

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

    def test_history_detail_refreshes_after_dialog_accepts(
        self, mock_config_service, monkeypatch
    ):
        import sonicinput.ui.qml_bridge as qml_bridge

        record = _make_history_record("h-1", "detail")
        history_service = Mock()
        history_service.get_records_keyset.return_value = [record]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)
        created = []

        class FakeDialog:
            def __init__(self, **kwargs):
                created.append(kwargs)

            def exec(self):
                return QDialog.DialogCode.Accepted

        monkeypatch.setattr(qml_bridge, "HistoryDetailDialog", FakeDialog)

        view_model = qml_bridge.FluentSettingsViewModel(mock_config_service)
        view_model.refreshHistory("")
        view_model.openHistoryDetail(0)

        assert created[0]["record"] is record
        assert history_service.get_records_keyset.call_count == 2

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
        ]:
            assert f'objectName: "{object_name}"' in qml_source

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
        from PySide6.QtCore import QObject, QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel, qml_path

        history_service = Mock()
        history_service.get_records_keyset.return_value = [
            _make_history_record("h-1", "qml record")
        ]
        history_service.get_aggregate_stats.return_value = (1, 2.5, 1)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("settingsViewModel", view_model)
        engine.rootContext().setContextProperty("settingsHost", None)
        engine.load(QUrl.fromLocalFile(str(qml_path("FluentSettingsWindow.qml"))))
        root = engine.rootObjects()[0]

        root.setProperty("selectedSection", 5)
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
        from PySide6.QtCore import QObject, QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
        from sonicinput.ui.qml_bridge import FluentSettingsViewModel, qml_path

        history_service = Mock()
        history_service.get_records_keyset.return_value = []
        history_service.get_aggregate_stats.return_value = (0, 0.0, 0)
        mock_config_service.get_history_service = Mock(return_value=history_service)

        QQuickStyle.setStyle("FluentWinUI3")
        view_model = FluentSettingsViewModel(mock_config_service)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("settingsViewModel", view_model)
        engine.rootContext().setContextProperty("settingsHost", None)
        engine.load(QUrl.fromLocalFile(str(qml_path("FluentSettingsWindow.qml"))))
        root = engine.rootObjects()[0]

        root.setProperty("selectedSection", 5)
        view_model.refreshHistory("")
        qapp.processEvents()

        history_list = root.findChild(QObject, "historyList")
        empty_state = root.findChild(QObject, "historyEmptyState")

        assert history_list.property("count") == 0
        assert empty_state.property("visible") is True


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
