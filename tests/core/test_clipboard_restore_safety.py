"""Safety tests for clipboard format restore filtering and OLE fallback."""

from sonicinput.input.clipboard_input import ClipboardInput, ClipboardOleSnapshot
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


def test_restore_clipboard_prefers_ole_snapshot(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)
    snapshot = ClipboardOleSnapshot(marshaled_data_object=object())
    calls = {"ole": 0, "fallback": 0}

    def _fake_restore_ole(_snapshot):
        calls["ole"] += 1
        return True

    def _fake_restore_all(_formats):
        calls["fallback"] += 1

    monkeypatch.setattr(clipboard, "_restore_ole_snapshot", _fake_restore_ole)
    monkeypatch.setattr(clipboard, "_restore_all_formats", _fake_restore_all)

    clipboard.restore_clipboard(snapshot)

    assert calls["ole"] == 1
    assert calls["fallback"] == 0


def test_restore_clipboard_ole_failure_falls_back_to_formats(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)
    snapshot = ClipboardOleSnapshot(
        marshaled_data_object=object(),
        fallback_formats={13: "hello"},
    )
    fallback_calls = []

    monkeypatch.setattr(clipboard, "_restore_ole_snapshot", lambda _snapshot: False)
    monkeypatch.setattr(
        clipboard,
        "_restore_all_formats",
        lambda formats: fallback_calls.append(formats),
    )

    clipboard.restore_clipboard(snapshot)

    assert len(fallback_calls) == 1
    assert fallback_calls[0] == {13: "hello"}


def test_backup_clipboard_prefers_ole_snapshot_when_available(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)
    monkeypatch.setattr(clipboard, "_backup_all_formats", lambda: {13: "hello"})

    expected = ClipboardOleSnapshot(marshaled_data_object=object(), fallback_formats={})
    monkeypatch.setattr(
        clipboard,
        "_backup_ole_snapshot",
        lambda fallback_formats: ClipboardOleSnapshot(
            marshaled_data_object=expected.marshaled_data_object,
            fallback_formats=dict(fallback_formats),
        ),
    )
    monkeypatch.setattr(clipboard, "_is_elevated", lambda: False)
    monkeypatch.setattr(clipboard_module.pyperclip, "paste", lambda: "hello")

    result = clipboard.backup_clipboard()

    assert isinstance(result, ClipboardOleSnapshot)
    assert result.fallback_formats == {13: "hello"}


def test_backup_clipboard_text_only_returns_text(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)
    monkeypatch.setattr(
        clipboard,
        "_paste_text_from_clipboard_with_retry",
        lambda: "safe text snapshot",
    )
    monkeypatch.setattr(clipboard, "_is_elevated", lambda: False)

    result = clipboard.backup_clipboard_text_only()

    assert result == "safe text snapshot"
    assert clipboard.original_clipboard == "safe text snapshot"


def test_input_via_clipboard_recording_mode_uses_retry_copy(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)
    clipboard.set_recording_mode(True)

    calls = {"copy": 0, "paste": 0}

    def _fake_copy(text):
        calls["copy"] += 1
        return text == "hello world"

    def _fake_send_ctrl_v():
        calls["paste"] += 1

    monkeypatch.setattr(clipboard, "_copy_text_to_clipboard_with_retry", _fake_copy)
    monkeypatch.setattr(clipboard, "send_ctrl_v", _fake_send_ctrl_v)

    assert clipboard.input_via_clipboard("hello world") is True
    assert calls["copy"] == 1
    assert calls["paste"] == 1


def test_input_via_clipboard_recording_mode_copy_failure_returns_false(monkeypatch):
    clipboard = _make_clipboard_input(monkeypatch)
    clipboard.set_recording_mode(True)
    monkeypatch.setattr(
        clipboard, "_copy_text_to_clipboard_with_retry", lambda _text: False
    )
    monkeypatch.setattr(clipboard, "send_ctrl_v", lambda: None)

    assert clipboard.input_via_clipboard("hello world") is False
