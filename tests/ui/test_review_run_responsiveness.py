from __future__ import annotations

from threading import Event, get_ident

import pytest

from sonicinput.ui.main_window import MainWindow
from sonicinput.ui.qml_bridge import FluentSettingsViewModel


class _BlockingReviewService:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.thread_ids: list[int] = []

    def get_setting(self, _key, default=None):
        return default

    def run_review_now(self):
        return self._run_review()

    def run_idle_review_once(self):
        return self._run_review()

    def _run_review(self):
        self.thread_ids.append(get_ident())
        self.entered.set()
        self.release.wait(timeout=2)
        return {
            "ran": True,
            "reason": "completed",
            "jobId": "review-1",
            "reviewedRecordCount": 1,
            "suggestionCount": 1,
        }

    def list_review_suggestions(self, limit=100):
        del limit
        return []

    def list_lexicon_entries(self):
        return []


@pytest.mark.gui
def test_manual_review_runs_outside_gui_thread(qtbot) -> None:
    service = _BlockingReviewService()
    view_model = FluentSettingsViewModel(service)
    gui_thread_id = get_ident()

    try:
        result = view_model.runReviewNow()
        qtbot.waitUntil(service.entered.is_set, timeout=1000)

        assert result["reason"] == "review_started"
        assert len(service.thread_ids) == 1
        assert service.thread_ids[0] != gui_thread_id
        assert view_model.reviewRunBusy is True
    finally:
        service.release.set()
        qtbot.waitUntil(lambda: not view_model.reviewRunBusy, timeout=3000)


@pytest.mark.gui
def test_scheduled_review_runs_outside_gui_thread(qtbot) -> None:
    service = _BlockingReviewService()
    window = MainWindow(ui_settings_service=service)
    qtbot.addWidget(window)
    gui_thread_id = get_ident()

    try:
        window._on_review_auto_timer()
        qtbot.waitUntil(service.entered.is_set, timeout=1000)

        assert len(service.thread_ids) == 1
        assert service.thread_ids[0] != gui_thread_id
        assert window._review_auto_worker is not None
        assert window._review_auto_worker.isRunning()
    finally:
        service.release.set()
        qtbot.waitUntil(
            lambda: window._review_auto_worker is None
            or not window._review_auto_worker.isRunning(),
            timeout=3000,
        )


@pytest.mark.gui
def test_history_cancel_does_not_wait_on_gui_thread() -> None:
    class _RetryWorker:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

        def wait(self, *_args) -> None:
            raise AssertionError("GUI cancellation must not wait for the worker")

    view_model = FluentSettingsViewModel(_BlockingReviewService())
    worker = _RetryWorker()
    view_model._retry_worker = worker
    view_model._history_action_stage = "running"
    view_model._history_action_busy = True

    view_model.cancelHistoryAction()

    assert worker.stopped is True
    assert view_model.historyActionStage == "canceling"
    assert view_model.historyActionBusy is True
