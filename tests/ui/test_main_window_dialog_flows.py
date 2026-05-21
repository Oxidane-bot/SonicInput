"""Integration tests for MainWindow's dialog flows after the Fluent UI migration.

These are whitebox tests — they reach into `window._settings_window` to emit the
signals that would normally come from the QML side. The goal is to lock in that
`_on_model_load_requested` / `_on_model_test_requested` / `_on_model_unload_requested`
construct `QMessageBox` and `QProgressDialog` with a valid (QWidget|None) parent
and a `str` cancelButtonText.

The `qmessagebox_guard` and `qprogressdialog_guard` fixtures in `conftest.py`
assert PySide6's parent-type contract; if a regression passes `FluentSettingsWindow`
(a QObject) as parent again, these tests fail with a clear message.
"""

from unittest.mock import MagicMock, Mock

import pytest
from PySide6.QtWidgets import QMessageBox, QWidget


def _check_parent(name: str, parent) -> None:
    assert parent is None or isinstance(parent, QWidget), (
        f"{name} parent must be QWidget or None, got {type(parent).__name__}"
    )


def _build_ui_settings_service(mock_config_service):
    """Build the ui_settings_service shape expected by FluentSettingsWindow.

    Mirrors the wiring in `conftest.py::settings_window` fixture but kept inline
    so the test instantiates MainWindow with the real `show_settings()` path.
    """
    svc = MagicMock()
    svc.config_path = mock_config_service.config_path
    svc.config_service = mock_config_service
    svc.get_setting = mock_config_service.get_setting
    svc.set_setting = mock_config_service.set_setting
    svc.get_all_settings = mock_config_service.get_all_settings
    svc.save_config = mock_config_service.save_config
    svc.export_config = mock_config_service.export_config
    svc.import_config = mock_config_service.import_config
    svc.reset_to_defaults = mock_config_service.reset_to_default

    event_service = MagicMock()
    event_service.on = Mock()
    event_service.emit = Mock()

    svc.get_event_service = Mock(return_value=event_service)
    svc.get_config_service = Mock(return_value=mock_config_service)
    svc.get_transcription_service = Mock(return_value=None)
    svc.get_ai_processing_controller = Mock(return_value=None)
    svc.get_launch_at_login_service = Mock(return_value=None)
    svc.get_localization_service = Mock(return_value=None)

    history_service = MagicMock()
    history_service.get_records = Mock(return_value=[])
    history_service.search_records = Mock(return_value=[])
    history_service.get_records_keyset = Mock(return_value=[])
    history_service.search_records_keyset = Mock(return_value=[])
    history_service.get_total_count = Mock(return_value=0)
    history_service.get_aggregate_stats = Mock(return_value=(0, 0.0, 0))
    svc.get_history_service = Mock(return_value=history_service)
    svc.get_default_config = Mock(return_value={})
    return svc


def _build_window(qtbot, mock_config_service, ui_model_service):
    from sonicinput.ui.main_window import MainWindow

    ui_settings_service = _build_ui_settings_service(mock_config_service)
    window = MainWindow(
        ui_settings_service=ui_settings_service,
        ui_model_service=ui_model_service,
    )
    qtbot.addWidget(window)
    window.show_settings()
    qtbot.waitUntil(
        lambda: getattr(window, "_settings_window", None) is not None, timeout=2000
    )
    return window


def _teardown_window(window):
    settings = getattr(window, "_settings_window", None)
    if settings is not None:
        settings.close()
        settings.deleteLater()


@pytest.mark.gui
@pytest.mark.e2e
def test_model_load_failure_routes_through_valid_parent(
    qtbot, mock_config_service, monkeypatch
):
    """load_model returning False triggers QMessageBox.critical — parent must be QWidget|None."""

    # Allow the critical call to land (the autouse guard raises on critical by default).
    # We swap in a recording stub that only checks parent typing via _assert_valid_parent
    # — which is already what the autouse guard does. We just need critical to NOT raise.
    calls = []

    def _critical(*args, **_kwargs):
        _check_parent("QMessageBox.critical", args[0] if args else None)
        calls.append(("critical", args[0] if args else None))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "critical", _critical)

    ui_model_service = MagicMock()
    ui_model_service.load_model.return_value = False
    window = _build_window(qtbot, mock_config_service, ui_model_service)
    try:
        window._settings_window.model_load_requested.emit("paraformer")
        qtbot.wait(100)
        assert calls, "Expected QMessageBox.critical to be invoked on load failure"
        # The autouse guard already asserted parent type; this is a belt-and-braces check.
        parent = calls[0][1]
        assert parent is None or isinstance(parent, QWidget)
    finally:
        _teardown_window(window)


@pytest.mark.gui
@pytest.mark.e2e
def test_model_test_no_engine_shows_warning_with_valid_parent(
    qtbot, mock_config_service, monkeypatch
):
    """When ui_model_service has no whisper engine, a warning dialog is shown."""

    calls = []

    def _warning(*args, **_kwargs):
        _check_parent("QMessageBox.warning", args[0] if args else None)
        calls.append(("warning", args[0] if args else None))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", _warning)

    ui_model_service = MagicMock()
    ui_model_service.get_whisper_engine.return_value = None
    window = _build_window(qtbot, mock_config_service, ui_model_service)
    try:
        window._settings_window.model_test_requested.emit()
        qtbot.wait(100)
        assert calls, "Expected QMessageBox.warning when no whisper engine present"
    finally:
        _teardown_window(window)


@pytest.mark.gui
@pytest.mark.e2e
def test_model_test_with_engine_constructs_valid_progress_dialog(
    qtbot, mock_config_service
):
    """Engine present + model loaded triggers QProgressDialog construction.

    The qprogressdialog_guard autouse fixture validates the constructor signature.
    If parent is not QWidget|None or cancelButtonText is not str, this test fails.
    """
    speech_engine = MagicMock()
    speech_engine.is_model_loaded = True
    speech_engine.model_name = "paraformer"
    speech_engine.device = "cpu"
    speech_engine.transcribe.return_value = {
        "text": "",
        "confidence": 0.0,
        "language": "zh",
    }

    ui_model_service = MagicMock()
    ui_model_service.get_whisper_engine.return_value = speech_engine

    window = _build_window(qtbot, mock_config_service, ui_model_service)
    try:
        window._settings_window.model_test_requested.emit()
        # ModelTestThread is async; we only need the QProgressDialog
        # constructor to have been called (guarded). Wait briefly.
        qtbot.wait(150)
    finally:
        _teardown_window(window)


@pytest.mark.gui
@pytest.mark.e2e
def test_model_unload_calls_service(qtbot, mock_config_service):
    """Unload flow doesn't currently show any dialog, but ensure it doesn't crash."""
    ui_model_service = MagicMock()
    window = _build_window(qtbot, mock_config_service, ui_model_service)
    try:
        window._settings_window.model_unload_requested.emit()
        qtbot.wait(100)
        ui_model_service.unload_model.assert_called_once()
    finally:
        _teardown_window(window)
