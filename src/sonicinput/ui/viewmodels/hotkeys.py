"""快捷键领域 mixin — 规范化、校验与增删改"""

from typing import Any

from PySide6.QtCore import Property, Slot

from .base import SettingsViewModelBase


class HotkeyViewModelMixin(SettingsViewModelBase):
    """快捷键列表的规范化/查重/增删改逻辑。"""

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

    def _get_hotkeys(self) -> list[str]:
        keys = self._get("hotkeys.keys", ["ctrl+alt+space"])
        if isinstance(keys, list):
            result = [str(key).strip() for key in keys if str(key).strip()]
            return result or ["ctrl+alt+space"]
        value = str(keys).strip()
        return [value] if value else ["ctrl+alt+space"]

    def _set_hotkeys(self, keys: list[str]) -> None:
        cleaned = [str(key).strip() for key in keys if str(key).strip()]
        self._set_pending("hotkeys.keys", cleaned or ["ctrl+alt+space"])

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

    # PySide6 存根不接受字符串形式的 QML 类型名(如 "QVariantList"),
    # 但它是合法的运行时 API — 本文件与其余 viewmodel mixin 中的
    # `type: ignore[arg-type]` 注释均为此存根缺陷。
    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def hotkeyList(self) -> list[str]:
        return self._get_hotkeys()

    @Property(int, notify=SettingsViewModelBase.changed)
    def hotkeyCount(self) -> int:
        return len(self._get_hotkeys())

    @Property(str, notify=SettingsViewModelBase.changed)
    def hotkeySummary(self) -> str:
        return ", ".join(self._get_hotkeys())

    @Slot(str, result=str)
    def normalizeHotkey(self, hotkey: str) -> str:
        return self._normalize_hotkey(hotkey)

    @Slot(str, int, result="QVariant")  # type: ignore[arg-type]
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

    @Slot(str, result="QVariant")  # type: ignore[arg-type]
    def addHotkey(self, hotkey: str) -> dict[str, Any]:
        return self._apply_hotkey_change(hotkey, None)

    @Slot(str, int, result="QVariant")  # type: ignore[arg-type]
    def replaceHotkey(self, hotkey: str, index: int) -> dict[str, Any]:
        return self._apply_hotkey_change(hotkey, index)

    @Slot(int, result="QVariant")  # type: ignore[arg-type]
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


__all__ = ["HotkeyViewModelMixin"]
