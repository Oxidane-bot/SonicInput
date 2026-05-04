"""Desktop UI redesign regression tests."""

import pytest


@pytest.mark.gui
class TestFluentSettingsRedesign:
    def test_settings_window_uses_fluent_qml_surface(self, settings_window):
        assert settings_window.root.objectName() == "fluentSettingsWindow"
        assert settings_window.view_model.sectionCount == 6

    def test_settings_selection_switches_qml_stack(self, qtbot, settings_window):
        settings_window.root.setProperty("selectedSection", 3)

        qtbot.waitUntil(
            lambda: settings_window.root.property("selectedSection") == 3,
            timeout=1000,
        )

    def test_settings_qml_contains_full_fluent_navigation(self):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentSettingsWindow.qml").read_text(encoding="utf-8")

        assert 'objectName: "languageCombo"' in qml_source
        assert 'objectName: "hotkeysField"' in qml_source
        assert 'objectName: "transcriptionProviderCombo"' in qml_source
        assert 'objectName: "aiProviderCombo"' in qml_source
        assert 'objectName: "inputMethodCombo"' in qml_source


@pytest.mark.gui
class TestTrayMenuRedesign:
    def test_tray_menu_has_modern_style_and_icons(self, monkeypatch, qtbot):
        from PySide6.QtWidgets import QSystemTrayIcon
        from sonicinput.ui.components.system_tray.tray_widget import TrayWidget

        monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
        tray = TrayWidget()

        assert tray._context_menu is not None
        assert tray._context_menu.objectName() == "sonic_tray_menu"
        assert "background-color" in tray._context_menu.styleSheet()
        assert not tray._menu_actions["recording"].icon().isNull()
        assert not tray._menu_actions["settings"].icon().isNull()

        tray.cleanup()


@pytest.mark.gui
class TestFluentRecordingOverlayRedesign:
    def test_overlay_has_compact_qml_geometry_and_stop_action(self, recording_overlay):
        from sonicinput.ui.qml_bridge import qml_path

        qml_source = qml_path("FluentRecordingOverlay.qml").read_text(encoding="utf-8")

        assert recording_overlay.root.objectName() == "fluentRecordingOverlay"
        assert recording_overlay.root.width() == 252
        assert recording_overlay.root.height() == 52
        assert "id: stopButton" in qml_source
        assert 'ToolTip.text: "Stop Recording"' in qml_source

    def test_overlay_stop_button_emits_stop_request(self, qtbot, recording_overlay):
        with qtbot.waitSignal(recording_overlay.stop_recording_requested, timeout=1000):
            recording_overlay.view_model.requestStop()
