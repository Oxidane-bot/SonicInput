import threading
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QThread

from sonicinput.core.services.ui_event_bridge import UIEventBridge


class ThreadRecordingOverlay(QObject):
    def __init__(self):
        super().__init__()
        self.audio_level_threads = []

    def update_audio_level(self, level):
        self.audio_level_threads.append(QThread.currentThread())


@pytest.mark.gui
def test_audio_level_update_is_dispatched_to_gui_thread(qtbot):
    event_service = Mock()
    event_service.on = Mock()
    bridge = UIEventBridge(event_service)
    overlay = ThreadRecordingOverlay()
    bridge.setup_overlay_events(overlay)

    worker = threading.Thread(target=lambda: bridge.handle_audio_level_update(0.5))
    worker.start()
    worker.join(timeout=2.0)

    qtbot.waitUntil(lambda: len(overlay.audio_level_threads) == 1, timeout=2000)
    assert overlay.audio_level_threads[0] == QThread.currentThread()
