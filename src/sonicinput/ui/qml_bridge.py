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

    _MODIFIER_ALIASES = {
        "control": "ctrl",
        "ctrl": "ctrl",
        "shift": "shift",
        "alt": "alt",
        "option": "alt",
        "win": "win",
        "meta": "win",
        "cmd": "win",
        "command": "win",
    }

    _MODIFIER_ORDER = {
        "ctrl": 0,
        "shift": 1,
        "alt": 2,
        "win": 3,
    }

    _ZH_CN = {
        "ai_behavior": "AI 行为",
        "ai_processing": "AI 处理",
        "ai_provider": "AI 提供商",
        "api_key": "API 密钥",
        "api_key_optional": "API 密钥（可选）",
        "always_on_top": "始终置顶",
        "application": "应用",
        "apply": "应用",
        "audio_and_input": "音频和输入",
        "audio_device": "音频设备",
        "auto_detect_terminal": "自动检测终端应用",
        "auto_save_dragged_position": "自动保存拖动位置",
        "base_url": "基础 URL",
        "batch_reprocess": "批量重新处理",
        "chunk_duration": "分块时长",
        "clipboard_restore_delay_ms": "剪贴板恢复延迟 (ms)",
        "dashscope_default": "留空则使用 DashScope 默认地址",
        "enable_ai_streaming_output": "启用 AI 流式输出",
        "enable_ai_optimization": "启用 AI 文本优化",
        "enable_fallback": "启用备用输入方法",
        "enable_itn": "启用逆文本归一化",
        "enable_sentence_split": "启用句子切分",
        "filter_thinking_tags": "过滤思考标签",
        "history": "历史",
        "hotkey_backend": "快捷键后端",
        "hotkeys": "快捷键",
        "active_hotkeys": "当前快捷键",
        "add_shortcut": "添加快捷键",
        "change": "更改",
        "capture_cancel_hint": "按 Esc 取消",
        "capture_duplicate_hotkey": "该快捷键已存在",
        "capture_failed": "无法开始录制，请重试",
        "capture_idle_hint": "点击添加或更改来录制新的快捷键组合",
        "capture_ready": "准备录制快捷键",
        "capture_timed_out": "录制超时，请重试",
        "capture_unavailable": "当前环境无法录制快捷键",
        "capturing_shortcut": "正在录制快捷键",
        "at_least_one_shortcut_required": "至少需要保留一个快捷键",
        "confirm": "确认",
        "edit_shortcut": "编辑快捷键",
        "edit_hotkeys": "编辑快捷键",
        "language": "语言",
        "launch_at_login": "Windows 登录时启动",
        "leave_empty_default": "留空则使用默认值",
        "load": "加载",
        "load_model_on_startup": "启动时加载模型",
        "log_level": "日志级别",
        "local_sherpa": "本地 sherpa-onnx",
        "max_log_file_size": "最大日志文件大小 (MB)",
        "max_retries": "最大重试次数",
        "model": "模型",
        "model_id": "模型 ID",
        "no_hotkeys": "未配置快捷键",
        "streaming_mode": "流式模式",
        "no_history_records_loaded": "未加载历史记录",
        "openai_compatible": "OpenAI 兼容",
        "one_hotkey_per_line": "每行一个快捷键",
        "press_shortcut": "按下快捷键",
        "preferred_method": "首选方法",
        "preset_position": "预设位置",
        "provider_credentials": "提供商凭据",
        "recording_overlay": "录音悬浮窗",
        "refresh": "刷新",
        "registered_hotkeys": "已注册快捷键",
        "remove": "移除",
        "remove_shortcut": "移除快捷键",
        "revert": "还原",
        "search_history": "搜索转写或 AI 文本",
        "seconds": "秒",
        "selected_hotkey": "已选快捷键",
        "show_console_output": "显示控制台输出",
        "show_recording_overlay": "显示录音悬浮窗",
        "show_tray_notifications": "显示托盘通知",
        "start_minimized": "启动后最小化到托盘",
        "start_ai_after_first_chunk": "首个 ASR 分块完成后启动 AI",
        "streaming_transcription": "流式转写",
        "system_default": "系统默认",
        "system_prompt": "系统提示词",
        "system_prompt_help": "定义 AI 助手的角色；转写文本会作为用户消息发送。",
        "system_prompt_placeholder": "你是专业的转写修正助手。只输出修正后的文本。",
        "test": "测试",
        "text_input": "文本输入",
        "theme_accent": "主题强调色",
        "time_stats": "总记录: 0  总时长: 0.0 秒  成功率: 0%",
        "timeout": "超时",
        "total_duration_zero": "总时长: 0.0 秒",
        "total_records_zero": "总记录: 0",
        "transcription": "转写",
        "transcription_provider": "转写提供商",
        "typing_delay_ms": "输入延迟 (ms)",
        "unload": "卸载",
        "shortcut_count": "已绑定 {count} 个",
        "success_rate_zero": "成功率: 0%",
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

    def _get_hotkeys(self) -> list[str]:
        keys = self._get("hotkeys.keys", ["f12"])
        if isinstance(keys, list):
            result = [str(key).strip() for key in keys if str(key).strip()]
            return result or ["f12"]
        value = str(keys).strip()
        return [value] if value else ["f12"]

    def _set_hotkeys(self, keys: list[str]) -> None:
        cleaned = [str(key).strip() for key in keys if str(key).strip()]
        self._set_pending("hotkeys.keys", cleaned or ["f12"])

    def _normalize_hotkey_token(self, token: str) -> str:
        token = token.strip().lower().replace(" ", "")
        return self._MODIFIER_ALIASES.get(token, token)

    def _normalize_hotkey(self, hotkey: str) -> str:
        if not isinstance(hotkey, str):
            return ""

        parts = [
            part
            for part in (
                self._normalize_hotkey_token(item) for item in hotkey.split("+")
            )
            if part
        ]
        if not parts:
            return ""

        modifiers: list[str] = []
        main_tokens: list[str] = []

        for part in parts[:-1]:
            if part in self._MODIFIER_ORDER and part not in modifiers:
                modifiers.append(part)

        main = parts[-1]
        if main in self._MODIFIER_ORDER:
            return ""

        if len(main) == 1:
            main_tokens.append(main.lower())
        else:
            main_tokens.append(main)

        modifiers.sort(key=lambda item: self._MODIFIER_ORDER.get(item, 99))
        normalized = "+".join([*modifiers, *main_tokens])

        validate = getattr(self._settings_service, "validate_before_save", None)
        if callable(validate):
            is_valid, _error = validate("hotkeys.keys", [normalized])
            if not is_valid:
                return ""

        return normalized

    def _hotkey_result(
        self, success: bool, message: str = "", normalized: str = ""
    ) -> dict[str, Any]:
        return {
            "success": success,
            "message": message,
            "normalized": normalized,
        }

    def _apply_hotkey_change(self, hotkey: str, index: int | None) -> dict[str, Any]:
        normalized = self._normalize_hotkey(hotkey)
        if not normalized:
            return self._hotkey_result(
                False,
                self.translate(
                    "capture_failed", "Unable to start recording, please try again."
                ),
                "",
            )

        keys = self._get_hotkeys()

        if index is not None and (index < 0 or index >= len(keys)):
            return self._hotkey_result(
                False,
                self.translate(
                    "capture_failed", "Unable to start recording, please try again."
                ),
                normalized,
            )

        duplicate_index = next(
            (i for i, key in enumerate(keys) if key == normalized), -1
        )
        if duplicate_index >= 0 and duplicate_index != index:
            return self._hotkey_result(
                False,
                self.translate(
                    "capture_duplicate_hotkey", "That shortcut already exists."
                ),
                normalized,
            )

        if index is None:
            keys.append(normalized)
        else:
            keys[index] = normalized

        self._set_hotkeys(keys)
        self.changed.emit()
        return self._hotkey_result(True, "", normalized)

    def _set_pending(self, key: str, value: Any) -> None:
        if self._pending.get(key) == value:
            return
        self._pending[key] = value
        self.changed.emit()

    @Slot(str, "QVariant", result="QVariant")
    def value(self, key: str, default: Any = None) -> Any:
        return self._get(key, default)

    @Property("QVariantList", notify=changed)
    def hotkeyList(self) -> list[str]:
        return self._get_hotkeys()

    @Property(int, notify=changed)
    def hotkeyCount(self) -> int:
        return len(self._get_hotkeys())

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
        return ", ".join(self._get_hotkeys())

    @Slot(str, result=str)
    def normalizeHotkey(self, hotkey: str) -> str:
        return self._normalize_hotkey(hotkey)

    @Slot(str, int, result="QVariant")
    def validateHotkey(self, hotkey: str, ignore_index: int = -1) -> dict[str, Any]:
        normalized = self._normalize_hotkey(hotkey)
        if not normalized:
            return self._hotkey_result(
                False,
                self.translate(
                    "capture_failed", "Unable to start recording, please try again."
                ),
                "",
            )

        keys = self._get_hotkeys()
        duplicate_index = next(
            (i for i, key in enumerate(keys) if key == normalized), -1
        )
        if duplicate_index >= 0 and duplicate_index != ignore_index:
            return self._hotkey_result(
                False,
                self.translate(
                    "capture_duplicate_hotkey", "That shortcut already exists."
                ),
                normalized,
            )

        return self._hotkey_result(True, "", normalized)

    @Slot(str, result="QVariant")
    def addHotkey(self, hotkey: str) -> dict[str, Any]:
        return self._apply_hotkey_change(hotkey, None)

    @Slot(str, int, result="QVariant")
    def replaceHotkey(self, hotkey: str, index: int) -> dict[str, Any]:
        return self._apply_hotkey_change(hotkey, index)

    @Slot(int, result="QVariant")
    def removeHotkeyAt(self, index: int) -> dict[str, Any]:
        keys = self._get_hotkeys()
        if index < 0 or index >= len(keys):
            return self._hotkey_result(
                False,
                self.translate(
                    "capture_failed", "Unable to start recording, please try again."
                ),
            )
        if len(keys) <= 1:
            return self._hotkey_result(
                False,
                self.translate(
                    "at_least_one_shortcut_required",
                    "At least one shortcut must remain.",
                ),
            )

        del keys[index]
        self._set_hotkeys(keys)
        self.changed.emit()
        return self._hotkey_result(True, "")

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
