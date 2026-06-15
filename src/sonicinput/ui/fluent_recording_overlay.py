"""Fluent QML recording overlay host."""

from PySide6.QtCore import QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QWidget

from .qml_bridge import FluentOverlayViewModel, qml_path


class FluentRecordingOverlay(QWidget):
    """Compatibility wrapper exposing the existing overlay public API."""

    stop_recording_requested = Signal()
    show_recording_requested = Signal()
    hide_recording_requested = Signal()
    show_processing_requested = Signal()
    show_completed_requested = Signal(int)
    show_warning_requested = Signal(int)
    show_error_requested = Signal(int)
    show_model_loading_requested = Signal()
    set_status_requested = Signal(str)
    update_audio_level_requested = Signal(float)
    hide_recording_delayed_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view_model = FluentOverlayViewModel()
        self.view_model.stopRecordingRequested.connect(self.stop_recording_requested)
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty(
            "overlayViewModel", self.view_model
        )
        self.engine.rootContext().setContextProperty("overlayHost", self)
        if QQuickStyle.name() != "FluentWinUI3":
            QQuickStyle.setStyle("FluentWinUI3")
        self.engine.load(
            QUrl.fromLocalFile(str(qml_path("FluentRecordingOverlay.qml")))
        )
        roots = self.engine.rootObjects()
        if not roots:
            raise RuntimeError("Failed to load FluentRecordingOverlay.qml")
        self.root = roots[0]
        self.recording_duration = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_recording_time)
        self.config_service = None
        self._state_manager = None
        self.show_recording_requested.connect(self._show_recording_impl)
        self.hide_recording_requested.connect(self._hide_recording_impl)
        self.show_processing_requested.connect(self._show_processing_impl)
        self.show_completed_requested.connect(self._show_completed_impl)
        self.show_warning_requested.connect(self._show_warning_impl)
        self.show_error_requested.connect(self._show_error_impl)
        self.set_status_requested.connect(self._set_status_text_impl)
        self.update_audio_level_requested.connect(self._update_audio_level_impl)
        self.hide_recording_delayed_requested.connect(self._hide_recording_delayed_impl)
        self.show_model_loading_requested.connect(self._show_model_loading_impl)

    def set_config_service(self, config_service) -> None:
        self.config_service = config_service

    def set_state_manager(self, state_manager) -> None:
        self._state_manager = state_manager

    @Slot(int, int)
    def save_position(self, x: int, y: int) -> None:
        if self.config_service is None:
            return
        if not self.config_service.get_setting("ui.overlay_position.auto_save", True):
            return
        x, y = self._clamp_to_screen(int(x), int(y))
        self.config_service.set_setting("ui.overlay_position.mode", "custom")
        self.config_service.set_setting("ui.overlay_position.custom.x", x)
        self.config_service.set_setting("ui.overlay_position.custom.y", y)
        self.config_service.set_setting(
            "ui.overlay_position.last_screen", self._current_screen_info()
        )
        save = getattr(self.config_service, "save_config", None)
        if callable(save):
            save()

    def restore_position(self) -> None:
        if self.config_service is None:
            return
        mode = self.config_service.get_setting("ui.overlay_position.mode", "auto")
        if mode != "custom":
            return
        x = int(self.config_service.get_setting("ui.overlay_position.custom.x", 0))
        y = int(self.config_service.get_setting("ui.overlay_position.custom.y", 0))
        x, y = self._clamp_to_screen(x, y)
        self.root.setX(x)
        self.root.setY(y)

    def _present_overlay(self) -> None:
        """Show the overlay and reassert topmost window state."""
        self.root.setFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.root.setFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.root.show()
        self.root.raise_()

    def _clamp_to_screen(self, x: int, y: int) -> tuple[int, int]:
        screen = self.root.screen()
        if screen is None:
            return x, y
        bounds = screen.availableGeometry()
        max_x = bounds.x() + max(0, bounds.width() - int(self.root.width()))
        max_y = bounds.y() + max(0, bounds.height() - int(self.root.height()))
        return (
            min(max(x, bounds.x()), max_x),
            min(max(y, bounds.y()), max_y),
        )

    def _current_screen_info(self) -> dict[str, object]:
        screen = self.root.screen()
        if screen is None:
            return {"name": "", "geometry": "", "device_pixel_ratio": 1.0}
        geometry = screen.geometry()
        return {
            "name": screen.name(),
            "geometry": (
                f"{geometry.x()},{geometry.y()},{geometry.width()},{geometry.height()}"
            ),
            "device_pixel_ratio": float(screen.devicePixelRatio()),
        }

    @property
    def is_recording(self) -> bool:
        if self._state_manager is None:
            return False
        try:
            from ..core.interfaces.state import RecordingState

            return self._state_manager.get_recording_state() in (
                RecordingState.STARTING,
                RecordingState.RECORDING,
            )
        except Exception:
            return False

    def show_recording(self) -> None:
        self.show_recording_requested.emit()

    def _show_recording_impl(self) -> None:
        self.recording_duration = 0
        self.view_model.showRecording()
        self.restore_position()
        self._present_overlay()
        self._timer.start(1000)

    def hide_recording(self) -> None:
        self.hide_recording_requested.emit()

    def _hide_recording_impl(self) -> None:
        self._timer.stop()
        self.view_model.hide()
        self.root.hide()

    def show_processing(self) -> None:
        self.show_processing_requested.emit()

    def _show_processing_impl(self) -> None:
        self._timer.stop()
        self.view_model.showProcessing()
        self._present_overlay()

    def show_completed(self, delay_ms: int = 500) -> None:
        self.show_completed_requested.emit(delay_ms)

    def _show_completed_impl(self, delay_ms: int = 500) -> None:
        self.view_model.showCompleted()
        self._present_overlay()
        QTimer.singleShot(delay_ms, self.hide_recording)

    def show_warning(self, delay_ms: int = 1500) -> None:
        self.show_warning_requested.emit(delay_ms)

    def _show_warning_impl(self, delay_ms: int = 1500) -> None:
        self.view_model.showWarning()
        self._present_overlay()
        QTimer.singleShot(delay_ms, self.hide_recording)

    def show_error(self, delay_ms: int = 2000) -> None:
        self.show_error_requested.emit(delay_ms)

    def _show_error_impl(self, delay_ms: int = 2000) -> None:
        self.view_model.showError()
        self._present_overlay()
        QTimer.singleShot(delay_ms, self.hide_recording)

    def show_model_loading(self) -> None:
        self.show_model_loading_requested.emit()

    def _show_model_loading_impl(self) -> None:
        self._timer.stop()
        self.view_model.showModelLoading()
        self._present_overlay()

    def set_status_text(self, text: str) -> None:
        self.set_status_requested.emit(text)

    def _set_status_text_impl(self, text: str) -> None:
        lowered = text.lower()
        if "processing" in lowered or "ai" in lowered:
            self._show_processing_impl()
        elif "error" in lowered:
            self._show_error_impl()
        elif "completed" in lowered:
            self._show_completed_impl()
        elif "recording" in lowered:
            self._show_recording_impl()

    def update_audio_level(self, level: float) -> None:
        self.update_audio_level_requested.emit(level)

    def _update_audio_level_impl(self, level: float) -> None:
        self.view_model.updateAudioLevel(level)

    def update_waveform(self, _audio_data) -> None:
        return None

    def start_processing_animation(self) -> None:
        self.show_processing()

    def stop_processing_animation(self) -> None:
        return None

    def hide_recording_delayed(self, delay_ms: int = 1000) -> None:
        self.hide_recording_delayed_requested.emit(delay_ms)

    def _hide_recording_delayed_impl(self, delay_ms: int = 1000) -> None:
        QTimer.singleShot(delay_ms, self.hide_recording)

    def update_recording_time(self) -> None:
        self.recording_duration += 1
        self.view_model.setElapsedSeconds(self.recording_duration)

    def isVisible(self) -> bool:
        return bool(self.root.isVisible())
