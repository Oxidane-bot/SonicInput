import threading
from unittest.mock import Mock

import sonicinput.input.smart_input as smart_input_module
from sonicinput.input.clipboard_input import ClipboardOleSnapshot
from sonicinput.input.smart_input import SmartTextInput


class _FakeThread:
    last_instance = None

    def __init__(self, target, daemon):
        self.target = target
        self.daemon = daemon
        self.started = False
        self.join_called = False
        _FakeThread.last_instance = self

    def start(self):
        self.started = True

    def join(self, timeout=None):
        self.join_called = True

    def is_alive(self):
        return self.started and not self.join_called


def test_stop_recording_mode_schedules_background_restore_without_join(monkeypatch):
    smart_input = SmartTextInput.__new__(SmartTextInput)
    smart_input.config_service = Mock()
    smart_input.config_service.get_setting.return_value = 1.0
    smart_input.clipboard_input = Mock()
    smart_input._recording_mode = True
    smart_input._original_clipboard = {13: "hello"}

    monkeypatch.setattr(threading, "Thread", _FakeThread)

    smart_input.stop_recording_mode()

    assert _FakeThread.last_instance is not None
    assert _FakeThread.last_instance.started is True
    assert _FakeThread.last_instance.join_called is False
    smart_input.clipboard_input.set_recording_mode.assert_called_once_with(False)
    assert smart_input._recording_mode is False
    assert smart_input._original_clipboard == ""


def test_stop_recording_mode_handles_ole_snapshot_clipboard_info(monkeypatch):
    class _ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    class _CaptureLogger:
        def __init__(self):
            self.events = []

        def log_audio_event(self, message, extra):
            self.events.append((message, extra))

        def log_error(self, *_args, **_kwargs):
            return None

    logger = _CaptureLogger()
    smart_input = SmartTextInput.__new__(SmartTextInput)
    smart_input.config_service = Mock()
    smart_input.config_service.get_setting.return_value = 0
    smart_input.clipboard_input = Mock()
    smart_input._recording_mode = True
    smart_input._original_clipboard = ClipboardOleSnapshot(
        marshaled_data_object=object(),
        fallback_formats={13: "hello"},
    )

    monkeypatch.setattr(threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(smart_input_module, "app_logger", logger, raising=False)

    smart_input.stop_recording_mode()

    smart_input.clipboard_input.restore_clipboard.assert_called_once()
    assert any(
        message == "Recording mode stopped, clipboard restored successfully"
        and "ole_snapshot" in extra["clipboard_info"]
        for message, extra in logger.events
    )


def test_do_stop_cancels_pending_restore_thread(monkeypatch):
    smart_input = SmartTextInput.__new__(SmartTextInput)
    smart_input._recording_mode = False
    smart_input._method_failures = {"clipboard": 2}
    smart_input._last_failure_time = {"clipboard": 1.0}
    smart_input._restore_cancel_event = threading.Event()
    smart_input._restore_thread_lock = threading.Lock()
    fake_thread = _FakeThread(target=lambda: None, daemon=False)
    fake_thread.started = True
    smart_input._restore_thread = fake_thread

    assert smart_input._do_stop() is True
    assert fake_thread.join_called is True
    assert smart_input._restore_cancel_event.is_set() is True
    assert smart_input._method_failures == {}
    assert smart_input._last_failure_time == {}


def test_start_recording_mode_uses_text_only_clipboard_backup():
    smart_input = SmartTextInput.__new__(SmartTextInput)
    smart_input.clipboard_input = Mock()
    smart_input._recording_mode = False
    smart_input._original_clipboard = ""
    smart_input.clipboard_input.backup_clipboard_text_only.return_value = "hello"

    smart_input.start_recording_mode()

    smart_input.clipboard_input.backup_clipboard_text_only.assert_called_once_with()
    smart_input.clipboard_input.set_recording_mode.assert_called_once_with(True)
    assert smart_input._recording_mode is True
    assert smart_input._original_clipboard == "hello"


def test_input_text_routes_pure_backspace_to_sendinput_even_when_clipboard_preferred():
    smart_input = SmartTextInput.__new__(SmartTextInput)
    smart_input.preferred_method = "clipboard"
    smart_input.fallback_enabled = True
    smart_input._method_failures = {}
    smart_input._last_failure_time = {}
    smart_input.clipboard_input = Mock()
    smart_input.sendinput_method = Mock()

    smart_input._try_clipboard_method = Mock(return_value=True)
    smart_input._try_sendinput_method = Mock(return_value=True)

    assert smart_input.input_text("\b\b") is True
    smart_input._try_sendinput_method.assert_called_once_with("\b\b")
    smart_input._try_clipboard_method.assert_not_called()
