"""E2E-style desktop UI flow tests."""

from pathlib import Path

import pytest


@pytest.mark.gui
@pytest.mark.e2e
def test_fluent_settings_and_overlay_hosts_flow(qtbot, mock_config_service):
    from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay
    from sonicinput.ui.fluent_settings_window import FluentSettingsWindow

    settings = FluentSettingsWindow(mock_config_service)
    settings.show()
    qtbot.waitUntil(lambda: settings.isVisible(), timeout=2000)
    settings.view_model.setStartMinimized(True)
    settings.view_model.apply()

    assert mock_config_service.get_setting("ui.start_minimized") is True

    overlay = FluentRecordingOverlay()
    overlay.show_recording()
    qtbot.waitUntil(lambda: overlay.isVisible(), timeout=2000)
    with qtbot.waitSignal(overlay.stop_recording_requested, timeout=1000):
        overlay.view_model.requestStop()
    overlay.hide_recording()
    settings.close()


@pytest.mark.gui
@pytest.mark.e2e
def test_main_window_uses_only_fluent_settings(qapp, monkeypatch, mock_config_service):
    from sonicinput.ui.main_window import MainWindow

    created = []

    class SignalStub:
        def connect(self, callback):
            self.callback = callback

    class FakeFluentSettings:
        model_load_requested = SignalStub()
        model_unload_requested = SignalStub()
        model_test_requested = SignalStub()

        def __init__(self, settings_service, model_service=None):
            created.append((settings_service, model_service))

        def show(self):
            return None

        def raise_(self):
            return None

        def activateWindow(self):
            return None

    def legacy_settings_window_forbidden(*_args, **_kwargs):
        raise AssertionError("legacy SettingsWindow must not be used as fallback")

    monkeypatch.setattr(
        "sonicinput.ui.fluent_settings_window.FluentSettingsWindow",
        FakeFluentSettings,
    )
    monkeypatch.setattr(
        "sonicinput.ui.settings_window.SettingsWindow",
        legacy_settings_window_forbidden,
        raising=False,
    )

    window = MainWindow(
        ui_settings_service=mock_config_service,
        ui_model_service=object(),
    )
    window.show_settings()

    assert len(created) == 1


@pytest.mark.gui
@pytest.mark.e2e
def test_app_creates_only_fluent_recording_overlay():
    source = Path("app.py").read_text(encoding="utf-8")

    assert "FluentRecordingOverlay" in source
    assert "from sonicinput.ui.recording_overlay import RecordingOverlay" not in source
    assert "fluent_overlay_fallback" not in source
