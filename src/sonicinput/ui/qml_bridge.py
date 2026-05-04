"""Python bridge objects for the Fluent QML UI layer."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot


def qml_path(filename: str) -> Path:
    """Return the absolute path to a bundled QML file."""
    return Path(__file__).resolve().parent / "qml" / filename


class FluentSettingsViewModel(QObject):
    """Settings bridge used by Fluent QML surfaces."""

    changed = Signal()
    applied = Signal()

    _SECTIONS = (
        "Application",
        "Hotkeys",
        "Transcription",
        "AI Processing",
        "Audio and Input",
        "History",
    )

    _ZH_CN = {
        "ai_behavior": "AI 行为",
        "ai_processing": "AI 处理",
        "ai_provider": "AI 提供商",
        "always_on_top": "始终置顶",
        "application": "应用",
        "apply": "应用",
        "audio_and_input": "音频和输入",
        "audio_device": "音频设备",
        "auto_detect_terminal": "自动检测终端应用",
        "auto_save_dragged_position": "自动保存拖动位置",
        "batch_reprocess": "批量重新处理",
        "chunk_duration": "分块时长",
        "enable_ai_optimization": "启用 AI 文本优化",
        "enable_fallback": "启用备用输入方法",
        "history": "历史",
        "hotkey_backend": "快捷键后端",
        "hotkeys": "快捷键",
        "language": "语言",
        "launch_at_login": "Windows 登录时启动",
        "load": "加载",
        "load_model_on_startup": "启动时加载模型",
        "log_level": "日志级别",
        "local_sherpa": "本地 sherpa-onnx",
        "max_log_file_size": "最大日志文件大小 (MB)",
        "model": "模型",
        "streaming_mode": "流式模式",
        "no_history_records_loaded": "未加载历史记录",
        "preferred_method": "首选方法",
        "preset_position": "预设位置",
        "provider_credentials": "提供商凭据",
        "recording_overlay": "录音悬浮窗",
        "refresh": "刷新",
        "registered_hotkeys": "已注册快捷键",
        "revert": "还原",
        "search_history": "搜索转写或 AI 文本",
        "show_console_output": "显示控制台输出",
        "show_recording_overlay": "显示录音悬浮窗",
        "show_tray_notifications": "显示托盘通知",
        "start_minimized": "启动后最小化到托盘",
        "streaming_transcription": "流式转写",
        "system_default": "系统默认",
        "test": "测试",
        "text_input": "文本输入",
        "theme_accent": "主题强调色",
        "time_stats": "总记录: 0  总时长: 0.0 秒  成功率: 0%",
        "transcription": "转写",
        "transcription_provider": "转写提供商",
        "unload": "卸载",
    }

    def __init__(self, settings_service, parent: QObject | None = None):
        super().__init__(parent)
        self._settings_service = settings_service
        self._pending: dict[str, Any] = {}

    def _get(self, key: str, default: Any = None) -> Any:
        if key in self._pending:
            return self._pending[key]
        return self._settings_service.get_setting(key, default)

    def _get_all(self) -> dict[str, Any]:
        get_all = getattr(self._settings_service, "get_all_settings", None)
        if callable(get_all):
            data = get_all()
            if isinstance(data, dict):
                return data
        return {}

    def _set_pending(self, key: str, value: Any) -> None:
        if self._pending.get(key) == value:
            return
        self._pending[key] = value
        self.changed.emit()

    @Slot(str, "QVariant", result="QVariant")
    def value(self, key: str, default: Any = None) -> Any:
        return self._get(key, default)

    @Property(str, notify=changed)
    def uiLanguage(self) -> str:
        return str(self._get("ui.language", "auto"))

    @Slot(str, str, result=str)
    def translate(self, token: str, fallback: str) -> str:
        language = str(self._get("ui.language", "auto"))
        if language == "zh-CN":
            return self._ZH_CN.get(token, fallback)
        return fallback

    @Slot(str, "QVariant")
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

    @Slot(str, result="QVariant")
    def listValue(self, key: str) -> list[Any]:
        value = self._get(key, [])
        return value if isinstance(value, list) else []

    @Property(int, constant=True)
    def sectionCount(self) -> int:
        return len(self._SECTIONS)

    @Slot(int, result=str)
    def sectionLabel(self, index: int) -> str:
        if 0 <= index < len(self._SECTIONS):
            return self._SECTIONS[index]
        return ""

    @Property(bool, notify=changed)
    def startMinimized(self) -> bool:
        return bool(self._get("ui.start_minimized", True))

    @Slot(bool)
    def setStartMinimized(self, value: bool) -> None:
        self._set_pending("ui.start_minimized", bool(value))

    @Property(bool, notify=changed)
    def launchAtLogin(self) -> bool:
        return bool(self._get("ui.launch_at_login", False))

    @Slot(bool)
    def setLaunchAtLogin(self, value: bool) -> None:
        self._set_pending("ui.launch_at_login", bool(value))
        if value:
            self._set_pending("ui.start_minimized", True)

    @Property(bool, notify=changed)
    def trayNotifications(self) -> bool:
        return bool(self._get("ui.tray_notifications", True))

    @Slot(bool)
    def setTrayNotifications(self, value: bool) -> None:
        self._set_pending("ui.tray_notifications", bool(value))

    @Property(bool, notify=changed)
    def showOverlay(self) -> bool:
        return bool(self._get("ui.show_overlay", True))

    @Slot(bool)
    def setShowOverlay(self, value: bool) -> None:
        self._set_pending("ui.show_overlay", bool(value))

    @Property(bool, notify=changed)
    def overlayAlwaysOnTop(self) -> bool:
        return bool(self._get("ui.overlay_always_on_top", True))

    @Slot(bool)
    def setOverlayAlwaysOnTop(self, value: bool) -> None:
        self._set_pending("ui.overlay_always_on_top", bool(value))

    @Property(str, notify=changed)
    def themeColor(self) -> str:
        return str(self._get("ui.theme_color", "cyan"))

    @Slot(str)
    def setThemeColor(self, value: str) -> None:
        self._set_pending("ui.theme_color", value)

    @Property(str, notify=changed)
    def logLevel(self) -> str:
        return str(self._get("logging.level", "WARNING"))

    @Slot(str)
    def setLogLevel(self, value: str) -> None:
        self._set_pending("logging.level", value)

    @Property(bool, notify=changed)
    def consoleOutput(self) -> bool:
        return bool(self._get("logging.console_output", False))

    @Slot(bool)
    def setConsoleOutput(self, value: bool) -> None:
        self._set_pending("logging.console_output", bool(value))

    @Property(str, notify=changed)
    def transcriptionProvider(self) -> str:
        return str(self._get("transcription.provider", "local"))

    @Property(str, notify=changed)
    def aiProvider(self) -> str:
        return str(self._get("ai.provider", "openrouter"))

    @Property(bool, notify=changed)
    def aiEnabled(self) -> bool:
        return bool(self._get("ai.enabled", False))

    @Property(str, notify=changed)
    def hotkeySummary(self) -> str:
        keys = self._get("hotkeys.keys", ["f12"])
        if isinstance(keys, list):
            return ", ".join(str(key) for key in keys)
        return str(keys)

    @Slot()
    def reload(self) -> None:
        self._pending.clear()
        self.changed.emit()

    @Slot()
    def apply(self) -> None:
        for key, value in self._pending.items():
            self._settings_service.set_setting(key, value)
        save = getattr(self._settings_service, "save_config", None)
        if callable(save):
            save()
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
