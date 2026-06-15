"""UIEventBridge 模型加载状态反馈测试。

覆盖场景：用户首次按热键时，模型还在加载（lazy load）。
overlay 应该显示 "Loading model..."，加载完成后回到 recording。
"""

from __future__ import annotations

from typing import Any

import pytest

from sonicinput.core.services.events import Events
from sonicinput.core.services.ui_event_bridge import UIEventBridge


class _FakeViewModel:
    def __init__(self) -> None:
        self._state = "idle"


class _FakeOverlay:
    def __init__(self, recording_now: bool = True) -> None:
        self.view_model = _FakeViewModel()
        self.calls: list[str] = []
        self._recording_now = recording_now

        class _StateManager:
            def __init__(self, outer):
                self._outer = outer

            def get_recording_state(self):
                from sonicinput.core.interfaces.state import RecordingState

                return (
                    RecordingState.RECORDING
                    if self._outer._recording_now
                    else RecordingState.IDLE
                )

        self._state_manager = _StateManager(self)

    def show_recording(self) -> None:
        self.calls.append("show_recording")
        self.view_model._state = "recording"

    def show_model_loading(self) -> None:
        self.calls.append("show_model_loading")
        self.view_model._state = "model_loading"

    def show_processing(self) -> None:
        self.calls.append("show_processing")
        self.view_model._state = "processing"

    def hide_recording(self) -> None:
        self.calls.append("hide_recording")
        self.view_model._state = "idle"

    def show_error(self, delay_ms: int = 2000) -> None:
        self.calls.append("show_error")
        self.view_model._state = "error"


class _FakeEvents:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def on(self, event_name: str, callback, priority=None) -> str:
        self.listeners.setdefault(event_name, []).append(callback)
        return f"on:{event_name}:{len(self.listeners[event_name])}"

    def emit(self, event_name: str, data: Any = None) -> None:
        for callback in self.listeners.get(event_name, []):
            callback(data)


def _make_bridge(events: _FakeEvents, overlay: _FakeOverlay) -> UIEventBridge:
    bridge = UIEventBridge(event_service=events)
    bridge.setup_overlay_events(overlay)
    return bridge


def test_model_loading_started_switches_overlay_to_loading_state() -> None:
    overlay = _FakeOverlay()
    overlay.view_model._state = "recording"  # 已经在录音中
    events = _FakeEvents()
    _make_bridge(events, overlay)

    events.emit(Events.MODEL_LOADING_STARTED, {"model_name": "paraformer"})

    assert "show_model_loading" in overlay.calls


def test_model_loading_completed_returns_to_recording_when_still_recording() -> None:
    overlay = _FakeOverlay(recording_now=True)
    overlay.view_model._state = "model_loading"
    events = _FakeEvents()
    _make_bridge(events, overlay)

    events.emit(Events.MODEL_LOADING_COMPLETED, {"model_name": "paraformer"})

    assert overlay.calls[-1] == "show_recording"


def test_model_loading_completed_hides_overlay_when_not_recording() -> None:
    overlay = _FakeOverlay(recording_now=False)
    overlay.view_model._state = "model_loading"
    events = _FakeEvents()
    _make_bridge(events, overlay)

    events.emit(Events.MODEL_LOADING_COMPLETED, {"model_name": "paraformer"})

    assert overlay.calls[-1] == "hide_recording"


def test_model_loading_started_does_not_override_processing_state() -> None:
    """如果 overlay 已经在 processing 状态（用户已停止录音），不应被模型加载事件抢走。"""
    overlay = _FakeOverlay()
    overlay.view_model._state = "processing"
    events = _FakeEvents()
    _make_bridge(events, overlay)

    events.emit(Events.MODEL_LOADING_STARTED, {"model_name": "paraformer"})

    assert "show_model_loading" not in overlay.calls
