"""Tests for the Fluent QML UI layer."""

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from unittest.mock import Mock


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
            "hotkeysField",
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
        assert "width: 252" in qml_source
        assert "height: 52" in qml_source
        assert "anchors.leftMargin: 8" in qml_source
        assert "anchors.rightMargin: 8" in qml_source
        assert qml_source.count("Layout.preferredWidth: 54") == 2

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
