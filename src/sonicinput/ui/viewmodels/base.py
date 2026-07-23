"""设置视图模型的共享基础 — 信号、状态契约与通用助手

FluentSettingsViewModel 被按领域拆分为多个 mixin
(hotkeys/review/history/batch_reprocess),它们都继承本基类:
- 共享 Qt 信号(changed/applied/applyFailed)
- 共享状态属性在此声明类型(实际初始化在 FluentSettingsViewModel.__init__)
- 跨 mixin 调用的方法在此声明契约(由对应领域 mixin 覆盖实现)

注意: 本类不是 QObject;PySide6 的元类会在最终组合类
(FluentSettingsViewModel) 上收集整个 MRO 中的 Signal/Slot/Property。
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal, Slot

from .zh_cn import ZH_CN

if TYPE_CHECKING:
    # 仅供类型检查:让 mypy 把 mixin 当作 QObject 子类,
    # 从而正确解析 Signal 描述符(self.changed.emit() 等)。
    # 运行时保持普通类,由最终组合类提供唯一的 QObject 基类。
    from PySide6.QtCore import QObject as _TypingBase
else:
    _TypingBase = object


class SettingsViewModelBase(_TypingBase):
    """Fluent 设置视图模型各领域 mixin 的共享基础。"""

    changed = Signal()
    applied = Signal()
    applyFailed = Signal(str)

    # ---- 共享状态(在 FluentSettingsViewModel.__init__ 中初始化) ----
    _settings_service: Any
    _pending: dict[str, Any]
    _history_service: Any

    # history 状态(review 的 reprocess/revert 也会读写)
    _history_records: list[Any]
    _history_rows: list[dict[str, Any]]
    _history_query: str
    _history_page_size: int
    _history_page_cursor_timestamp: "datetime | None"
    _history_page_cursor_id: "str | None"
    _history_has_more_pages: bool
    _history_total_text: str
    _history_duration_text: str
    _history_success_rate_text: str
    _selected_history_index: int
    _selected_history_record: Any
    _selected_history_detail: dict[str, Any]
    _history_detail_visible: bool
    _retry_worker: Any
    _history_action_busy: bool
    _history_action_message: str
    _history_action_stage: str

    # batch reprocess 状态
    _batch_worker: Any
    _batch_cancel_requested: bool
    _batch_reprocess_visible: bool
    _batch_reprocess_stage: str
    _batch_reprocess_total: int
    _batch_reprocess_cooldown_seconds: int
    _batch_reprocess_progress_value: int
    _batch_reprocess_progress_total: int
    _batch_reprocess_message: str
    _batch_reprocess_result: dict[str, Any]

    # review 状态
    _review_suggestions: list[dict[str, Any]]
    _lexicon_entries: list[dict[str, Any]]
    _review_run_worker: Any
    _review_run_busy: bool
    _review_run_message: str
    _lexicon_export_message: str

    _ZH_CN = ZH_CN

    # ---- 通用助手 ----

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

    def _get_history_service(self) -> Any:
        if self._history_service is None:
            get_history_service = getattr(
                self._settings_service, "get_history_service", None
            )
            if callable(get_history_service):
                self._history_service = get_history_service()
        return self._history_service

    @staticmethod
    def _format_confidence(value: Any) -> str:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.0
        return f"{confidence * 100:.0f}%"

    @Slot(str, str, result=str)
    def translate(self, token: str, fallback: str) -> str:
        language = str(self._get("ui.language", "auto"))
        if language == "zh-CN":
            return self._ZH_CN.get(token, fallback)
        return fallback

    # ---- 跨 mixin 契约(由对应领域 mixin 实现) ----

    def refreshHistory(self, query: str = "") -> None:  # noqa: N802 (Qt 命名)
        raise NotImplementedError

    def _retry_history_record(self, record: Any) -> None:
        raise NotImplementedError

    def _record_to_history_detail(self, record: Any) -> dict[str, Any]:
        raise NotImplementedError


__all__ = ["SettingsViewModelBase"]
