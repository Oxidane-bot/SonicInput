from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from sonicinput.ui.settings_window import SettingsWindow


def test_accept_settings_only_closes_when_apply_succeeds():
    calls = {"close": 0}
    fake_window = SimpleNamespace(
        apply_settings=lambda: False,
        close=lambda: calls.__setitem__("close", calls["close"] + 1),
    )

    SettingsWindow.accept_settings(fake_window)

    assert calls["close"] == 0


def test_unload_model_emits_only_after_confirmation(monkeypatch):
    unload_requests = []
    fake_window = SimpleNamespace(
        model_unload_requested=SimpleNamespace(
            emit=lambda: unload_requests.append("emitted")
        )
    )

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    SettingsWindow.unload_model(fake_window)

    assert unload_requests == []
