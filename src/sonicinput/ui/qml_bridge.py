"""Python bridge objects for the Fluent QML UI layer.

FluentSettingsViewModel 的领域逻辑(快捷键/审查/历史/批量重处理)
拆分在 viewmodels/ 包的 mixin 中;本文件只保留:
- 通用设置读写(pending -> apply)与分区导航
- 应用级设置 Property(启动/托盘/悬浮窗/主题/日志/提供商)
- FluentOverlayViewModel 与 qml_path
"""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from .viewmodels import (
    BatchReprocessViewModelMixin,
    HistoryViewModelMixin,
    HotkeyViewModelMixin,
    ReviewViewModelMixin,
    SettingsViewModelBase,
)


def qml_path(filename: str) -> Path:
    """Return the absolute path to a bundled QML file."""
    return Path(__file__).resolve().parent / "qml" / filename


class FluentSettingsViewModel(
    HotkeyViewModelMixin,
    ReviewViewModelMixin,
    HistoryViewModelMixin,
    BatchReprocessViewModelMixin,
    QObject,
):
    """Settings bridge used by Fluent QML surfaces.

    PySide6 的元类会收集整个 MRO 中(包括普通 mixin 类)的
    Signal/Slot/Property，组成当前 QML 使用的 API。
    """

    def __init__(self, settings_service, parent: QObject | None = None):
        super().__init__(parent)
        self._settings_service = settings_service
        self._pending = {}
        self._history_service = None
        self._history_records = []
        self._history_rows = []
        self._history_query = ""
        self._history_page_size = 200
        self._history_page_cursor_timestamp = None
        self._history_page_cursor_id = None
        self._history_has_more_pages = True
        self._history_total_text = "Total Records: 0"
        self._history_duration_text = "Total Duration: 0.0s"
        self._history_success_rate_text = "Success Rate: 0%"
        self._selected_history_index = -1
        self._selected_history_record = None
        self._selected_history_detail = {}
        self._history_detail_visible = False
        self._batch_worker = None
        self._batch_cancel_requested = False
        self._batch_reprocess_visible = False
        self._batch_reprocess_stage = "idle"
        self._batch_reprocess_total = 0
        self._batch_reprocess_cooldown_seconds = 0
        self._batch_reprocess_progress_value = 0
        self._batch_reprocess_progress_total = 0
        self._batch_reprocess_message = ""
        self._batch_reprocess_result = {}
        self._retry_worker = None
        self._history_action_busy = False
        self._history_action_message = ""
        self._history_action_stage = "idle"
        self._review_suggestions = []
        self._lexicon_entries = []
        self._review_run_worker = None
        self._review_run_busy = False
        self._review_run_message = ""
        self._lexicon_export_message = ""

    # ---- 通用设置读写 ----

    @Slot(str, "QVariant", result="QVariant")  # type: ignore[arg-type]
    def value(self, key: str, default: Any = None) -> Any:
        return self._get(key, default)

    @Slot(str, "QVariant")  # type: ignore[arg-type]
    def setValue(self, key: str, value: Any) -> None:
        self._set_pending(key, value)

    @Slot(str, result=str)
    def stringValue(self, key: str) -> str:
        value = self._get(key, "")
        return "" if value is None else str(value)

    @Slot(str, result=bool)
    def boolValue(self, key: str) -> bool:
        return bool(self._get(key, False))

    @Slot(str, result=float)
    def numberValue(self, key: str) -> float:
        value = self._get(key, 0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @Slot(str, result="QVariant")  # type: ignore[arg-type]
    def listValue(self, key: str) -> list[Any]:
        value = self._get(key, [])
        return value if isinstance(value, list) else []

    # ---- 应用级设置 Property ----

    @Property(str, notify=SettingsViewModelBase.changed)
    def uiLanguage(self) -> str:
        return str(self._get("ui.language", "auto"))

    @Property(bool, notify=SettingsViewModelBase.changed)
    def startMinimized(self) -> bool:
        return bool(self._get("ui.start_minimized", True))

    @Slot(bool)
    def setStartMinimized(self, value: bool) -> None:
        self._set_pending("ui.start_minimized", bool(value))

    @Property(bool, notify=SettingsViewModelBase.changed)
    def launchAtLogin(self) -> bool:
        return bool(self._get("ui.launch_at_login", False))

    @Slot(bool)
    def setLaunchAtLogin(self, value: bool) -> None:
        self._set_pending("ui.launch_at_login", bool(value))
        if value:
            self._set_pending("ui.start_minimized", True)

    @Property(bool, notify=SettingsViewModelBase.changed)
    def trayNotifications(self) -> bool:
        return bool(self._get("ui.tray_notifications", True))

    @Slot(bool)
    def setTrayNotifications(self, value: bool) -> None:
        self._set_pending("ui.tray_notifications", bool(value))

    @Property(bool, notify=SettingsViewModelBase.changed)
    def showOverlay(self) -> bool:
        return bool(self._get("ui.show_overlay", True))

    @Slot(bool)
    def setShowOverlay(self, value: bool) -> None:
        self._set_pending("ui.show_overlay", bool(value))

    @Property(bool, notify=SettingsViewModelBase.changed)
    def overlayAlwaysOnTop(self) -> bool:
        return bool(self._get("ui.overlay_always_on_top", True))

    @Slot(bool)
    def setOverlayAlwaysOnTop(self, value: bool) -> None:
        self._set_pending("ui.overlay_always_on_top", bool(value))

    @Property(str, notify=SettingsViewModelBase.changed)
    def themeColor(self) -> str:
        return str(self._get("ui.theme_color", "cyan"))

    @Slot(str)
    def setThemeColor(self, value: str) -> None:
        self._set_pending("ui.theme_color", value)

    @Property(str, notify=SettingsViewModelBase.changed)
    def logLevel(self) -> str:
        return str(self._get("logging.level", "WARNING"))

    @Slot(str)
    def setLogLevel(self, value: str) -> None:
        self._set_pending("logging.level", value)

    @Property(bool, notify=SettingsViewModelBase.changed)
    def consoleOutput(self) -> bool:
        return bool(self._get("logging.console_output", False))

    @Slot(bool)
    def setConsoleOutput(self, value: bool) -> None:
        self._set_pending("logging.console_output", bool(value))

    @Property(str, notify=SettingsViewModelBase.changed)
    def transcriptionProvider(self) -> str:
        return str(self._get("transcription.provider", "local"))

    @Property(str, notify=SettingsViewModelBase.changed)
    def aiProvider(self) -> str:
        return str(self._get("ai.provider", "openrouter"))

    @Property(bool, notify=SettingsViewModelBase.changed)
    def aiEnabled(self) -> bool:
        return bool(self._get("ai.enabled", False))

    # ---- 提交/回滚 ----

    @Slot()
    def reload(self) -> None:
        self._pending.clear()
        self.changed.emit()

    @Slot()
    def apply(self) -> None:
        try:
            batch = getattr(self._settings_service, "set_settings_batch", None)
            if callable(batch) and self._pending:
                # 批量提交:让 provider/api_key 等关联校验能看到整批变更
                batch(dict(self._pending))
            else:
                for key, value in self._pending.items():
                    self._settings_service.set_setting(key, value)
        except Exception as e:
            # 配置校验失败(如切到无 key 的 cloud provider)→ 通知 UI
            self.applyFailed.emit(str(e))
            return
        save = getattr(self._settings_service, "save_config", None)
        if callable(save):
            try:
                save()
            except Exception as e:
                self.applyFailed.emit(str(e))
                return
        get_localization = getattr(
            self._settings_service, "get_localization_service", None
        )
        localization_service = (
            get_localization() if callable(get_localization) else None
        )
        apply_language = getattr(localization_service, "apply_language", None)
        if callable(apply_language):
            apply_language()
        self._pending.clear()
        self.applied.emit()
        self.changed.emit()


class FluentOverlayViewModel(QObject):
    """Recording overlay bridge used by Fluent QML surfaces."""

    changed = Signal()
    stopRecordingRequested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._visible = False
        self._status_text = "Ready"
        self._elapsed_text = "00:00"
        self._audio_level = 0.0
        self._state = "idle"

    @Property(bool, notify=changed)
    def visible(self) -> bool:
        return self._visible

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status_text

    @Property(str, notify=changed)
    def elapsedText(self) -> str:
        return self._elapsed_text

    @Property(float, notify=changed)
    def audioLevel(self) -> float:
        return self._audio_level

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    def _set_state(self, state: str, text: str, visible: bool = True) -> None:
        self._state = state
        self._status_text = text
        self._visible = visible
        self.changed.emit()

    @Slot()
    def showRecording(self) -> None:
        self._elapsed_text = "00:00"
        self._audio_level = 0.08
        self._set_state("recording", "Recording", True)

    @Slot()
    def showModelLoading(self) -> None:
        self._set_state("model_loading", "Loading model...", True)

    @Slot()
    def showProcessing(self) -> None:
        self._set_state("processing", "Processing", True)

    @Slot()
    def showCompleted(self) -> None:
        self._set_state("completed", "Completed", True)

    @Slot()
    def showWarning(self) -> None:
        self._set_state("warning", "Warning", True)

    @Slot()
    def showError(self) -> None:
        self._set_state("error", "Error", True)

    @Slot()
    def hide(self) -> None:
        self._set_state("idle", "Ready", False)

    @Slot(float)
    def updateAudioLevel(self, level: float) -> None:
        self._audio_level = min(1.0, max(0.0, float(level)))
        self.changed.emit()

    @Slot(int)
    def setElapsedSeconds(self, seconds: int) -> None:
        minutes = max(0, seconds) // 60
        rest = max(0, seconds) % 60
        self._elapsed_text = f"{minutes:02d}:{rest:02d}"
        self.changed.emit()

    @Slot()
    def requestStop(self) -> None:
        self.stopRecordingRequested.emit()
