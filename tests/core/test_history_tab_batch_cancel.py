from PySide6.QtWidgets import QMessageBox

from sonicinput.ui.settings_tabs.history_tab import HistoryTab


class _FakeWorker:
    def __init__(self):
        self.stop_calls = 0
        self.wait_calls = []
        self.terminate_calls = 0

    def stop(self):
        self.stop_calls += 1

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return True

    def isRunning(self):
        return True

    def terminate(self):
        self.terminate_calls += 1


class _FakeProgressDialog:
    def __init__(self):
        self.closed = False
        self.labels = []
        self.cancel_buttons = []

    def setLabelText(self, text):
        self.labels.append(text)

    def setCancelButton(self, button):
        self.cancel_buttons.append(button)

    def close(self):
        self.closed = True


def test_history_tab_cancel_requests_stop_without_terminate(monkeypatch):
    tab = HistoryTab.__new__(HistoryTab)
    tab.batch_worker = _FakeWorker()
    tab.batch_progress_dialog = _FakeProgressDialog()
    tab.parent_window = None
    tab._batch_cancel_requested = False

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    tab._on_batch_canceled()

    assert tab._batch_cancel_requested is True
    assert tab.batch_worker.stop_calls == 1
    assert tab.batch_worker.terminate_calls == 0
    assert tab.batch_progress_dialog.labels
    assert tab.batch_progress_dialog.cancel_buttons == [None]


def test_history_tab_completed_after_cancel_shows_canceled_message(monkeypatch):
    tab = HistoryTab.__new__(HistoryTab)
    tab.batch_worker = _FakeWorker()
    tab.batch_progress_dialog = _FakeProgressDialog()
    tab.parent_window = None
    tab._batch_cancel_requested = True
    load_history_calls = []
    info_calls = []

    monkeypatch.setattr(tab, "_load_history", lambda: load_history_calls.append(True))
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: info_calls.append((args[1], args[2])),
    )

    tab._on_batch_completed({"total": 3, "success": 1, "skipped": 1, "failed": 1, "errors": []})

    assert load_history_calls == [True]
    assert tab.batch_progress_dialog is None
    assert tab.batch_worker is None
    assert info_calls
    assert "Canceled" in info_calls[0][0]
