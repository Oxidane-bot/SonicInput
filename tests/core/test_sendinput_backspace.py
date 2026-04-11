from ctypes import wintypes
from types import SimpleNamespace

import sonicinput.input.sendinput as sendinput_module
from sonicinput.input.sendinput import KEYEVENTF_KEYUP, SendInputMethod


class _DummyLogger:
    def log_audio_event(self, *_args, **_kwargs):
        return None

    def log_error(self, *_args, **_kwargs):
        return None

    def log_warning(self, *_args, **_kwargs):
        return None


def test_input_via_sendinput_translates_backspace_to_vk_back(monkeypatch):
    monkeypatch.setattr(sendinput_module, "app_logger", _DummyLogger(), raising=False)
    monkeypatch.setattr(sendinput_module.win32gui, "GetForegroundWindow", lambda: 1)

    send_calls = []

    def _fake_send_input(num_events, input_ptr, input_size):
        input_array = input_ptr._obj
        send_calls.append(
            {
                "num_events": num_events,
                "input_size": input_size,
                "events": [
                    (
                        input_array[index].union.ki.wVk,
                        input_array[index].union.ki.wScan,
                        input_array[index].union.ki.dwFlags,
                    )
                    for index in range(num_events)
                ],
            }
        )
        return num_events

    monkeypatch.setattr(
        sendinput_module.ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(SendInput=_fake_send_input)),
        raising=False,
    )

    method = SendInputMethod()

    assert method.input_via_sendinput("\b\b") is True
    assert len(send_calls) == 1
    assert send_calls[0]["num_events"] == 4
    assert send_calls[0]["events"] == [
        (wintypes.WORD(0x08).value, 0, 0),
        (wintypes.WORD(0x08).value, 0, KEYEVENTF_KEYUP),
        (wintypes.WORD(0x08).value, 0, 0),
        (wintypes.WORD(0x08).value, 0, KEYEVENTF_KEYUP),
    ]


def test_sendinput_capability_does_not_emit_foreground_keystrokes(monkeypatch):
    monkeypatch.setattr(sendinput_module, "app_logger", _DummyLogger(), raising=False)
    monkeypatch.setattr(sendinput_module.win32gui, "GetForegroundWindow", lambda: 1)

    send_calls = []

    def _fake_send_input(num_events, input_ptr, input_size):
        send_calls.append((num_events, input_size))
        return num_events

    monkeypatch.setattr(
        sendinput_module.ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(SendInput=_fake_send_input)),
        raising=False,
    )

    method = SendInputMethod()
    monkeypatch.setattr(
        method,
        "input_via_sendinput",
        lambda _text: (_ for _ in ()).throw(AssertionError("unexpected text input")),
    )

    assert method.test_sendinput_capability() is True
    assert send_calls == []
