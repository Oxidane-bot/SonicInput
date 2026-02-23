"""Safety tests for clipboard format restore filtering."""

from sonicinput.input.clipboard_input import ClipboardInput
import sonicinput.input.clipboard_input as clipboard_module


class _DummyLogger:
    def log_audio_event(self, *_args, **_kwargs):
        return None

    def log_error(self, *_args, **_kwargs):
        return None


def _make_clipboard_input(monkeypatch) -> ClipboardInput:
    monkeypatch.setattr(clipboard_module, "app_logger", _DummyLogger(), raising=False)
    return ClipboardInput()


def test_can_restore_standard_text_and_dib(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)

    can_unicode, reason_unicode = clipboard._can_restore_format(13, "hello")
    can_dib, reason_dib = clipboard._can_restore_format(8, b"\x00\x01")

    assert can_unicode is True
    assert reason_unicode == "safe_standard"
    assert can_dib is True
    assert reason_dib == "safe_standard"


def test_can_restore_registered_allowlist(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)

    monkeypatch.setattr(
        clipboard_module.win32clipboard,
        "GetClipboardFormatName",
        lambda _fmt: "HTML Format",
    )
    can_restore, reason = clipboard._can_restore_format(49161, b"<html></html>")

    assert can_restore is True
    assert reason.startswith("safe_registered:")


def test_restore_all_formats_skips_unallowlisted_registered_formats(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)

    monkeypatch.setattr(
        clipboard,
        "_sort_formats_by_dependency",
        lambda formats: formats,
        raising=False,
    )
    monkeypatch.setattr(
        clipboard,
        "_open_clipboard_with_retry",
        lambda _hwnd: True,
        raising=False,
    )
    monkeypatch.setattr(
        clipboard_module.win32gui, "GetDesktopWindow", lambda: 12345, raising=False
    )

    monkeypatch.setattr(
        clipboard_module.win32clipboard, "EmptyClipboard", lambda: None, raising=False
    )
    monkeypatch.setattr(
        clipboard_module.win32clipboard, "CloseClipboard", lambda: None, raising=False
    )

    set_calls = []

    def _fake_set_clipboard_data(fmt, data):
        set_calls.append((fmt, data))
        return 1

    monkeypatch.setattr(
        clipboard_module.win32clipboard,
        "SetClipboardData",
        _fake_set_clipboard_data,
        raising=False,
    )

    def _fake_get_clipboard_data(fmt):
        if fmt == 13:
            return "hello"
        if fmt == 8:
            return b"\x00\x01"
        return b"fallback"

    monkeypatch.setattr(
        clipboard_module.win32clipboard,
        "GetClipboardData",
        _fake_get_clipboard_data,
        raising=False,
    )

    def _fake_format_name(fmt):
        if fmt == 49161:
            return "HTML Format"
        if fmt == 50115:
            return "MyApp.InternalClipboardObject"
        return f"Fmt{fmt}"

    monkeypatch.setattr(
        clipboard_module.win32clipboard,
        "GetClipboardFormatName",
        _fake_format_name,
        raising=False,
    )

    clipboard._restore_all_formats(
        {
            13: "hello",
            8: b"\x00\x01",
            49161: b"<p>hi</p>",
            50115: b"\x01\x02\x03",
        }
    )

    called_formats = [fmt for fmt, _ in set_calls]
    assert 13 in called_formats
    assert 8 in called_formats
    assert 49161 in called_formats
    assert 50115 not in called_formats
