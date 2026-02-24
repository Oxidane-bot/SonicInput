import threading
from unittest.mock import Mock

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
