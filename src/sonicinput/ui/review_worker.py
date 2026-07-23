"""Background execution for manual and scheduled lexicon review."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal


class ReviewRunThread(QThread):
    """Run a review service call without blocking the Qt event loop."""

    completed = Signal(dict)

    def __init__(self, run_review: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._run_review = run_review

    def run(self) -> None:
        try:
            raw_result = self._run_review()
            if isinstance(raw_result, dict):
                result = dict(raw_result)
            else:
                result = {
                    "ran": False,
                    "reason": "invalid_review_result",
                    "reviewedRecordCount": 0,
                    "suggestionCount": 0,
                }
        except Exception as exc:
            result = {
                "ran": False,
                "reason": "review_run_failed",
                "error": str(exc),
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }
        self.completed.emit(result)


__all__ = ["ReviewRunThread"]
