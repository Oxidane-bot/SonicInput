from __future__ import annotations

import threading
from queue import Queue

import sonicinput.speech.sherpa_models as sherpa_models
from sonicinput.speech.sherpa_models import SherpaModelManager


def test_progress_dialog_is_only_shown_on_main_thread() -> None:
    original_available = sherpa_models.PYSIDE6_AVAILABLE
    original_instance = sherpa_models.QApplication.instance

    try:
        sherpa_models.PYSIDE6_AVAILABLE = True
        sherpa_models.QApplication.instance = staticmethod(lambda: object())

        results: Queue[bool] = Queue()

        def _worker() -> None:
            results.put(SherpaModelManager._should_show_progress_dialog())

        thread = threading.Thread(target=_worker)
        thread.start()
        thread.join(timeout=5)

        assert results.get(timeout=1) is False
    finally:
        sherpa_models.PYSIDE6_AVAILABLE = original_available
        sherpa_models.QApplication.instance = original_instance
