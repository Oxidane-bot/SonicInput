"""AI处理控制器

负责AI文本优化处理。
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import requests

from ...ai import AIClientFactory
from ...utils import OpenRouterAPIError, app_logger
from ..base.lifecycle_component import LifecycleComponent
from ..interfaces import (
    IAIProcessingController,
    IAIService,
    IConfigService,
    IEventService,
    IStateManager,
)
from ..services.config import ConfigKeys
from ..services.events import Events
from ..services.storage import HistoryStorageService
from .base_controller import BaseController


class AIProcessingController(
    LifecycleComponent, BaseController, IAIProcessingController
):
    """AI处理控制器实现

    职责：
    - 处理AI文本优化
    - 动态选择AI服务提供商
    - 错误处理和回退
    - 通过 EventBus 发送AI处理事件
    """

    _SENTENCE_PUNCT_RE = re.compile(r"[。！？!?;；]+")
    _ASCII_ALNUM_END_RE = re.compile(r"[A-Za-z0-9]$")
    _ASCII_ALNUM_START_RE = re.compile(r"^[A-Za-z0-9]")
    _SPLIT_BOUNDARIES = (
        "然后",
        "但是",
        "所以",
        "并且",
        "而且",
        "如果",
        "因为",
        "不过",
        "另外",
        "最后",
        "接着",
        "同时",
        "之后",
        "因此",
        "而是",
        "为了",
        "以及",
        "比如",
        "例如",
    )

    def __init__(
        self,
        config_service: IConfigService,
        event_service: IEventService,
        state_manager: IStateManager,
        history_service: HistoryStorageService,
    ):
        # Initialize LifecycleComponent
        LifecycleComponent.__init__(self, "AIProcessingController")

        # Initialize base controller
        BaseController.__init__(self, config_service, event_service, state_manager)

        # Controller-specific services
        self._history_service = history_service

        # TPS追踪（用于性能日志）
        self._last_ai_tps: float = 0.0

        # 当前处理的记录ID
        self._current_record_id: Optional[str] = None
        self._sentence_splitter = None
        self._sentence_splitter_error: Optional[str] = None
        self._last_incremental_output_used = False
        self._chunk_text_by_id: Dict[int, str] = {}
        self._chunk_ai_refined_parts: List[str] = []
        self._chunk_ai_pending_sentences: List[str] = []
        self._chunk_ai_processed_sentence_count = 0
        self._chunk_ai_last_transcription_text = ""
        self._chunk_ai_base_event_data: Dict[str, Any] = {}

        # NOTE: Event listener registration moved to _do_start() for hot reload support
        # NOTE: Initialization logging moved to _do_start() for hot reload support

    def _do_start(self) -> bool:
        """Initialize AI processing resources

        Returns:
            True if start successful
        """
        try:
            # Register event listeners (supports hot reload)
            self._register_event_listeners()

            # Log initialization
            self._log_initialization()

            app_logger.log_audio_event(
                "AI processing controller ready", {"ai_enabled": self.is_ai_enabled()}
            )
            return True
        except Exception as e:
            app_logger.log_error(e, "AIProcessingController._do_start")
            return False

    def _do_stop(self) -> bool:
        """Cleanup AI processing resources

        Returns:
            True if stop successful
        """
        try:
            # Cleanup event listeners (supports hot reload)
            self._cleanup_event_listeners()

            # Clear current record ID
            self._current_record_id = None
            self._last_ai_tps = 0.0
            self._sentence_splitter = None
            self._sentence_splitter_error = None
            self._last_incremental_output_used = False
            self._reset_chunk_ai_state()

            app_logger.log_audio_event("AI processing controller stopped", {})
            return True
        except Exception as e:
            app_logger.log_error(e, "AIProcessingController._do_stop")
            return False

    def _register_event_listeners(self) -> None:
        """Register event listeners for AI processing events

        NOTE: Called from _do_start() to support hot reload.
        Uses _track_listener() to enable proper cleanup.
        """
        self._track_listener(
            Events.TRANSCRIPTION_COMPLETED, self._on_transcription_completed
        )
        self._track_listener(
            Events.TRANSCRIPTION_REQUEST, self._on_transcription_request
        )
        self._track_listener(
            Events.STREAMING_CHUNK_COMPLETED, self._on_streaming_chunk_completed
        )
        self._track_listener(Events.RECORDING_STARTED, self._on_recording_started)
        self._track_listener(Events.TRANSCRIPTION_ERROR, self._on_transcription_error)

    def _reset_chunk_ai_state(self) -> None:
        self._chunk_text_by_id.clear()
        self._chunk_ai_refined_parts.clear()
        self._chunk_ai_pending_sentences.clear()
        self._chunk_ai_processed_sentence_count = 0
        self._chunk_ai_last_transcription_text = ""
        self._chunk_ai_base_event_data = {}

    def _on_recording_started(self, data: Any = None) -> None:
        self._current_record_id = None
        self._last_incremental_output_used = False
        self._reset_chunk_ai_state()

    def _on_transcription_error(self, data: Any = None) -> None:
        self._reset_chunk_ai_state()

    def _on_transcription_request(self, data: dict) -> None:
        self._current_record_id = data.get("record_id")
        self._last_incremental_output_used = False
        self._reset_chunk_ai_state()
        self._chunk_ai_base_event_data = {
            "streaming_mode": "chunked",
            "record_id": self._current_record_id,
            "audio_duration": data.get("audio_duration", 0.0),
            "recording_stop_time": data.get("recording_stop_time"),
        }

    def _is_first_chunk_output_enabled(self) -> bool:
        return self._config.get_setting(ConfigKeys.AI_FIRST_CHUNK_OUTPUT_ENABLED, False)

    def _should_use_ai(self, streaming_mode: str, text: str) -> bool:
        if streaming_mode == "realtime":
            app_logger.log_audio_event(
                "Realtime mode: skipping AI processing", {"text_length": len(text)}
            )
            return False
        if streaming_mode == "chunked":
            enabled = self.is_ai_enabled()
            app_logger.log_audio_event(
                "Chunked mode AI decision",
                {"enabled": enabled, "text_length": len(text)},
            )
            return enabled
        if streaming_mode == "disabled":
            enabled = self.is_ai_enabled()
            app_logger.log_audio_event(
                "Disabled streaming mode AI decision",
                {"enabled": enabled, "text_length": len(text)},
            )
            return enabled

        enabled = self.is_ai_enabled()
        app_logger.log_audio_event(
            f"Unknown streaming_mode '{streaming_mode}': defaulting to respect AI switch",
            {"ai_enabled": enabled, "text_length": len(text)},
        )
        return enabled

    def _longest_suffix_prefix_overlap(
        self, left: str, right: str, max_chars: int = 60
    ) -> int:
        left = left.strip()
        right = right.strip()
        limit = min(len(left), len(right), max_chars)
        for size in range(limit, 0, -1):
            if left[-size:] == right[:size]:
                return size
        return 0

    def _smart_concat_text(self, left_text: str, right_text: str) -> str:
        if not left_text:
            return right_text
        if not right_text:
            return left_text
        if self._ASCII_ALNUM_END_RE.search(
            left_text
        ) and self._ASCII_ALNUM_START_RE.match(right_text):
            return f"{left_text} {right_text}"
        return left_text + right_text

    def _merge_chunk_texts_with_boundary_dedup(self, text_parts: List[str]) -> str:
        merged = ""
        for raw_text in text_parts:
            part = raw_text.strip()
            if not part:
                continue
            if not merged:
                merged = part
                continue

            overlap = self._longest_suffix_prefix_overlap(merged, part, max_chars=60)
            if overlap > 0:
                merged = merged + part[overlap:]
            else:
                merged = self._smart_concat_text(merged, part)
        return merged.strip()

    def _get_contiguous_chunk_text(self) -> str:
        if not self._chunk_text_by_id:
            return ""

        parts: List[str] = []
        next_chunk_id = 0
        while next_chunk_id in self._chunk_text_by_id:
            parts.append(self._chunk_text_by_id[next_chunk_id])
            next_chunk_id += 1
        return self._merge_chunk_texts_with_boundary_dedup(parts)

    def _consume_chunk_ai_sentences(self, text: str) -> None:
        sentences, split_method = self._split_text_for_ai(text)
        stable_sentences = sentences[:-1] if len(sentences) > 1 else []
        new_stable_sentences = stable_sentences[
            self._chunk_ai_processed_sentence_count :
        ]
        if not new_stable_sentences:
            return

        self._chunk_ai_pending_sentences.extend(new_stable_sentences)
        self._chunk_ai_processed_sentence_count = len(stable_sentences)

        app_logger.log_audio_event(
            "Chunk AI sentences updated",
            {
                "split_method": split_method,
                "stable_sentences": len(stable_sentences),
                "pending_sentences": len(self._chunk_ai_pending_sentences),
            },
        )

        while len(self._chunk_ai_pending_sentences) >= 2:
            group_size = 5 if len(self._chunk_ai_pending_sentences) >= 5 else 2
            group_sentences = self._chunk_ai_pending_sentences[:group_size]
            del self._chunk_ai_pending_sentences[:group_size]

            refined_part = self.process_with_ai(
                "".join(group_sentences).strip(),
                update_history=False,
            )
            self._chunk_ai_refined_parts.append(refined_part)
            cumulative_text = self._join_refined_groups(self._chunk_ai_refined_parts)
            self._last_incremental_output_used = True
            self._emit_incremental_ai_text(
                cumulative_text,
                {
                    **self._chunk_ai_base_event_data,
                    "original_text": text,
                },
            )

    def _on_streaming_chunk_completed(self, data: dict) -> None:
        if not (
            self._is_first_chunk_output_enabled()
            and self._is_sentence_split_enabled()
            and self.is_ai_enabled()
        ):
            return

        result = data.get("result") or {}
        if not result.get("success", False):
            return

        chunk_text = str(result.get("text", "") or "").strip()
        if not chunk_text:
            return

        chunk_id = data.get("chunk_id", result.get("chunk_id"))
        if not isinstance(chunk_id, int) or chunk_id < 0:
            return

        self._chunk_text_by_id[chunk_id] = chunk_text
        contiguous_text = self._get_contiguous_chunk_text()
        if (
            not contiguous_text
            or contiguous_text == self._chunk_ai_last_transcription_text
        ):
            return

        self._chunk_ai_last_transcription_text = contiguous_text
        self._consume_chunk_ai_sentences(contiguous_text)

    def _finalize_chunk_triggered_ai(
        self,
        final_text: str,
        incremental_event_data: Dict[str, Any],
    ) -> str:
        merged_text = final_text.strip() or self._get_contiguous_chunk_text()
        sentences, split_method = self._split_text_for_ai(merged_text)
        remaining_sentences = sentences[self._chunk_ai_processed_sentence_count :]
        pending_sentences = [*self._chunk_ai_pending_sentences, *remaining_sentences]

        app_logger.log_audio_event(
            "Finalizing chunk-triggered AI",
            {
                "split_method": split_method,
                "final_sentence_count": len(sentences),
                "remaining_sentences": len(remaining_sentences),
                "pending_sentences": len(pending_sentences),
                "refined_parts": len(self._chunk_ai_refined_parts),
            },
        )

        refined_parts = list(self._chunk_ai_refined_parts)
        for group in self._group_sentences_3_5(pending_sentences):
            group_text = "".join(group).strip()
            if not group_text:
                continue
            refined_parts.append(
                self.process_with_ai(
                    group_text,
                    update_history=False,
                )
            )

        refined_text = self._join_refined_groups(refined_parts)
        if not refined_text:
            refined_text = merged_text

        if self._current_record_id:
            self._update_ai_status(
                record_id=self._current_record_id,
                ai_text=refined_text,
                status="success",
                error=None,
                final_text=refined_text,
            )

        self._events.emit(
            Events.AI_PROCESSING_COMPLETED,
            {"original": merged_text, "refined": refined_text},
        )

        app_logger.log_audio_event(
            "Chunk-triggered AI finalized",
            {
                "incremental_output_used": self._last_incremental_output_used,
                "final_length": len(refined_text),
            },
        )

        return refined_text

    def _on_transcription_completed(self, data: dict) -> None:
        """处理转录完成事件

        Args:
            data: 转录结果数据（可能包含 streaming_mode）
        """
        text = data.get("text", "")
        self._current_record_id = data.get("record_id")
        streaming_mode = data.get("streaming_mode", "chunked")

        should_use_ai = self._should_use_ai(streaming_mode, text)

        # 根据策略决定是否使用 AI
        if should_use_ai and text.strip():
            data_copy = {k: v for k, v in data.items() if k != "text"}
            use_first_chunk_output = (
                streaming_mode == "chunked"
                and self._is_sentence_split_enabled()
                and self._is_first_chunk_output_enabled()
            )
            if use_first_chunk_output:
                optimized_text = self._finalize_chunk_triggered_ai(
                    text,
                    {
                        "original_text": text,
                        "streaming_mode": streaming_mode,
                        **data_copy,
                    },
                )
            else:
                self._last_incremental_output_used = False
                optimized_text = self.process_with_ai(
                    text,
                    incremental_event_data={
                        "original_text": text,
                        "streaming_mode": streaming_mode,
                        **data_copy,
                    },
                )

            # 发送AI处理完成事件（携带优化后的文本）
            self._events.emit(
                Events.AI_PROCESSED_TEXT,
                {
                    "text": optimized_text,
                    "original_text": text,
                    "ai_tps": self._last_ai_tps,
                    "streaming_mode": streaming_mode,
                    "incremental_output_used": self._last_incremental_output_used,
                    **data_copy,  # 保留原始数据（audio_duration等）
                },
            )
            self._reset_chunk_ai_state()
        else:
            # 不使用AI：更新历史记录
            skip_reason = (
                "realtime_mode"
                if streaming_mode == "realtime"
                else "ai_disabled"
                if not self.is_ai_enabled()
                else "no_text"
            )

            if self._current_record_id:
                self._update_ai_status(
                    record_id=self._current_record_id,
                    ai_text=None,
                    status="skipped",
                    error=None,
                    final_text=text,
                )

            # 不使用AI，直接发送原文本
            # 创建data副本并移除会冲突的键
            data_copy = {k: v for k, v in data.items() if k != "text"}

            self._events.emit(
                Events.AI_PROCESSED_TEXT,
                {
                    "text": text,
                    "original_text": text,
                    "streaming_mode": streaming_mode,
                    "skip_reason": skip_reason,
                    **data_copy,
                },
            )
            self._reset_chunk_ai_state()

    def _is_sentence_split_enabled(self) -> bool:
        return self._config.get_setting(ConfigKeys.AI_SENTENCE_SPLIT_ENABLED, False)

    def _get_wtpsplit_splitter(self):
        if self._sentence_splitter is not None:
            return self._sentence_splitter
        if self._sentence_splitter_error is not None:
            return None
        try:
            from wtpsplit_lite import SaT  # type: ignore

            self._sentence_splitter = SaT("sat-3l-sm")
            return self._sentence_splitter
        except Exception as e:
            self._sentence_splitter_error = str(e)
            app_logger.log_audio_event(
                "AI sentence splitter unavailable",
                {"error": self._sentence_splitter_error},
            )
            return None

    def _split_by_punctuation(self, text: str) -> List[str]:
        parts: List[str] = []
        start = 0
        for match in self._SENTENCE_PUNCT_RE.finditer(text):
            end = match.end()
            segment = text[start:end].strip()
            if segment:
                parts.append(segment)
            start = end
        tail = text[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def _split_by_heuristic(
        self, text: str, min_len: int = 14, max_len: int = 42
    ) -> List[str]:
        cleaned = text.strip().replace("\n", "")
        if not cleaned:
            return []
        out: List[str] = []
        start = 0
        i = 0
        length = len(cleaned)
        while i < length:
            if i - start >= max_len:
                out.append(cleaned[start:i])
                start = i
                continue
            if i - start >= min_len:
                hit = None
                for token in self._SPLIT_BOUNDARIES:
                    if cleaned.startswith(token, i):
                        hit = token
                        break
                if hit:
                    out.append(cleaned[start:i])
                    start = i
                    i += len(hit)
                    continue
            i += 1
        if start < length:
            out.append(cleaned[start:])

        if len(out) >= 2 and len(out[-1]) < 8:
            out[-2] = out[-2] + out[-1]
            out.pop()
        return [segment.strip() for segment in out if segment.strip()]

    def _split_text_for_ai(self, text: str) -> Tuple[List[str], str]:
        cleaned = text.strip().replace("\n", "")
        if not cleaned:
            return [], "empty"

        if self._SENTENCE_PUNCT_RE.search(cleaned):
            return self._split_by_punctuation(cleaned), "punctuation"

        splitter = self._get_wtpsplit_splitter()
        if splitter is not None:
            try:
                parts = [
                    segment.strip()
                    for segment in splitter.split(cleaned)
                    if segment.strip()
                ]
                if parts:
                    return parts, "wtpsplit"
            except Exception as e:
                app_logger.log_audio_event(
                    "AI sentence split failed, falling back",
                    {"error": str(e)},
                )

        return self._split_by_heuristic(cleaned), "heuristic"

    def _group_sentences_3_5(self, sentences: List[str]) -> List[List[str]]:
        count = len(sentences)
        if count == 0:
            return []
        if count <= 5:
            return [sentences]

        sizes: List[int] = []
        remaining = count
        while remaining > 0:
            if remaining <= 5:
                sizes.append(remaining)
                break
            remainder = remaining % 4
            if remainder == 1:
                sizes.extend([3, 4])
                remaining -= 7
            elif remainder == 2:
                sizes.extend([3, 3])
                remaining -= 6
            else:
                sizes.append(4)
                remaining -= 4

        groups: List[List[str]] = []
        index = 0
        for size in sizes:
            groups.append(sentences[index : index + size])
            index += size
        return groups

    def _join_refined_groups(self, parts: List[str]) -> str:
        merged = ""
        for raw_part in parts:
            part = raw_part.strip()
            if not part:
                continue
            if not merged:
                merged = part
                continue
            if self._ASCII_ALNUM_END_RE.search(
                merged
            ) and self._ASCII_ALNUM_START_RE.match(part):
                merged = f"{merged} {part}"
            else:
                merged = merged + part
        return merged.strip()

    def _emit_incremental_ai_text(
        self,
        text: str,
        incremental_event_data: Optional[Dict[str, Any]],
    ) -> None:
        if not incremental_event_data or not text.strip():
            return

        payload = dict(incremental_event_data)
        payload["text"] = text
        payload["incremental"] = True
        payload["incremental_output_used"] = True
        payload["ai_tps"] = self._last_ai_tps
        self._events.emit(Events.AI_INCREMENTAL_TEXT_UPDATED, payload)

    def process_with_ai(
        self,
        text: str,
        record_id: Optional[str] = None,
        incremental_event_data: Optional[Dict[str, Any]] = None,
        update_history: bool = True,
    ) -> str:
        """使用AI优化文本

        Args:
            text: 原始文本
            record_id: 历史记录ID（可选，用于更新历史记录）

        Returns:
            优化后的文本
        """
        # 确定使用哪个record_id：优先使用传入的，fallback到实例变量
        actual_record_id = (
            record_id if record_id is not None else self._current_record_id
        )

        try:
            self._events.emit(Events.AI_PROCESSING_STARTED)

            # 获取配置
            provider = self._config.get_setting(ConfigKeys.AI_PROVIDER, "openrouter")
            model_key = f"ai.{provider}.model_id"
            model = self._config.get_setting(model_key, "anthropic/claude-3-sonnet")
            prompt_template = self._config.get_setting(
                ConfigKeys.AI_PROMPT,
                "Please improve and correct the following text: {text}",
            )

            # 动态获取AI服务
            ai_service = self._get_current_ai_service()
            if not ai_service:
                app_logger.log_audio_event(
                    "AI service not available, skipping optimization", {}
                )
                return text

            sentence_split_enabled = self._is_sentence_split_enabled()
            split_method = "disabled"
            sentence_count = 0
            group_count = 0

            incremental_output_used = False

            if sentence_split_enabled:
                sentences, split_method = self._split_text_for_ai(text)
                sentence_count = len(sentences)
                groups = self._group_sentences_3_5(sentences)
                group_count = len(groups)

                if group_count > 1:
                    refined_parts: List[str] = []
                    for group in groups:
                        group_text = "".join(group).strip()
                        if not group_text:
                            continue
                        refined_part = ai_service.refine_text(
                            group_text, prompt_template, model
                        )
                        refined_parts.append(refined_part)
                        self._last_ai_tps = getattr(ai_service, "_last_tps", 0.0)
                        cumulative_text = self._join_refined_groups(refined_parts)
                        self._emit_incremental_ai_text(
                            cumulative_text,
                            incremental_event_data,
                        )
                        incremental_output_used = True
                    refined_text = (
                        self._join_refined_groups(refined_parts)
                        if refined_parts
                        else text
                    )
                else:
                    refined_text = ai_service.refine_text(text, prompt_template, model)
            else:
                refined_text = ai_service.refine_text(text, prompt_template, model)

            app_logger.log_audio_event(
                "AI sentence split status",
                {
                    "enabled": sentence_split_enabled,
                    "method": split_method,
                    "sentences": sentence_count,
                    "groups": group_count,
                    "incremental_output_used": incremental_output_used,
                },
            )
            self._last_incremental_output_used = (
                self._last_incremental_output_used or incremental_output_used
            )

            # 保存TPS到实例变量
            self._last_ai_tps = getattr(ai_service, "_last_tps", 0.0)

            # 更新历史记录（AI成功）
            if update_history and actual_record_id:
                self._update_ai_status(
                    record_id=actual_record_id,
                    ai_text=refined_text,
                    status="success",
                    error=None,
                    final_text=refined_text,
                )

            # 发送AI处理完成事件
            self._events.emit(
                Events.AI_PROCESSING_COMPLETED,
                {"original": text, "refined": refined_text},
            )

            app_logger.log_audio_event(
                "AI refine completed",
                {
                    "model": model,
                    "original_length": len(text),
                    "refined_length": len(refined_text),
                },
            )

            return refined_text

        except requests.exceptions.Timeout as e:
            error_msg = "AI request timeout - API response too slow"
            app_logger.log_audio_event(
                f"{error_msg} - AI optimization skipped, using original text",
                {"error": str(e), "provider": provider},
            )
            app_logger.log_error(e, "process_with_ai")

            # 更新历史记录（AI失败）
            if update_history and actual_record_id:
                self._update_ai_status(
                    record_id=actual_record_id,
                    ai_text=None,
                    status="failed",
                    error=error_msg,
                    final_text=text,
                )

            self._events.emit(Events.AI_PROCESSING_ERROR, error_msg)
            return text  # 回退到原文本

        except requests.exceptions.ConnectionError as e:
            error_msg = "Network connection failed - check internet connection"
            app_logger.log_audio_event(
                f"{error_msg} - AI optimization skipped, using original text",
                {"error": str(e), "provider": provider},
            )
            app_logger.log_error(e, "process_with_ai")

            # 更新历史记录（AI失败）
            if update_history and actual_record_id:
                self._update_ai_status(
                    record_id=actual_record_id,
                    ai_text=None,
                    status="failed",
                    error=error_msg,
                    final_text=text,
                )

            self._events.emit(Events.AI_PROCESSING_ERROR, error_msg)
            return text

        except OpenRouterAPIError as e:
            error_str = str(e).lower()
            if "timeout" in error_str:
                error_msg = "AI API timeout after retries"
            elif "429" in str(e) or "rate limit" in error_str:
                error_msg = "AI API rate limit exceeded"
            elif "401" in str(e) or "unauthorized" in error_str:
                error_msg = "AI API key invalid or unauthorized"
            else:
                error_msg = "AI API error"

            # 明确日志：AI 优化已跳过
            app_logger.log_audio_event(
                f"{error_msg} - AI optimization skipped, using original text",
                {"error": str(e), "provider": provider},
            )
            app_logger.log_error(e, "process_with_ai")

            # 更新历史记录（AI失败）
            if update_history and actual_record_id:
                self._update_ai_status(
                    record_id=actual_record_id,
                    ai_text=None,
                    status="failed",
                    error=error_msg,
                    final_text=text,
                )

            self._events.emit(Events.AI_PROCESSING_ERROR, error_msg)
            return text

        except Exception as e:
            error_msg = f"Unknown AI processing error: {type(e).__name__}"
            app_logger.log_audio_event(
                f"{error_msg} - AI optimization skipped, using original text",
                {"error": str(e), "provider": provider},
            )
            app_logger.log_error(e, "process_with_ai")

            # 更新历史记录（AI失败）
            if update_history and actual_record_id:
                self._update_ai_status(
                    record_id=actual_record_id,
                    ai_text=None,
                    status="failed",
                    error=error_msg,
                    final_text=text,
                )

            self._events.emit(Events.AI_PROCESSING_ERROR, error_msg)
            return text

    def is_ai_enabled(self) -> bool:
        """AI是否启用"""
        return self._config.get_setting(ConfigKeys.AI_ENABLED, True)

    def _get_current_ai_service(self) -> Optional[IAIService]:
        """根据当前配置动态获取 AI service 实例 - 使用 AIClientFactory

        Returns:
            AI服务实例，失败返回None
        """
        try:
            # 使用工厂从配置创建客户端（统一逻辑）
            return AIClientFactory.create_from_config(self._config)

        except Exception as e:
            app_logger.log_error(e, "_get_current_ai_service")
            return None

    def _update_ai_status(
        self,
        record_id: str,
        ai_text: Optional[str],
        status: str,
        error: Optional[str],
        final_text: str,
    ) -> None:
        """更新历史记录的AI处理状态

        Args:
            record_id: 历史记录ID
            ai_text: AI优化后的文本（成功时）
            status: AI状态 ("success" | "failed" | "skipped")
            error: 错误信息（失败时）
            final_text: 最终文本（成功时为AI文本，失败/跳过时为转录文本）
        """
        try:
            # 获取现有记录
            record = self._history_service.get_record_by_id(record_id)
            if not record:
                app_logger.log_audio_event(
                    "Cannot update AI status - record not found",
                    {"record_id": record_id},
                )
                return

            # 获取AI提供商
            provider = self._config.get_setting(ConfigKeys.AI_PROVIDER, "openrouter")

            # 更新AI相关字段
            record.ai_optimized_text = ai_text
            record.ai_provider = provider if status == "success" else None
            record.ai_status = status
            record.ai_error = error
            record.final_text = final_text

            # 更新现有记录（使用 UPDATE 而不是 INSERT）
            update_success = self._history_service.update_record(record)

            if update_success:
                app_logger.log_audio_event(
                    "AI status updated in history",
                    {
                        "record_id": record_id,
                        "status": status,
                        "ai_text_length": len(ai_text) if ai_text else 0,
                    },
                )
            else:
                app_logger.log_audio_event(
                    "Failed to update AI status in history", {"record_id": record_id}
                )

        except Exception as e:
            app_logger.log_error(e, "_update_ai_status")
