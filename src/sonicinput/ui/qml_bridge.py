"""Python bridge objects for the Fluent QML UI layer."""

from datetime import datetime
from pathlib import Path
from typing import Any
from collections import Counter

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QApplication

from .history_formatters import (
    build_diagnostic_tooltip,
    format_fallback_for_table,
    format_mode_for_table,
    format_transcription_path_for_display,
    format_transcribe_for_table,
    get_ai_status_display,
    get_status_display,
)
from .history_workers import BatchReprocessingWorker, ReprocessingWorker


def qml_path(filename: str) -> Path:
    """Return the absolute path to a bundled QML file."""
    return Path(__file__).resolve().parent / "qml" / filename


class FluentSettingsViewModel(QObject):
    """Settings bridge used by Fluent QML surfaces."""

    changed = Signal()
    applied = Signal()
    applyFailed = Signal(str)

    _SECTIONS = (
        "Application",
        "Hotkeys",
        "Transcription",
        "AI Processing",
        "Audio and Input",
        "History",
        "Local Quality Review",
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
    _REVIEW_SUGGESTION_DISPLAY_LIMIT = 24
    _REVIEW_NON_LEXICON_DISPLAY_LIMIT = 16
    _REVIEW_LEXICON_DISPLAY_LIMIT = 8
    _REVIEW_SOURCE_RECORD_PREVIEW_LIMIT = 2
    _REVIEW_SOURCE_RECORD_PREVIEW_CHARS = 96

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
        "revert_to_raw": "回退到原始转写",
        "chunk_duration": "分块时长",
        "clipboard_restore_delay_ms": "剪贴板恢复延迟 (ms)",
        "dashscope_default": "留空则使用 DashScope 默认地址",
        "audio_file": "音频文件",
        "close": "关闭",
        "copy_to_clipboard": "复制",
        "delete_record": "删除记录",
        "detail": "详情",
        "diagnostics": "诊断",
        "decision_reason": "决策原因",
        "enable_ai_streaming_output": "启用 AI 流式输出",
        "enable_ai_optimization": "启用 AI 文本优化",
        "enable_fallback": "启用备用输入方法",
        "enable_idle_review": "启用自动质量审查",
        "enable_itn": "启用逆文本归一化",
        "enable_sentence_split": "启用句子切分",
        "fallback": "备用输入",
        "fallback_type": "备用类型",
        "fallback_reason": "备用原因",
        "final_text": "最终文本",
        "filter_thinking_tags": "过滤思考标签",
        "history": "历史",
        "hotkey_backend": "快捷键后端",
        "hotkeys": "快捷键",
        "active_hotkeys": "当前快捷键",
        "accept": "接受",
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
        "ignore": "忽略",
        "ignore_once": "仅忽略这次",
        "always_ignore_similar": "总是忽略相似项",
        "review_ignore_scope_hint": "“仅忽略这次”只会收起当前卡片；“总是忽略相似项”会抑制后续相似建议再次进入待审查列表。",
        "language": "语言",
        "launch_at_login": "Windows 登录时启动",
        "leave_empty_default": "留空则使用默认值",
        "load": "加载",
        "load_model_on_startup": "启动时加载模型",
        "log_level": "日志级别",
        "local_sherpa": "本地 sherpa-onnx",
        "max_log_file_size": "最大日志文件大小 (MB)",
        "max_review_records": "每次审查记录数",
        "max_retries": "最大重试次数",
        "duration": "时长",
        "evidence": "证据",
        "mode": "模式",
        "model": "模型",
        "model_id": "模型 ID",
        "no_hotkeys": "未配置快捷键",
        "no_lexicon_entries": "暂无本地词汇记忆",
        "no_review_suggestions": "暂无待审查建议",
        "no_review_suggestions_in_category": "当前“{category}”下暂无待审查建议。",
        "streaming_mode": "流式模式",
        "no_history_records_loaded": "未加载历史记录",
        "openai_compatible": "OpenAI 兼容",
        "one_hotkey_per_line": "每行一个快捷键",
        "press_shortcut": "按下快捷键",
        "preferred_method": "首选方法",
        "preset_position": "预设位置",
        "provider": "提供商",
        "quality_review": "本地质量审查",
        "quality_review_help": "这是本地规则扫描，不调用云端模型；只有你接受的词汇才会进入本地记忆。",
        "provider_credentials": "提供商凭据",
        "recording_overlay": "录音悬浮窗",
        "recording_details": "录音详情",
        "record_id": "记录 ID",
        "refresh": "刷新",
        "registered_hotkeys": "已注册快捷键",
        "remove": "移除",
        "remove_shortcut": "移除快捷键",
        "reject": "拒绝",
        "reprocess_sample": "重新处理样本",
        "review_run_completed": "本地规则审查完成：{records} 条记录，{suggestions} 条建议",
        "review_run_completed_empty": "本地规则审查完成：检查了 {records} 条记录，未发现待处理建议",
        "review_run_skipped": "审查未运行：{reason}",
        "review_categories": "审查类别",
        "review_filter_all_categories": "全部类别",
        "review_filter_show_only": "仅看此类",
        "review_filter_showing": "当前筛选",
        "review_back_to_overview": "返回总览",
        "review_group_expand": "展开",
        "review_group_collapse": "折叠",
        "review_hidden_suffix": "隐藏",
        "review_suggestion_overflow": "当前显示 {shown}/{total} 条待审查建议；系统优先展示高风险问题，其余术语候选已暂时折叠。",
        "review_suggestion_overflow_category": "当前在“{category}”中显示 {shown}/{total} 条待审查建议。",
        "review_suggestions": "审查建议",
        "review_idle_seconds": "自动审查空闲等待时间",
        "review_action_abnormal_repetition_alert": "建议检查 AI 是否卡在循环重复；这类输出通常应回退或重新处理。",
        "review_action_assistant_response_leak_alert": "建议确认 AI 是否变成了助手回复、拒绝语或占位提示；语音清理不应向用户说话。",
        "review_action_bad_ai_output_alert": "建议检查这条记录；若 AI 输出越界，应保留原始转写或重新处理。",
        "review_action_chunk_boundary_repeat_alert": "建议保留为 ASR/chunk 调试样本；若相邻片段重复，优先检查 chunk overlap 与边界去重。",
        "review_action_collapsed_to_fragment_alert": "建议优先检查是否发生极端截断；长口述若只剩一两个碎片词，通常应立即回退或重新处理。",
        "review_action_asr_failure_alert": "建议作为 ASR/fallback 调试样本保留，不会自动改变输入结果。",
        "review_action_fallback_candidate_alert": "建议保留为 fallback 条件调试样本；长录音若最终仍接近空白或噪声，说明回退条件可能还不够细。",
        "review_action_lexicon_candidate": "接受后会加入本地词汇记忆；拒绝或忽略不会影响后续输入。",
        "review_action_low_information_expansion_alert": "建议检查是否为短噪声或填充词被扩写；不会自动回写历史。",
        "review_action_over_compressed_long_input_alert": "建议检查长文本是否被总结或删减；不会自动回写历史。",
        "review_action_over_expanded_short_input_alert": "建议检查短输入是否被扩写成解释或回答；语音清理通常应保持保守。",
        "review_action_prompt_failure_pattern": "这是本地 prompt/validator 调试线索；接受或导出都不会自动修改线上提示词。",
        "review_action_translation_command_leak_alert": "建议确认 AI 是否执行了翻译命令；语音清理不应替用户翻译。",
        "review_action_unexpected_language_shift_alert": "建议确认 AI 是否意外切换了语言；语音清理通常应保留原始语言。",
        "review_action_format_pollution_alert": "建议确认最终输入是否混入 markdown、标签或列表格式。",
        "review_debug_export_help": "可将这类 prompt/validator 失败模式导出为本地调试报告，不会自动改动提示词。",
        "review_debug_export_success": "已导出 {count} 条 prompt/validator 调试建议到 {path}",
        "review_debug_export_failed": "调试报告导出失败：{reason}",
        "review_export_debug_report": "导出调试报告",
        "review_jobs": "最近审查运行",
        "review_job_summary": "{records} 条记录，{suggestions} 条建议",
        "review_category_boundary_violation": "边界越界",
        "review_category_boundary_violation_desc": "AI 没有停留在转写清理边界内，转而回答、翻译、切换语言或输出结构化结果。",
        "review_category_content_distortion": "内容失真",
        "review_category_content_distortion_desc": "AI 对原始内容做了过度压缩、扩写、重复或其他破坏性改动。",
        "review_category_diagnostics": "诊断样本",
        "review_category_diagnostics_desc": "主要用于 ASR 或回退链路诊断，不一定直接表示 AI 清理越界。",
        "review_category_lexicon_learning": "词汇记忆",
        "review_category_lexicon_learning_desc": "用于积累可确认的本地术语记忆，只有接受后才会生效。",
        "review_category_prompt_quality": "提示词问题",
        "review_category_prompt_quality_desc": "汇总近期反复出现的 prompt/validator 失败模式，主要用于本地调试报告，不会自动改动线上提示词。",
        "review_priority_high": "优先处理",
        "review_priority_medium": "值得检查",
        "review_priority_low": "可稍后处理",
        "review_risk_high": "高风险",
        "review_risk_low": "低风险",
        "review_risk_medium": "中风险",
        "review_risk_high_desc": "可能已经影响最终输入质量，建议优先人工检查。",
        "review_risk_low_desc": "主要用于诊断或样本积累，通常不直接改变输入行为。",
        "review_risk_medium_desc": "可能改善后续纠错，但需要用户确认后才会生效。",
        "review_type_abnormal_repetition_alert": "异常重复警报",
        "review_type_assistant_response_leak_alert": "助手回复泄漏警报",
        "review_type_asr_failure_alert": "ASR 失败样本",
        "review_type_bad_ai_output_alert": "AI 越界警报",
        "review_type_chunk_boundary_repeat_alert": "分块边界重复",
        "review_type_collapsed_to_fragment_alert": "极端碎片化压缩",
        "review_type_fallback_candidate_alert": "Fallback 候选样本",
        "review_type_lexicon_candidate": "术语候选",
        "review_type_low_information_expansion_alert": "低信息扩写",
        "review_type_over_compressed_long_input_alert": "长文本压缩警报",
        "review_type_over_expanded_short_input_alert": "短输入扩写警报",
        "review_type_prompt_failure_pattern": "提示词失败模式",
        "review_type_translation_command_leak_alert": "翻译越界警报",
        "review_type_unexpected_language_shift_alert": "语言漂移警报",
        "review_type_format_pollution_alert": "格式污染警报",
        "local_example": "本地示例",
        "local_examples": "本地示例",
        "local_examples_more": "（另 {count} 条）",
        "run_review_now": "立即运行本地审查",
        "source_records": "来源记录",
        "reprocess_of": "重处理来源",
        "revert": "还原",
        "retry": "重试",
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
        "lexicon_memory": "本地词汇记忆",
        "clear_lexicon": "清空词汇记忆",
        "clear_learning_data": "清空学习数据",
        "clear_learning_data_success": "已清空本地学习数据。",
        "clear_learning_data_failed": "清空本地学习数据失败。",
        "export_lexicon": "导出词汇记忆",
        "export_lexicon_success": "已导出 {count} 条词汇记忆到 {path}",
        "export_lexicon_failed": "词汇记忆导出失败：{reason}",
        "open_source_record": "打开来源记录",
        "open_example_record": "打开示例记录",
        "time_stats": "总记录: 0  总时长: 0.0 秒  成功率: 0%",
        "timeout": "超时",
        "time": "时间",
        "total_duration_format": "总时长: {duration:.1f}秒",
        "total_duration_zero": "总时长: 0.0 秒",
        "total_records_format": "总记录: {count}",
        "total_records_zero": "总记录: 0",
        "transcription": "转写",
        "transcription_path": "转写路径",
        "transcription_provider": "转写提供商",
        "transcribe_time": "转写耗时",
        "typing_delay_ms": "输入延迟 (ms)",
        "unload": "卸载",
        "use_lexicon_memory": "使用已接受的词汇记忆",
        "shortcut_count": "已绑定 {count} 个",
        "success_rate_format": "成功率: {rate:.1f}%",
        "success_rate_zero": "成功率: 0%",
    }

    def __init__(self, settings_service, parent: QObject | None = None):
        super().__init__(parent)
        self._settings_service = settings_service
        self._pending: dict[str, Any] = {}
        self._history_service = None
        self._history_records: list[Any] = []
        self._history_rows: list[dict[str, Any]] = []
        self._history_query = ""
        self._history_page_size = 200
        self._history_page_cursor_timestamp: datetime | None = None
        self._history_page_cursor_id: str | None = None
        self._history_has_more_pages = True
        self._history_total_text = "Total Records: 0"
        self._history_duration_text = "Total Duration: 0.0s"
        self._history_success_rate_text = "Success Rate: 0%"
        self._selected_history_index = -1
        self._selected_history_record = None
        self._selected_history_detail: dict[str, Any] = {}
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
        self._batch_reprocess_result: dict[str, Any] = {}
        self._retry_worker = None
        self._history_action_busy = False
        self._history_action_message = ""
        self._history_action_stage = "idle"
        self._review_suggestions: list[dict[str, Any]] = []
        self._review_suggestion_groups: list[dict[str, Any]] = []
        self._lexicon_entries: list[dict[str, Any]] = []
        self._review_jobs: list[dict[str, Any]] = []
        self._review_run_message = ""
        self._review_suggestion_overflow_text = ""
        self._review_category_summaries: list[dict[str, Any]] = []
        self._review_last_run_result: dict[str, Any] = {}
        self._review_selected_category = "all"
        self._review_group_expanded_overrides: dict[str, bool] = {}
        self._review_source_record_cache: dict[str, Any] = {}
        self._lexicon_export_message = ""
        self._lexicon_last_export_path = ""
        self._review_debug_export_message = ""
        self._review_debug_last_export_path = ""
        self._review_learning_data_message = ""
        self._pending_review_reprocess_suggestion_id = ""

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

    def _set_pending(self, key: str, value: Any) -> None:
        if self._pending.get(key) == value:
            return
        self._pending[key] = value
        self.changed.emit()

    def _get_history_service(self):
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

    def _format_review_suggestion(self, item: dict[str, Any]) -> dict[str, Any]:
        suggestion_type = str(item.get("suggestion_type", "") or "")
        risk_level = str(item.get("risk_level", "") or "")
        source_record_ids = item.get("source_record_ids", [])
        if isinstance(source_record_ids, list):
            source_record_text = ", ".join(str(value) for value in source_record_ids)
            source_record_id_list = [
                str(value) for value in source_record_ids if str(value)
            ]
        else:
            source_record_text = str(source_record_ids or "")
            source_record_id_list = [source_record_text] if source_record_text else ""

        if not isinstance(source_record_id_list, list):
            source_record_id_list = (
                [str(source_record_id_list)] if source_record_id_list else []
            )
        source_record_label = self.translate("source_records", "Source Records")
        source_record_preview_text = self._review_source_record_preview_text(
            source_record_id_list
        )
        source_record_open_id = self._first_viewable_source_record_id(
            source_record_id_list
        )
        if source_record_preview_text:
            source_record_label = self._review_source_record_label(
                len(source_record_id_list)
            )
            source_record_text = source_record_preview_text
        primary_source_record_id = (
            source_record_id_list[0] if len(source_record_id_list) == 1 else ""
        )
        primary_source_record = self._get_history_record_by_id(primary_source_record_id)
        can_reprocess_sample = (
            bool(primary_source_record_id) and suggestion_type != "lexicon_candidate"
        )
        can_revert_to_raw = (
            bool(primary_source_record_id)
            and suggestion_type != "lexicon_candidate"
            and primary_source_record is not None
            and bool(getattr(primary_source_record, "transcription_text", "") or "")
            and str(getattr(primary_source_record, "final_text", "") or "")
            != str(getattr(primary_source_record, "transcription_text", "") or "")
        )

        evidence_count = int(item.get("evidence_count", 0) or 0)
        category_key = self._review_category_key(suggestion_type)
        return {
            "id": str(item.get("suggestion_id", "") or ""),
            "type": suggestion_type,
            "typeLabel": self._review_type_label(suggestion_type),
            "category": category_key,
            "categoryLabel": self._review_category_label(category_key),
            "categoryDescription": self._review_category_description(category_key),
            "categoryPriorityLevel": self._review_category_priority_level(category_key),
            "categoryPriorityLabel": self._review_category_priority_label(category_key),
            "title": str(item.get("title", "") or ""),
            "detail": str(item.get("detail", "") or ""),
            "riskLevel": risk_level,
            "riskLabel": self._review_risk_label(risk_level),
            "riskDescription": self._review_risk_description(risk_level),
            "confidenceText": self._format_confidence(item.get("confidence")),
            "evidenceText": self.translate("evidence", "Evidence")
            + f": {evidence_count}",
            "actionHint": self._review_action_hint(suggestion_type),
            "sourceRecordLabel": source_record_label,
            "sourceRecordText": source_record_text,
            "sourceRecordPreviewText": source_record_preview_text,
            "sourceRecordIds": source_record_id_list,
            "sourceRecordOpenId": source_record_open_id,
            "canOpenSourceRecord": bool(source_record_open_id),
            "sourceRecordActionLabel": self._review_source_record_action_label(
                len(source_record_id_list)
            ),
            "primarySourceRecordId": primary_source_record_id,
            "canReprocessSample": can_reprocess_sample,
            "canRevertToRaw": can_revert_to_raw,
            "oldForm": str(item.get("old_form", "") or ""),
            "newForm": str(item.get("new_form", "") or ""),
            "createdAt": str(item.get("created_at", "") or ""),
        }

    def _get_history_record_by_id(self, record_id: str) -> Any:
        normalized = str(record_id or "").strip()
        if not normalized:
            return None
        if normalized in self._review_source_record_cache:
            return self._review_source_record_cache[normalized]
        service = self._get_history_service()
        if not service:
            self._review_source_record_cache[normalized] = None
            return None
        get_record = getattr(service, "get_record_by_id", None)
        if not callable(get_record):
            self._review_source_record_cache[normalized] = None
            return None
        try:
            record = get_record(normalized)
        except Exception:
            record = None
        self._review_source_record_cache[normalized] = record
        return record

    def _review_source_record_label(self, source_count: int) -> str:
        if source_count == 1:
            return self.translate("local_example", "Local Example")
        return self.translate("local_examples", "Local Examples")

    def _review_source_record_preview_text(self, source_record_ids: list[str]) -> str:
        if not source_record_ids:
            return ""

        previews: list[str] = []
        for record_id in source_record_ids:
            preview = self._review_source_record_preview(record_id)
            if preview:
                previews.append(preview)
            if len(previews) >= self._REVIEW_SOURCE_RECORD_PREVIEW_LIMIT:
                break

        if not previews:
            return ""

        preview_text = " • ".join(previews)
        extra_count = max(
            0,
            len(source_record_ids) - self._REVIEW_SOURCE_RECORD_PREVIEW_LIMIT,
        )
        if extra_count > 0:
            preview_text += " " + self.translate(
                "local_examples_more",
                "(+{count} more)",
            ).format(count=extra_count)
        return preview_text

    def _review_source_record_preview(self, record_id: str) -> str:
        record = self._get_history_record_by_id(record_id)
        if record is None:
            return ""

        for attribute in ("final_text", "ai_optimized_text", "transcription_text"):
            preview = self._compact_review_source_text(
                getattr(record, attribute, "") or ""
            )
            if preview:
                return preview
        return ""

    def _compact_review_source_text(self, text: str) -> str:
        compact = " ".join(str(text or "").split())
        if not compact:
            return ""
        if len(compact) <= self._REVIEW_SOURCE_RECORD_PREVIEW_CHARS:
            return compact
        return compact[: self._REVIEW_SOURCE_RECORD_PREVIEW_CHARS - 1].rstrip() + "…"

    def _review_source_record_action_label(self, source_count: int) -> str:
        if source_count <= 1:
            return self.translate("open_source_record", "Open Source Record")
        return self.translate("open_example_record", "Open Example Record")

    def _first_viewable_source_record_id(self, source_record_ids: list[str]) -> str:
        for record_id in source_record_ids:
            if self._get_history_record_by_id(record_id) is not None:
                return record_id
        return ""

    def _review_type_label(self, suggestion_type: str) -> str:
        fallbacks = {
            "abnormal_repetition_alert": "Abnormal Repetition",
            "assistant_response_leak_alert": "Assistant Response Leak",
            "asr_failure_alert": "ASR Failure Sample",
            "bad_ai_output_alert": "AI Boundary Alert",
            "chunk_boundary_repeat_alert": "Chunk Boundary Repeat",
            "collapsed_to_fragment_alert": "Collapsed to Fragment",
            "fallback_candidate_alert": "Fallback Candidate",
            "format_pollution_alert": "Format Pollution Alert",
            "lexicon_candidate": "Lexicon Candidate",
            "low_information_expansion_alert": "Low-Information Expansion",
            "over_compressed_long_input_alert": "Over-Compressed Long Input",
            "over_expanded_short_input_alert": "Over-Expanded Short Input",
            "prompt_failure_pattern": "Prompt Failure Pattern",
            "translation_command_leak_alert": "Translation Command Leak",
            "unexpected_language_shift_alert": "Unexpected Language Shift",
        }
        return self.translate(
            f"review_type_{suggestion_type}",
            fallbacks.get(suggestion_type, suggestion_type),
        )

    @staticmethod
    def _review_category_key(suggestion_type: str) -> str:
        if suggestion_type == "lexicon_candidate":
            return "lexicon_learning"
        if suggestion_type == "prompt_failure_pattern":
            return "prompt_quality"
        if suggestion_type in {
            "asr_failure_alert",
            "chunk_boundary_repeat_alert",
            "fallback_candidate_alert",
        }:
            return "diagnostics"
        if suggestion_type in {
            "assistant_response_leak_alert",
            "bad_ai_output_alert",
            "format_pollution_alert",
            "translation_command_leak_alert",
            "unexpected_language_shift_alert",
        }:
            return "boundary_violation"
        return "content_distortion"

    def _review_category_label(self, category_key: str) -> str:
        fallbacks = {
            "boundary_violation": "Boundary Violation",
            "content_distortion": "Content Distortion",
            "diagnostics": "Diagnostic Sample",
            "lexicon_learning": "Lexicon Learning",
            "prompt_quality": "Prompt Issue",
        }
        return self.translate(
            f"review_category_{category_key}",
            fallbacks.get(category_key, category_key),
        )

    def _review_category_description(self, category_key: str) -> str:
        fallbacks = {
            "boundary_violation": "AI left transcript-cleaning boundaries and instead answered, translated, switched language, or emitted structured output.",
            "content_distortion": "AI over-compressed, over-expanded, repeated, or otherwise distorted the original content.",
            "diagnostics": "Mainly useful for ASR or fallback diagnostics rather than direct AI cleanup boundary violations.",
            "lexicon_learning": "Used to accumulate confirmable local terminology memory; it only takes effect after you accept it.",
            "prompt_quality": "Aggregates recurring prompt or validator failure patterns for local debugging; exporting or accepting it does not change prompts automatically.",
        }
        return self.translate(
            f"review_category_{category_key}_desc",
            fallbacks.get(category_key, ""),
        )

    @staticmethod
    def _review_category_priority_level(category_key: str) -> str:
        if category_key in {"boundary_violation", "content_distortion"}:
            return "high"
        if category_key in {"diagnostics", "prompt_quality"}:
            return "medium"
        return "low"

    def _review_category_priority_label(self, category_key: str) -> str:
        level = self._review_category_priority_level(category_key)
        fallbacks = {
            "high": "Review First",
            "medium": "Worth Checking",
            "low": "Review Later",
        }
        return self.translate(
            f"review_priority_{level}",
            fallbacks.get(level, level),
        )

    def _review_risk_label(self, risk_level: str) -> str:
        fallbacks = {"high": "High Risk", "medium": "Medium Risk", "low": "Low Risk"}
        return self.translate(
            f"review_risk_{risk_level}",
            fallbacks.get(risk_level, risk_level),
        )

    def _review_risk_description(self, risk_level: str) -> str:
        fallbacks = {
            "high": "May already affect final input quality; review this first.",
            "medium": "May improve future cleanup, but only after you confirm it.",
            "low": "Mostly useful for diagnostics or sample collection.",
        }
        return self.translate(
            f"review_risk_{risk_level}_desc",
            fallbacks.get(risk_level, ""),
        )

    def _review_action_hint(self, suggestion_type: str) -> str:
        fallbacks = {
            "abnormal_repetition_alert": "Check whether AI got stuck repeating a segment; this usually should be retried or rolled back.",
            "assistant_response_leak_alert": "Check whether AI turned into an assistant reply, refusal, or placeholder instead of cleaning the transcript.",
            "asr_failure_alert": "Keep as an ASR/fallback debugging sample; it will not change typed output automatically.",
            "bad_ai_output_alert": "Check the record; if AI crossed the boundary, keep the raw transcript or reprocess it.",
            "chunk_boundary_repeat_alert": "Keep this as an ASR/chunk debugging sample; repeated adjacent fragments usually point to chunk overlap or boundary dedup issues.",
            "collapsed_to_fragment_alert": "Check whether a long dictation collapsed into a tiny fragment or stray word; this usually should be rolled back or reprocessed immediately.",
            "fallback_candidate_alert": "Keep this as a fallback-threshold debugging sample; a longer recording stayed near-empty without triggering fallback.",
            "format_pollution_alert": "Check whether markdown, labels, or list formatting leaked into the final input.",
            "lexicon_candidate": "Accepting adds this to local lexicon memory; reject/ignore does not affect future input.",
            "low_information_expansion_alert": "Check whether short noise or filler was expanded; history is not rewritten automatically.",
            "over_compressed_long_input_alert": "Check whether a long dictation was summarized or had important clauses removed.",
            "over_expanded_short_input_alert": "Check whether a short input was expanded into an explanation, answer, or much longer rewrite.",
            "prompt_failure_pattern": "This is a local prompt/validator debugging clue. Accepting or exporting it does not change the live prompt automatically.",
            "translation_command_leak_alert": "Check whether AI executed a dictated translation command instead of preserving the transcript.",
            "unexpected_language_shift_alert": "Check whether AI unexpectedly switched the transcript into a different language.",
        }
        return self.translate(
            f"review_action_{suggestion_type}",
            fallbacks.get(suggestion_type, ""),
        )

    def _format_lexicon_entry(self, item: dict[str, Any]) -> dict[str, Any]:
        evidence_count = int(item.get("evidence_count", 0) or 0)
        return {
            "id": str(item.get("id", "") or ""),
            "term": str(item.get("term", "") or ""),
            "oldForm": str(item.get("old_form", "") or ""),
            "confidenceText": self._format_confidence(item.get("confidence")),
            "evidenceText": self.translate("evidence", "Evidence")
            + f": {evidence_count}",
            "updatedAt": str(item.get("updated_at", "") or ""),
        }

    def _format_review_job(self, item: dict[str, Any]) -> dict[str, Any]:
        reviewed_count = int(item.get("reviewed_count", 0) or 0)
        suggestion_count = int(item.get("suggestion_count", 0) or 0)
        return {
            "id": str(item.get("id", "") or ""),
            "createdAt": str(item.get("created_at", "") or ""),
            "status": str(item.get("status", "") or ""),
            "recordLimit": int(item.get("record_limit", 0) or 0),
            "reviewedRecordCount": reviewed_count,
            "suggestionCount": suggestion_count,
            "summaryText": self.translate(
                "review_job_summary",
                "{records} records, {suggestions} suggestions",
            ).format(records=reviewed_count, suggestions=suggestion_count),
        }

    def _load_review_suggestions(self) -> None:
        self._review_source_record_cache = {}
        list_suggestions = getattr(
            self._settings_service, "list_review_suggestions", None
        )
        if not callable(list_suggestions):
            self._review_suggestions = []
            self._review_suggestion_groups = []
            self._review_suggestion_overflow_text = ""
            self._review_category_summaries = []
            self._review_selected_category = "all"
            return
        try:
            suggestions = list_suggestions(limit=100)
        except Exception:
            suggestions = []
        normalized = [item for item in suggestions if isinstance(item, dict)]
        display_items = self._select_review_suggestion_items(normalized)
        self._review_suggestions = [
            self._format_review_suggestion(item) for item in display_items
        ]
        self._review_category_summaries = self._build_review_category_summaries(
            normalized,
            display_items,
        )
        self._review_suggestion_groups = self._build_review_suggestion_groups(
            display_items,
            self._review_category_summaries,
        )
        self._review_suggestion_overflow_text = self._build_review_overflow_text(
            normalized,
            display_items,
        )

    def _select_review_suggestion_items(
        self, suggestions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if self._review_selected_category == "all":
            return self._limit_review_suggestion_items(suggestions)

        filtered = [
            item
            for item in suggestions
            if self._review_category_key(str(item.get("suggestion_type", "") or ""))
            == self._review_selected_category
        ]
        return filtered[: self._REVIEW_SUGGESTION_DISPLAY_LIMIT]

    def _limit_review_suggestion_items(
        self, suggestions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not suggestions:
            return []

        non_lexicon = [
            item
            for item in suggestions
            if str(item.get("suggestion_type", "") or "") != "lexicon_candidate"
        ]
        lexicon = [
            item
            for item in suggestions
            if str(item.get("suggestion_type", "") or "") == "lexicon_candidate"
        ]

        limited_non_lexicon = non_lexicon[: self._REVIEW_NON_LEXICON_DISPLAY_LIMIT]
        remaining_slots = max(
            0, self._REVIEW_SUGGESTION_DISPLAY_LIMIT - len(limited_non_lexicon)
        )
        limited_lexicon = lexicon[
            : min(self._REVIEW_LEXICON_DISPLAY_LIMIT, remaining_slots)
        ]
        return [*limited_non_lexicon, *limited_lexicon]

    def _build_review_category_summaries(
        self,
        all_items: list[dict[str, Any]],
        shown_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not all_items:
            return []

        total_counts = Counter(
            self._review_category_key(str(item.get("suggestion_type", "") or ""))
            for item in all_items
        )
        shown_counts = Counter(
            self._review_category_key(str(item.get("suggestion_type", "") or ""))
            for item in shown_items
        )
        order = (
            "boundary_violation",
            "content_distortion",
            "prompt_quality",
            "diagnostics",
            "lexicon_learning",
        )
        summaries: list[dict[str, Any]] = []
        for category_key in order:
            total_count = int(total_counts.get(category_key, 0))
            if total_count <= 0:
                continue
            shown_count = int(shown_counts.get(category_key, 0))
            summaries.append(
                {
                    "category": category_key,
                    "categoryLabel": self._review_category_label(category_key),
                    "categoryDescription": self._review_category_description(
                        category_key
                    ),
                    "priorityLevel": self._review_category_priority_level(category_key),
                    "priorityLabel": self._review_category_priority_label(category_key),
                    "totalCount": total_count,
                    "shownCount": shown_count,
                    "hiddenCount": max(0, total_count - shown_count),
                    "isSelected": category_key == self._review_selected_category,
                }
            )
        return summaries

    def _build_review_overflow_text(
        self,
        all_items: list[dict[str, Any]],
        shown_items: list[dict[str, Any]],
    ) -> str:
        if not all_items:
            return ""

        if self._review_selected_category == "all":
            hidden_count = max(0, len(all_items) - len(shown_items))
            if hidden_count <= 0:
                return ""
            return self.translate(
                "review_suggestion_overflow",
                "Showing {shown}/{total} pending suggestions. High-risk issues are prioritized and extra lexicon candidates are temporarily hidden.",
            ).format(shown=len(shown_items), total=len(all_items))

        total_in_category = sum(
            1
            for item in all_items
            if self._review_category_key(str(item.get("suggestion_type", "") or ""))
            == self._review_selected_category
        )
        hidden_count = max(0, total_in_category - len(shown_items))
        if hidden_count <= 0:
            return ""
        return self.translate(
            "review_suggestion_overflow_category",
            "Showing {shown}/{total} pending suggestions in {category}.",
        ).format(
            shown=len(shown_items),
            total=total_in_category,
            category=self.reviewSelectedCategoryLabel,
        )

    def _build_review_suggestion_groups(
        self,
        shown_items: list[dict[str, Any]],
        summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not shown_items or not summaries:
            return []

        group_items: dict[str, list[dict[str, Any]]] = {}
        for item in shown_items:
            category_key = self._review_category_key(
                str(item.get("suggestion_type", "") or "")
            )
            group_items.setdefault(category_key, []).append(
                self._format_review_suggestion(item)
            )

        groups: list[dict[str, Any]] = []
        for summary in summaries:
            category_key = str(summary.get("category", "") or "")
            items = group_items.get(category_key, [])
            if not items:
                continue
            groups.append(
                {
                    "category": category_key,
                    "categoryLabel": summary.get("categoryLabel", ""),
                    "categoryDescription": summary.get("categoryDescription", ""),
                    "priorityLevel": summary.get("priorityLevel", "low"),
                    "priorityLabel": summary.get("priorityLabel", ""),
                    "totalCount": int(summary.get("totalCount", 0) or 0),
                    "shownCount": int(summary.get("shownCount", 0) or 0),
                    "hiddenCount": int(summary.get("hiddenCount", 0) or 0),
                    "isSelected": bool(summary.get("isSelected", False)),
                    "defaultExpanded": self._review_group_default_expanded(
                        category_key,
                        bool(summary.get("isSelected", False)),
                    ),
                    "isExpanded": self._review_group_expanded(
                        category_key,
                        bool(summary.get("isSelected", False)),
                    ),
                    "items": items,
                }
            )
        return groups

    @staticmethod
    def _review_group_default_expanded(
        category_key: str,
        is_selected: bool,
    ) -> bool:
        if is_selected:
            return True
        return category_key in {"boundary_violation", "content_distortion"}

    def _review_group_expanded(
        self,
        category_key: str,
        is_selected: bool,
    ) -> bool:
        if category_key in self._review_group_expanded_overrides:
            return bool(self._review_group_expanded_overrides[category_key])
        return self._review_group_default_expanded(category_key, is_selected)

    def _load_lexicon_entries(self) -> None:
        list_entries = getattr(self._settings_service, "list_lexicon_entries", None)
        if not callable(list_entries):
            self._lexicon_entries = []
            return
        try:
            entries = list_entries(limit=200)
        except Exception:
            entries = []
        self._lexicon_entries = [
            self._format_lexicon_entry(item)
            for item in entries
            if isinstance(item, dict)
        ]

    def _load_review_jobs(self) -> None:
        list_jobs = getattr(self._settings_service, "list_review_jobs", None)
        if not callable(list_jobs):
            self._review_jobs = []
            return
        try:
            jobs = list_jobs(limit=20)
        except Exception:
            jobs = []
        self._review_jobs = [
            self._format_review_job(item) for item in jobs if isinstance(item, dict)
        ]

    def _decide_review_suggestion(self, suggestion_id: str, decision: str) -> bool:
        suggestion_id = str(suggestion_id or "").strip()
        if not suggestion_id:
            return False

        decide = getattr(self._settings_service, "decide_review_suggestion", None)
        if not callable(decide):
            return False

        try:
            success = bool(decide(suggestion_id, decision))
        except Exception:
            success = False

        if success:
            self.refreshReviewSuggestions()
        return success

    def _format_review_run_message(self, result: dict[str, Any]) -> str:
        if result.get("ran"):
            records = int(result.get("reviewedRecordCount", 0) or 0)
            suggestions = int(result.get("suggestionCount", 0) or 0)
            if suggestions <= 0:
                return self.translate(
                    "review_run_completed_empty",
                    "Local rule review completed: checked {records} records, no suggestions",
                ).format(records=records)
            return self.translate(
                "review_run_completed",
                "Local rule review completed: {records} records, {suggestions} suggestions",
            ).format(
                records=records,
                suggestions=suggestions,
            )
        return self.translate(
            "review_run_skipped",
            "Review did not run: {reason}",
        ).format(reason=self._review_run_reason_text(result))

    def _review_run_reason_text(self, result: dict[str, Any]) -> str:
        reason = str(result.get("reason", "unknown") or "unknown")
        return {
            "review_disabled": self.translate("review_disabled", "Review is disabled"),
            "review_scheduler_unavailable": self.translate(
                "review_scheduler_unavailable", "Review scheduler unavailable"
            ),
            "review_run_failed": self.translate(
                "review_run_failed", "Review failed to run"
            ),
            "not_idle_long_enough": self.translate(
                "not_idle_long_enough", "Not idle long enough"
            ),
            "min_interval_not_reached": self.translate(
                "min_interval_not_reached", "Minimum interval not reached"
            ),
            "session_budget_exhausted": self.translate(
                "session_budget_exhausted", "Session review budget exhausted"
            ),
        }.get(reason, reason)

    def _set_history_stats(
        self, total_count: int, total_duration: float, success_count: int
    ) -> None:
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0.0
        self._history_total_text = self.translate(
            "total_records_format", "Total Records: {count}"
        ).format(count=total_count)
        self._history_duration_text = self.translate(
            "total_duration_format", "Total Duration: {duration:.1f}s"
        ).format(duration=total_duration)
        self._history_success_rate_text = self.translate(
            "success_rate_format", "Success Rate: {rate:.1f}%"
        ).format(rate=success_rate)

    def _update_history_stats(self) -> None:
        service = self._get_history_service()
        if not service:
            self._set_history_stats(0, 0.0, 0)
            return

        try:
            query = self._history_query or None
            total_count, total_duration, success_count = service.get_aggregate_stats(
                query=query
            )
            self._set_history_stats(
                int(total_count),
                float(total_duration),
                int(success_count),
            )
        except Exception:
            self._set_history_stats(0, 0.0, 0)

    @staticmethod
    def _history_status_display(record: Any) -> str:
        return get_ai_status_display(record)

    @staticmethod
    def _history_primary_text(record: Any) -> str:
        final_text = getattr(record, "final_text", "") or ""
        if final_text:
            return final_text
        ai_text = getattr(record, "ai_optimized_text", "") or ""
        if getattr(record, "ai_status", "") == "success" and ai_text:
            return ai_text
        return getattr(record, "transcription_text", "") or ""

    def _record_to_history_row(self, record: Any) -> dict[str, Any]:
        timestamp = getattr(record, "timestamp", None)
        if hasattr(timestamp, "strftime"):
            display_time = timestamp.strftime("%m-%d %H:%M")
            full_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        else:
            display_time = ""
            full_time = ""

        duration = float(getattr(record, "duration", 0.0) or 0.0)
        transcription_text = getattr(record, "transcription_text", "") or ""
        primary_text = self._history_primary_text(record)
        return {
            "id": getattr(record, "id", ""),
            "displayTime": display_time,
            "fullTime": full_time,
            "durationText": f"{duration:.1f}s",
            "transcriptionText": transcription_text,
            "primaryText": primary_text,
            "statusText": self._history_status_display(record),
            "aiStatus": getattr(record, "ai_status", "") or "",
            "tooltip": build_diagnostic_tooltip(record),
        }

    def _record_to_history_detail(self, record: Any) -> dict[str, Any]:
        row = self._record_to_history_row(record)
        ai_text = getattr(record, "ai_optimized_text", "") or ""
        transcription_error = getattr(record, "transcription_error", None) or ""
        ai_error = getattr(record, "ai_error", None) or ""
        reprocess_parent_id = getattr(record, "reprocess_parent_id", None) or ""
        return {
            **row,
            "audioPath": getattr(record, "audio_file_path", "") or "N/A",
            "reprocessParentId": reprocess_parent_id or "N/A",
            "transcriptionProvider": getattr(record, "transcription_provider", "")
            or "N/A",
            "transcriptionStatusText": get_status_display(
                str(getattr(record, "transcription_status", "") or "")
            ),
            "streamingMode": format_mode_for_table(record),
            "transcriptionPath": format_transcription_path_for_display(record),
            "transcriptionDecisionReason": getattr(
                record, "transcription_decision_reason", None
            )
            or "N/A",
            "transcribeTime": format_transcribe_for_table(record),
            "fallbackUsed": format_fallback_for_table(record),
            "fallbackType": getattr(record, "fallback_type", None) or "none",
            "fallbackReason": getattr(record, "fallback_reason", None) or "None",
            "transcriptionError": transcription_error,
            "aiOptimizedText": ai_text,
            "aiProvider": getattr(record, "ai_provider", None) or "N/A",
            "aiError": ai_error,
            "diagnosticsText": "Captured"
            if getattr(record, "diagnostics_collected", False)
            else "Legacy defaults",
        }

    def _clear_history_detail(self) -> None:
        self._selected_history_index = -1
        self._selected_history_record = None
        self._selected_history_detail = {}
        self._history_detail_visible = False

    def _load_history_page(self, append: bool) -> None:
        service = self._get_history_service()
        if not service:
            if not append:
                self._history_records = []
                self._history_rows = []
                self._set_history_stats(0, 0.0, 0)
                self.changed.emit()
            return

        query = self._history_query
        if query:
            page_records = service.search_records_keyset(
                query=query,
                limit=self._history_page_size,
                cursor_timestamp=self._history_page_cursor_timestamp,
                cursor_id=self._history_page_cursor_id,
            )
        else:
            page_records = service.get_records_keyset(
                limit=self._history_page_size,
                cursor_timestamp=self._history_page_cursor_timestamp,
                cursor_id=self._history_page_cursor_id,
            )

        if not page_records:
            self._history_has_more_pages = False
            if not append:
                self._history_records = []
                self._history_rows = []
            return

        if append:
            self._history_records.extend(page_records)
            self._history_rows.extend(
                self._record_to_history_row(record) for record in page_records
            )
        else:
            self._history_records = list(page_records)
            self._history_rows = [
                self._record_to_history_row(record) for record in page_records
            ]

        last_record = page_records[-1]
        self._history_page_cursor_timestamp = getattr(last_record, "timestamp", None)
        self._history_page_cursor_id = getattr(last_record, "id", None)
        self._history_has_more_pages = len(page_records) >= self._history_page_size

    @Slot(str, "QVariant", result="QVariant")
    def value(self, key: str, default: Any = None) -> Any:
        return self._get(key, default)

    @Property("QVariantList", notify=changed)
    def hotkeyList(self) -> list[str]:
        return self._get_hotkeys()

    @Property("QVariantList", notify=changed)
    def historyRecords(self) -> list[dict[str, Any]]:
        return self._history_rows

    @Property("QVariantList", notify=changed)
    def reviewSuggestions(self) -> list[dict[str, Any]]:
        return self._review_suggestions

    @Property("QVariantList", notify=changed)
    def reviewSuggestionGroups(self) -> list[dict[str, Any]]:
        return self._review_suggestion_groups

    @Property("QVariantList", notify=changed)
    def reviewCategorySummaries(self) -> list[dict[str, Any]]:
        return self._review_category_summaries

    @Property(str, notify=changed)
    def reviewSelectedCategory(self) -> str:
        return self._review_selected_category

    @Property(str, notify=changed)
    def reviewSelectedCategoryLabel(self) -> str:
        if self._review_selected_category == "all":
            return self.translate(
                "review_filter_all_categories",
                "All Categories",
            )
        return self._review_category_label(self._review_selected_category)

    @Property(bool, notify=changed)
    def reviewCategoryFilterActive(self) -> bool:
        return self._review_selected_category != "all"

    @Property("QVariantList", notify=changed)
    def lexiconEntries(self) -> list[dict[str, Any]]:
        return self._lexicon_entries

    @Property("QVariantList", notify=changed)
    def reviewJobs(self) -> list[dict[str, Any]]:
        return self._review_jobs

    @Property(int, notify=changed)
    def reviewSuggestionCount(self) -> int:
        return len(self._review_suggestions)

    @Property(str, notify=changed)
    def reviewEmptyStateText(self) -> str:
        if self._review_selected_category != "all":
            return self.translate(
                "no_review_suggestions_in_category",
                "No pending review suggestions in {category}.",
            ).format(category=self.reviewSelectedCategoryLabel)
        return self.translate(
            "no_review_suggestions",
            "No pending review suggestions",
        )

    @Property(str, notify=changed)
    def reviewIgnoreScopeHint(self) -> str:
        return self.translate(
            "review_ignore_scope_hint",
            "Ignore Once dismisses only this card. Always Ignore Similar suppresses future similar suggestions.",
        )

    @Property(str, notify=changed)
    def reviewSuggestionOverflowText(self) -> str:
        return self._review_suggestion_overflow_text

    @Property(int, notify=changed)
    def lexiconEntryCount(self) -> int:
        return len(self._lexicon_entries)

    @Property(str, notify=changed)
    def lexiconExportMessage(self) -> str:
        return self._lexicon_export_message

    @Property(str, notify=changed)
    def reviewLearningDataMessage(self) -> str:
        return self._review_learning_data_message

    @Property(str, notify=changed)
    def lexiconLastExportPath(self) -> str:
        return self._lexicon_last_export_path

    @Property(str, notify=changed)
    def reviewDebugExportMessage(self) -> str:
        return self._review_debug_export_message

    @Property(str, notify=changed)
    def reviewDebugLastExportPath(self) -> str:
        return self._review_debug_last_export_path

    @Property(int, notify=changed)
    def reviewJobCount(self) -> int:
        return len(self._review_jobs)

    @Property(str, notify=changed)
    def reviewRunMessage(self) -> str:
        return self._review_run_message

    @Property("QVariantMap", notify=changed)
    def reviewLastRunResult(self) -> dict[str, Any]:
        return self._review_last_run_result

    @Property(str, notify=changed)
    def historyTotalText(self) -> str:
        return self._history_total_text

    @Property(str, notify=changed)
    def historyDurationText(self) -> str:
        return self._history_duration_text

    @Property(str, notify=changed)
    def historySuccessRateText(self) -> str:
        return self._history_success_rate_text

    @Property(bool, notify=changed)
    def historyDetailVisible(self) -> bool:
        return self._history_detail_visible

    @Property("QVariantMap", notify=changed)
    def selectedHistoryDetail(self) -> dict[str, Any]:
        return self._selected_history_detail

    @Property(bool, notify=changed)
    def batchReprocessVisible(self) -> bool:
        return self._batch_reprocess_visible

    @Property(str, notify=changed)
    def batchReprocessStage(self) -> str:
        return self._batch_reprocess_stage

    @Property(bool, notify=changed)
    def batchReprocessRunning(self) -> bool:
        return self._batch_reprocess_stage == "running"

    @Property(int, notify=changed)
    def batchReprocessTotal(self) -> int:
        return self._batch_reprocess_total

    @Property(int, notify=changed)
    def batchReprocessCooldownSeconds(self) -> int:
        return self._batch_reprocess_cooldown_seconds

    @Property(int, notify=changed)
    def batchReprocessProgressValue(self) -> int:
        return self._batch_reprocess_progress_value

    @Property(int, notify=changed)
    def batchReprocessProgressTotal(self) -> int:
        return self._batch_reprocess_progress_total

    @Property(str, notify=changed)
    def batchReprocessMessage(self) -> str:
        return self._batch_reprocess_message

    @Property("QVariantMap", notify=changed)
    def batchReprocessResult(self) -> dict[str, Any]:
        return self._batch_reprocess_result

    @Property(bool, notify=changed)
    def historyActionBusy(self) -> bool:
        return self._history_action_busy

    @Property(str, notify=changed)
    def historyActionMessage(self) -> str:
        return self._history_action_message

    @Property(str, notify=changed)
    def historyActionStage(self) -> str:
        return self._history_action_stage

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

    @Slot()
    def refreshReviewSuggestions(self) -> None:
        self._load_review_suggestions()
        self._load_lexicon_entries()
        self._load_review_jobs()
        self.changed.emit()

    @Slot(str, result=bool)
    def setReviewCategoryFilter(self, category: str) -> bool:
        normalized = str(category or "").strip() or "all"
        allowed = {
            "all",
            "boundary_violation",
            "content_distortion",
            "diagnostics",
            "lexicon_learning",
            "prompt_quality",
        }
        if normalized not in allowed:
            normalized = "all"
        if self._review_selected_category == normalized:
            return False

        self._review_selected_category = normalized
        self._load_review_suggestions()
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def toggleReviewSuggestionGroup(self, category: str) -> bool:
        normalized = str(category or "").strip()
        if not normalized:
            return False

        groups = {
            str(item.get("category", "") or ""): item
            for item in self._review_suggestion_groups
        }
        current = groups.get(normalized)
        if not current:
            return False

        return self.setReviewSuggestionGroupExpanded(
            normalized,
            not bool(current.get("isExpanded", False)),
        )

    @Slot(str, bool, result=bool)
    def setReviewSuggestionGroupExpanded(self, category: str, expanded: bool) -> bool:
        normalized = str(category or "").strip()
        if not normalized:
            return False

        all_categories = {
            str(item.get("category", "") or "")
            for item in self._review_category_summaries
        }
        if normalized not in all_categories:
            return False

        expanded_bool = bool(expanded)
        self._review_group_expanded_overrides[normalized] = expanded_bool
        self._load_review_suggestions()
        self.changed.emit()
        return True

    @Slot(result="QVariant")
    def runReviewNow(self) -> dict[str, Any]:
        run_review = getattr(self._settings_service, "run_review_now", None)
        if not callable(run_review):
            run_review = getattr(self._settings_service, "run_idle_review_once", None)
        if not callable(run_review):
            result = {
                "ran": False,
                "reason": "review_scheduler_unavailable",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }
        else:
            try:
                raw_result = run_review()
            except Exception:
                raw_result = {
                    "ran": False,
                    "reason": "review_run_failed",
                    "jobId": "",
                    "reviewedRecordCount": 0,
                    "suggestionCount": 0,
                }
            result = dict(raw_result) if isinstance(raw_result, dict) else {}
            result.setdefault("ran", False)
            result.setdefault("reason", "review_run_failed")
            result.setdefault("jobId", "")
            result.setdefault("reviewedRecordCount", 0)
            result.setdefault("suggestionCount", 0)

        self._review_last_run_result = result
        self._review_run_message = self._format_review_run_message(result)
        self.refreshReviewSuggestions()
        return result

    @Slot(result="QVariant")
    def runIdleReviewOnce(self) -> dict[str, Any]:
        run_review = getattr(self._settings_service, "run_idle_review_once", None)
        if not callable(run_review):
            run_review = getattr(self._settings_service, "run_review_now", None)
        if not callable(run_review):
            result = {
                "ran": False,
                "reason": "review_scheduler_unavailable",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }
        else:
            try:
                raw_result = run_review()
            except Exception:
                raw_result = {
                    "ran": False,
                    "reason": "review_run_failed",
                    "jobId": "",
                    "reviewedRecordCount": 0,
                    "suggestionCount": 0,
                }
            result = dict(raw_result) if isinstance(raw_result, dict) else {}
            result.setdefault("ran", False)
            result.setdefault("reason", "review_run_failed")
            result.setdefault("jobId", "")
            result.setdefault("reviewedRecordCount", 0)
            result.setdefault("suggestionCount", 0)

        self._review_last_run_result = result
        self._review_run_message = self._format_review_run_message(result)
        self.refreshReviewSuggestions()
        return result

    @Slot(str, result=bool)
    def acceptReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "accepted")

    @Slot(str, result=bool)
    def rejectReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "rejected")

    @Slot(str, result=bool)
    def ignoreReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "ignored")

    @Slot(str, result=bool)
    def archiveReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "archived")

    @Slot(str, result=bool)
    def reprocessReviewSuggestion(self, suggestion_id: str) -> bool:
        suggestion_id = str(suggestion_id or "").strip()
        if not suggestion_id:
            return False

        suggestion = next(
            (
                item
                for item in self._review_suggestions
                if str(item.get("id", "") or "") == suggestion_id
            ),
            None,
        )
        if not suggestion:
            return False

        if not bool(suggestion.get("canReprocessSample", False)):
            return False

        primary_source_record_id = str(
            suggestion.get("primarySourceRecordId", "") or ""
        ).strip()
        if not primary_source_record_id:
            return False

        history_service = self._get_history_service()
        if not history_service:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Reprocessing requires history service."
            self.changed.emit()
            return False

        record = history_service.get_record_by_id(primary_source_record_id)
        if record is None:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Unable to locate the source record."
            self.changed.emit()
            return False

        self._pending_review_reprocess_suggestion_id = suggestion_id
        self._retry_history_record(record)
        return True

    @Slot(str, result=bool)
    def revertReviewSuggestionToRaw(self, suggestion_id: str) -> bool:
        suggestion_id = str(suggestion_id or "").strip()
        if not suggestion_id:
            return False

        suggestion = next(
            (
                item
                for item in self._review_suggestions
                if str(item.get("id", "") or "") == suggestion_id
            ),
            None,
        )
        if not suggestion:
            return False

        if not bool(suggestion.get("canRevertToRaw", False)):
            return False

        primary_source_record_id = str(
            suggestion.get("primarySourceRecordId", "") or ""
        ).strip()
        if not primary_source_record_id:
            return False

        history_service = self._get_history_service()
        if not history_service:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Rollback requires history service."
            self.changed.emit()
            return False

        record = self._get_history_record_by_id(primary_source_record_id)
        if record is None:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Unable to locate the source record."
            self.changed.emit()
            return False

        raw_text = str(getattr(record, "transcription_text", "") or "")
        if not raw_text:
            return False

        record.final_text = raw_text
        update_record = getattr(history_service, "update_record", None)
        if not callable(update_record):
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Rollback requires history update support."
            self.changed.emit()
            return False

        success = bool(update_record(record))
        self.refreshHistory(self._history_query)
        if success:
            self._decide_review_suggestion(suggestion_id, "archived")
            if (
                self._selected_history_record is not None
                and getattr(self._selected_history_record, "id", "") == record.id
            ):
                self._selected_history_record = record
                self._selected_history_detail = self._record_to_history_detail(record)
                self._history_detail_visible = True
            self._history_action_stage = "complete"
            self._history_action_busy = False
            self._history_action_message = (
                "Review sample has been reverted to the raw transcript."
            )
            self.changed.emit()
            return True

        self._history_action_stage = "failed"
        self._history_action_busy = False
        self._history_action_message = "Failed to revert the sample to raw transcript."
        self.changed.emit()
        return False

    @Slot(result=bool)
    def clearLexiconEntries(self) -> bool:
        clear_entries = getattr(self._settings_service, "clear_lexicon_entries", None)
        if not callable(clear_entries):
            return False
        try:
            success = bool(clear_entries())
        except Exception:
            success = False
        if success:
            self.refreshReviewSuggestions()
        return success

    @Slot(result=bool)
    def clearReviewLearningData(self) -> bool:
        clear_learning_data = getattr(
            self._settings_service,
            "clear_review_learning_data",
            None,
        )
        if not callable(clear_learning_data):
            self._review_learning_data_message = self.translate(
                "clear_learning_data_failed",
                "Failed to clear local learning data.",
            )
            self.changed.emit()
            return False
        try:
            success = bool(clear_learning_data())
        except Exception:
            success = False
        self._review_learning_data_message = self.translate(
            "clear_learning_data_success" if success else "clear_learning_data_failed",
            "Local learning data has been cleared."
            if success
            else "Failed to clear local learning data.",
        )
        if success:
            self.refreshReviewSuggestions()
        else:
            self.changed.emit()
        return success

    @Slot(str, result="QVariant")
    def exportLexiconEntries(self, export_path: str = "") -> dict[str, Any]:
        export_entries = getattr(self._settings_service, "export_lexicon_entries", None)
        if not callable(export_entries):
            result = {
                "success": False,
                "path": "",
                "count": 0,
                "reason": "export_unavailable",
            }
        else:
            try:
                raw = export_entries(export_path or None)
            except Exception as exc:
                raw = {
                    "success": False,
                    "path": "",
                    "count": 0,
                    "reason": str(exc),
                }
            result = (
                dict(raw)
                if isinstance(raw, dict)
                else {
                    "success": False,
                    "path": "",
                    "count": 0,
                    "reason": "export_failed",
                }
            )
        self._lexicon_last_export_path = str(result.get("path", "") or "")
        if result.get("success"):
            count = int(result.get("count", 0) or 0)
            target = self._lexicon_last_export_path or "local file"
            self._lexicon_export_message = self.translate(
                "export_lexicon_success",
                "Exported {count} lexicon entries to {path}",
            ).format(count=count, path=target)
        else:
            reason = str(result.get("reason", "export_failed") or "export_failed")
            self._lexicon_export_message = self.translate(
                "export_lexicon_failed",
                "Lexicon export failed: {reason}",
            ).format(reason=reason)
        self.changed.emit()
        return result

    @Slot(str, result="QVariant")
    def exportReviewDebugReport(self, export_path: str = "") -> dict[str, Any]:
        export_report = getattr(
            self._settings_service,
            "export_review_debug_report",
            None,
        )
        if not callable(export_report):
            result = {
                "success": False,
                "path": "",
                "count": 0,
                "reason": "export_unavailable",
            }
        else:
            try:
                raw = export_report(export_path or None)
            except Exception as exc:
                raw = {
                    "success": False,
                    "path": "",
                    "count": 0,
                    "reason": str(exc),
                }
            result = (
                dict(raw)
                if isinstance(raw, dict)
                else {
                    "success": False,
                    "path": "",
                    "count": 0,
                    "reason": "export_failed",
                }
            )
        self._review_debug_last_export_path = str(result.get("path", "") or "")
        if result.get("success"):
            count = int(result.get("count", 0) or 0)
            target = self._review_debug_last_export_path or "local file"
            self._review_debug_export_message = self.translate(
                "review_debug_export_success",
                "Exported {count} prompt/validator debug suggestions to {path}",
            ).format(count=count, path=target)
        else:
            reason = str(result.get("reason", "export_failed") or "export_failed")
            self._review_debug_export_message = self.translate(
                "review_debug_export_failed",
                "Prompt/validator debug export failed: {reason}",
            ).format(reason=reason)
        self.changed.emit()
        return result

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

    @Slot(str)
    def refreshHistory(self, query: str = "") -> None:
        self._history_query = str(query or "").strip()
        self._history_page_cursor_timestamp = None
        self._history_page_cursor_id = None
        self._history_has_more_pages = True
        self._load_history_page(append=False)
        self._update_history_stats()
        self.changed.emit()

    @Slot()
    def loadMoreHistory(self) -> None:
        if not self._history_has_more_pages:
            return
        self._load_history_page(append=True)
        self.changed.emit()

    @Slot(int)
    def openHistoryDetail(self, index: int) -> None:
        if index < 0 or index >= len(self._history_records):
            return

        self._selected_history_index = index
        self._selected_history_record = self._history_records[index]
        self._selected_history_detail = self._record_to_history_detail(
            self._selected_history_record
        )
        self._history_detail_visible = True
        self.changed.emit()

    def _open_history_record_by_id(self, record_id: str) -> bool:
        normalized = str(record_id or "").strip()
        if not normalized:
            return False

        for index, record in enumerate(self._history_records):
            if str(getattr(record, "id", "") or "") == normalized:
                self._selected_history_index = index
                self._selected_history_record = record
                self._selected_history_detail = self._record_to_history_detail(record)
                self._history_detail_visible = True
                self.changed.emit()
                return True

        record = self._get_history_record_by_id(normalized)
        if record is None:
            return False

        self._selected_history_index = -1
        self._selected_history_record = record
        self._selected_history_detail = self._record_to_history_detail(record)
        self._history_detail_visible = True
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def openReviewSourceRecord(self, suggestion_id: str) -> bool:
        suggestion_id = str(suggestion_id or "").strip()
        if not suggestion_id:
            return False

        suggestion = next(
            (
                item
                for item in self._review_suggestions
                if str(item.get("id", "") or "") == suggestion_id
            ),
            None,
        )
        if not suggestion:
            return False

        source_record_id = str(suggestion.get("sourceRecordOpenId", "") or "").strip()
        if not source_record_id:
            source_record_ids = suggestion.get("sourceRecordIds", [])
            if not isinstance(source_record_ids, list):
                source_record_ids = (
                    [str(source_record_ids)] if source_record_ids else []
                )
            source_record_id = self._first_viewable_source_record_id(
                [str(value) for value in source_record_ids if str(value)]
            )
        if not source_record_id:
            return False

        return self._open_history_record_by_id(source_record_id)

    @Slot()
    def closeHistoryDetail(self) -> None:
        self._clear_history_detail()
        self.changed.emit()

    @Slot(int)
    def retryHistoryRecord(self, index: int) -> None:
        if index < 0 or index >= len(self._history_records):
            return
        self._retry_history_record(self._history_records[index])

    @Slot()
    def retrySelectedHistoryRecord(self) -> None:
        if self._selected_history_record is None:
            return
        self._retry_history_record(self._selected_history_record)

    @Slot(int, result=bool)
    def deleteHistoryRecord(self, index: int) -> bool:
        if index < 0 or index >= len(self._history_records):
            return False

        service = self._get_history_service()
        if not service:
            return False

        record = self._history_records[index]
        success = bool(service.delete_record(getattr(record, "id", "")))
        if success:
            self.refreshHistory(self._history_query)
        return success

    @Slot(result=bool)
    def deleteSelectedHistoryRecord(self) -> bool:
        if self._selected_history_index < 0:
            return False
        success = self.deleteHistoryRecord(self._selected_history_index)
        if success:
            self._clear_history_detail()
            self.changed.emit()
        return success

    @Slot()
    def copySelectedHistoryText(self) -> None:
        if not self._selected_history_detail:
            return
        text = str(self._selected_history_detail.get("primaryText", ""))
        QApplication.clipboard().setText(text)

    def _retry_history_record(self, record: Any) -> None:
        from ..utils import app_logger

        get_transcription_service = getattr(
            self._settings_service, "get_transcription_service", None
        )
        get_ai_processing_controller = getattr(
            self._settings_service, "get_ai_processing_controller", None
        )
        transcription_service = (
            get_transcription_service() if callable(get_transcription_service) else None
        )
        ai_processing_controller = (
            get_ai_processing_controller()
            if callable(get_ai_processing_controller)
            else None
        )
        history_service = self._get_history_service()

        app_logger.log_audio_event(
            "Fluent history retry requested",
            {
                "has_transcription_service": transcription_service is not None,
                "has_ai_controller": ai_processing_controller is not None,
                "record_id": getattr(record, "id", ""),
            },
        )

        if not transcription_service or not history_service:
            self._pending_review_reprocess_suggestion_id = ""
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = (
                "Retry processing requires transcription service."
            )
            self.changed.emit()
            return

        self._retry_worker = ReprocessingWorker(
            record_id=getattr(record, "id", ""),
            audio_file_path=getattr(record, "audio_file_path", ""),
            transcription_service=transcription_service,
            ai_processing_controller=ai_processing_controller,
            config_service=self._settings_service,
            history_service=history_service,
        )
        self._retry_worker.progress_updated.connect(self._on_retry_progress_updated)
        self._retry_worker.reprocessing_completed.connect(
            self._on_retry_reprocessing_completed
        )
        self._retry_worker.reprocessing_failed.connect(
            self._on_retry_reprocessing_failed
        )
        self._history_action_stage = "running"
        self._history_action_busy = True
        self._history_action_message = "Initializing reprocessing..."
        self.changed.emit()
        self._retry_worker.start()

    def _on_retry_progress_updated(self, message: str) -> None:
        self._history_action_message = message
        self.changed.emit()

    def _on_retry_reprocessing_completed(self, result: dict) -> None:
        if self._retry_worker:
            if self._retry_worker.isRunning():
                self._retry_worker.wait(1000)
            self._retry_worker = None

        new_record_id = result.get("new_record_id")
        history_service = self._get_history_service()
        if new_record_id and history_service:
            fresh_record = history_service.get_record_by_id(new_record_id)
            if fresh_record:
                self._selected_history_record = fresh_record
                self._selected_history_detail = self._record_to_history_detail(
                    fresh_record
                )
                self._history_detail_visible = True

        self.refreshHistory(self._history_query)
        if self._pending_review_reprocess_suggestion_id:
            self._decide_review_suggestion(
                self._pending_review_reprocess_suggestion_id,
                "archived",
            )
            self._pending_review_reprocess_suggestion_id = ""
        self._history_action_stage = "complete"
        self._history_action_busy = False
        self._history_action_message = "Recording has been successfully reprocessed."
        self.changed.emit()

    def _on_retry_reprocessing_failed(self, error_message: str) -> None:
        if self._retry_worker:
            if self._retry_worker.isRunning():
                self._retry_worker.wait(1000)
            self._retry_worker = None

        self._pending_review_reprocess_suggestion_id = ""
        self._history_action_stage = "failed"
        self._history_action_busy = False
        self._history_action_message = (
            f"Failed to reprocess the recording: {error_message}"
        )
        self.changed.emit()

    @Slot()
    def _on_retry_reprocessing_canceled(self) -> None:
        if self._retry_worker:
            self._retry_worker.stop()
            self._retry_worker.wait(2000)
            self._retry_worker = None

        self._pending_review_reprocess_suggestion_id = ""
        self._history_action_stage = "canceled"
        self._history_action_busy = False
        self._history_action_message = "Reprocessing operation has been canceled."
        self.changed.emit()

    @Slot()
    def cancelHistoryAction(self) -> None:
        if self._retry_worker:
            self._on_retry_reprocessing_canceled()
            return
        self._history_action_stage = "idle"
        self._history_action_busy = False
        self._history_action_message = ""
        self.changed.emit()

    @Slot()
    def startBatchReprocess(self) -> None:
        service = self._get_history_service()
        if not service:
            self._set_batch_message(
                "failed",
                "History service not available. Please restart the application.",
                visible=True,
            )
            return

        try:
            total_records = int(service.get_total_count())
            if total_records <= 0:
                self._set_batch_message(
                    "empty",
                    "No history records found to reprocess.",
                    visible=True,
                )
                return

            self._batch_reprocess_visible = True
            self._batch_reprocess_stage = "confirm"
            self._batch_reprocess_total = total_records
            self._batch_reprocess_progress_value = 0
            self._batch_reprocess_progress_total = 0
            self._batch_reprocess_message = (
                f"You are about to re-transcribe {total_records} records."
            )
            self._batch_reprocess_result = {}
            self.changed.emit()
        except Exception as exc:
            self._set_batch_message(
                "failed",
                f"Failed to start batch reprocessing: {exc}",
                visible=True,
            )

    @Slot(int)
    def confirmBatchReprocess(self, cd_seconds: int = 0) -> None:
        total_records = self._batch_reprocess_total
        if total_records <= 0:
            return
        self._start_batch_reprocessing(total_records, max(0, int(cd_seconds or 0)))

    @Slot()
    def closeBatchReprocess(self) -> None:
        if self._batch_reprocess_stage in {"running", "canceling"}:
            return
        self._batch_reprocess_visible = False
        self._batch_reprocess_stage = "idle"
        self._batch_reprocess_message = ""
        self._batch_reprocess_result = {}
        self.changed.emit()

    def _set_batch_message(self, stage: str, message: str, visible: bool) -> None:
        self._batch_reprocess_visible = visible
        self._batch_reprocess_stage = stage
        self._batch_reprocess_message = message
        self.changed.emit()

    def _start_batch_reprocessing(self, total_records: int, cd_seconds: int) -> None:
        self._batch_cancel_requested = False
        get_transcription_service = getattr(
            self._settings_service, "get_transcription_service", None
        )
        get_ai_processing_controller = getattr(
            self._settings_service, "get_ai_processing_controller", None
        )
        transcription_service = (
            get_transcription_service() if callable(get_transcription_service) else None
        )
        ai_processing_controller = (
            get_ai_processing_controller()
            if callable(get_ai_processing_controller)
            else None
        )
        history_service = self._get_history_service()

        if not transcription_service or not history_service:
            self._set_batch_message(
                "failed",
                "Required services not available. Please restart the application.",
                visible=True,
            )
            return

        self._batch_worker = BatchReprocessingWorker(
            total_records=total_records,
            cd_seconds=cd_seconds,
            transcription_service=transcription_service,
            ai_processing_controller=ai_processing_controller,
            config_service=self._settings_service,
            history_service=history_service,
        )
        self._batch_worker.progress_updated.connect(self._on_batch_progress_updated)
        self._batch_worker.batch_completed.connect(self._on_batch_completed)
        self._batch_reprocess_visible = True
        self._batch_reprocess_stage = "running"
        self._batch_reprocess_total = total_records
        self._batch_reprocess_cooldown_seconds = cd_seconds
        self._batch_reprocess_progress_value = 0
        self._batch_reprocess_progress_total = total_records
        self._batch_reprocess_message = "Starting batch reprocessing..."
        self._batch_reprocess_result = {}
        self.changed.emit()
        self._batch_worker.start()

    def _on_batch_progress_updated(
        self, current: int, total: int, record_id: str
    ) -> None:
        self._batch_reprocess_progress_value = int(current)
        self._batch_reprocess_progress_total = int(total)
        self._batch_reprocess_message = f"Processing {current}/{total} records...\nCurrent record: {record_id[:16]}..."
        self.changed.emit()

    def _on_batch_completed(self, stats: dict) -> None:
        if self._batch_worker:
            self._batch_worker.wait()
            self._batch_worker = None

        self.refreshHistory(self._history_query)
        self._batch_reprocess_result = dict(stats)

        if self._batch_cancel_requested:
            self._batch_cancel_requested = False
            self._set_batch_message(
                "canceled",
                "Batch reprocessing was canceled. Completed work has been kept, and remaining records were skipped.",
                visible=True,
            )
            return

        report_lines = [
            "Batch Reprocessing Complete!",
            f"Total records: {stats.get('total', 0)}",
            f"Successful: {stats.get('success', 0)}",
            f"Skipped: {stats.get('skipped', 0)}",
            f"Failed: {stats.get('failed', 0)}",
        ]
        errors = stats.get("errors", [])
        if errors:
            report_lines.append("")
            report_lines.append(f"First {min(5, len(errors))} errors:")
            report_lines.extend(f"  {error}" for error in errors[:5])
            if len(errors) > 5:
                report_lines.append(f"... and {len(errors) - 5} more errors")

        self._set_batch_message("complete", "\n".join(report_lines), visible=True)

    @Slot()
    def cancelBatchReprocess(self) -> None:
        self._batch_cancel_requested = True
        self._batch_reprocess_stage = "canceling"
        self._batch_reprocess_message = (
            "Cancel requested...\nWaiting for the current record to finish safely."
        )
        if self._batch_worker:
            self._batch_worker.stop()
        self.changed.emit()

    @Slot()
    def reload(self) -> None:
        self._pending.clear()
        self.changed.emit()

    @Slot()
    def apply(self) -> None:
        try:
            batch = getattr(self._settings_service, "set_settings_batch", None)
            if callable(batch) and self._pending:
                # 批量提交：让 provider/api_key 等关联校验能看到整批变更
                batch(dict(self._pending))
            else:
                for key, value in self._pending.items():
                    self._settings_service.set_setting(key, value)
        except Exception as e:
            # 配置校验失败（如切到无 key 的 cloud provider）→ 通知 UI
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
