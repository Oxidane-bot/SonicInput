"""输入控制器

负责文本输入到活动窗口。
"""

import time

from ...utils import app_logger, logger
from ..base.lifecycle_component import LifecycleComponent
from ..interfaces import (
    IConfigService,
    IEventService,
    IInputController,
    IInputService,
    IStateManager,
)
from ..interfaces.state import AppState
from ..services.events import Events
from .base_controller import BaseController
from .text_diff_helper import calculate_text_diff


class InputController(LifecycleComponent, BaseController, IInputController):
    """输入控制器实现

    职责：
    - 处理文本输入
    - 管理输入方法配置
    - 记录性能指标
    - 通过 EventBus 发送输入事件
    """

    def __init__(
        self,
        input_service: IInputService,
        config_service: IConfigService,
        event_service: IEventService,
        state_manager: IStateManager,
    ):
        # Initialize LifecycleComponent first
        LifecycleComponent.__init__(self, "InputController")

        # Initialize BaseController
        BaseController.__init__(self, config_service, event_service, state_manager)

        # Controller-specific services
        self._input_service = input_service

        # Realtime 模式状态追踪（用于实时文本差量更新）
        self._last_realtime_text: str = ""  # 上一次输入的实时文本
        self._last_incremental_ai_text: str = ""
        self._last_streaming_ai_text: str = ""

        # NOTE: Event listener registration moved to _do_start() for hot reload support
        # NOTE: Initialization logging moved to _do_start() for hot reload support

    def _register_event_listeners(self) -> None:
        """Register event listeners for input events

        NOTE: Called from _do_start() to support hot reload.
        Uses _track_listener() to enable proper cleanup.
        """
        # AI 处理完成的文本（chunked 模式）
        self._track_listener(Events.AI_PROCESSED_TEXT, self._on_text_ready_for_input)
        self._track_listener(
            Events.AI_INCREMENTAL_TEXT_UPDATED,
            self._on_ai_incremental_text_updated,
        )
        self._track_listener(
            Events.AI_STREAMING_TOKEN_RECEIVED, self._on_ai_streaming_token
        )

        # 实时文本更新（realtime 模式）
        self._track_listener(
            Events.REALTIME_TEXT_UPDATED, self._on_realtime_text_updated
        )

        # 录音开始/停止事件（用于重置状态）
        self._track_listener(Events.RECORDING_STARTED, self._on_recording_started)
        self._track_listener(Events.RECORDING_STOPPED, self._on_recording_stopped)

        # 转录错误事件（用于恢复剪贴板）
        self._track_listener(
            Events.TRANSCRIPTION_ERROR, self._on_transcription_error_restore_clipboard
        )

    def _on_text_ready_for_input(self, data: dict) -> None:
        """处理准备好输入的文本事件

        Args:
            data: 包含 text、性能统计数据和 streaming_mode
        """
        # 从事件数据中获取实际的 streaming_mode，而不是依赖本地标志
        streaming_mode = data.get("streaming_mode", "chunked")
        streaming_output_used = data.get("streaming_output_used", False)

        # 关键修复：realtime模式下，文本已经在录音过程中实时输入了
        # 不应该在录音结束后再输入一遍
        if streaming_mode == "realtime":
            app_logger.log_audio_event(
                "Skipping final text input in realtime mode (already input during recording)",
                {
                    "text_length": len(data.get("text", "")),
                    "streaming_mode": streaming_mode,
                },
            )

            # 关键修复：realtime 模式下也要恢复剪贴板
            if hasattr(self._input_service, "stop_recording_mode"):
                self._input_service.stop_recording_mode()

            # 关键修复：即使跳过文本输入，也要触发完成事件和设置状态
            # 让 RecordingOverlay 能够正常隐藏
            self._events.emit(Events.TEXT_INPUT_COMPLETED, "")
            self._state_manager.set_app_state(AppState.IDLE)

            # 记录整体性能日志
            self._log_performance(data)
            return

        text = data.get("text", "")
        incremental_output_used = data.get("incremental_output_used", False)

        if streaming_output_used:
            self._apply_live_text_update(
                new_text=text,
                previous_text=self._last_streaming_ai_text,
                update_state_attr="_last_streaming_ai_text",
                shrink_guard_ratio=None,
                log_context="AI streaming final text",
            )
            self._finish_text_input(text, data)
        elif incremental_output_used:
            self._apply_live_text_update(
                new_text=text,
                previous_text=self._last_incremental_ai_text,
                update_state_attr="_last_incremental_ai_text",
                shrink_guard_ratio=None,
                log_context="AI final text",
            )
            self._finish_text_input(text, data)
        elif text.strip():
            self.input_text(text)

            # 记录整体性能日志
            self._log_performance(data)
        else:
            # 空文本处理：仍需触发完成事件，让悬浮窗正常关闭
            app_logger.log_audio_event(
                "Empty text received, skipping input but triggering completion",
                {"data_keys": list(data.keys()), "streaming_mode": streaming_mode},
            )

            # 空文本时也要恢复剪贴板
            if hasattr(self._input_service, "stop_recording_mode"):
                self._input_service.stop_recording_mode()

            # 触发完成事件
            self._events.emit(Events.TEXT_INPUT_COMPLETED, "")
            # 设置状态为 IDLE
            self._state_manager.set_app_state(AppState.IDLE)
            # 记录性能日志
            self._log_performance(data)

    def _finish_text_input(self, text: str, data: dict) -> None:
        if hasattr(self._input_service, "stop_recording_mode"):
            self._input_service.stop_recording_mode()

        self._events.emit(Events.TEXT_INPUT_COMPLETED, text)
        self._state_manager.set_app_state(AppState.IDLE)
        self._log_performance(data)

    def _apply_live_text_update(
        self,
        new_text: str,
        previous_text: str,
        update_state_attr: str,
        log_context: str,
        shrink_guard_ratio: float | None,
    ) -> None:
        if new_text == previous_text or (not new_text and not previous_text):
            return

        app_logger.log_audio_event(
            f"{log_context} update received",
            {
                "old_text": previous_text[:30] + "..."
                if len(previous_text) > 30
                else previous_text,
                "new_text": new_text[:30] + "..." if len(new_text) > 30 else new_text,
            },
        )

        if (
            shrink_guard_ratio is not None
            and previous_text
            and len(new_text) < len(previous_text) * shrink_guard_ratio
        ):
            app_logger.log_audio_event(
                f"{log_context} shrank unexpectedly, skipping diff",
                {
                    "old_length": len(previous_text),
                    "new_length": len(new_text),
                    "shrink_guard_ratio": shrink_guard_ratio,
                },
            )
            return

        backspace_count, text_to_append = calculate_text_diff(previous_text, new_text)

        app_logger.log_audio_event(
            f"{log_context} diff calculated",
            {
                "backspace_count": backspace_count,
                "append_text": text_to_append[:30] + "..."
                if len(text_to_append) > 30
                else text_to_append,
            },
        )

        if backspace_count > 0:
            self._input_service.input_text("\b" * backspace_count)

        if text_to_append:
            self._input_service.input_text(text_to_append)

        setattr(self, update_state_attr, new_text)

    def input_text(self, text: str) -> bool:
        """输入文本

        Args:
            text: 要输入的文本

        Returns:
            是否输入成功
        """
        try:
            self._events.emit(Events.TEXT_INPUT_STARTED, text)

            input_start = time.time()
            success = self._input_service.input_text(text)
            input_duration = time.time() - input_start

            if success:
                self._events.emit(Events.TEXT_INPUT_COMPLETED, text)

                # 文本输入成功后，恢复原始剪贴板内容
                # 修复：将剪贴板恢复从 TRANSCRIPTION_COMPLETED 移到这里，确保在文本输入完成后才恢复
                if hasattr(self._input_service, "stop_recording_mode"):
                    self._input_service.stop_recording_mode()

                # 重置应用状态为 IDLE（完成整个语音输入流程）
                self._state_manager.set_app_state(AppState.IDLE)

                app_logger.log_audio_event(
                    "Text input completed",
                    {
                        "duration": f"{input_duration:.3f}s",
                        "text_length": len(text),
                        "text": text[:50] + "..." if len(text) > 50 else text,
                    },
                )
                return True
            else:
                self._events.emit(Events.TEXT_INPUT_ERROR, "Failed to input text")

                # 文本输入失败时也要恢复剪贴板
                if hasattr(self._input_service, "stop_recording_mode"):
                    self._input_service.stop_recording_mode()

                # 即使失败也要重置状态，否则无法进行下一次录音
                self._state_manager.set_app_state(AppState.IDLE)

                return False

        except Exception as e:
            app_logger.log_error(e, "input_text")
            self._events.emit(Events.TEXT_INPUT_ERROR, str(e))

            # 异常时也要恢复剪贴板
            if hasattr(self._input_service, "stop_recording_mode"):
                self._input_service.stop_recording_mode()

            # 异常时也要重置状态
            self._state_manager.set_app_state(AppState.IDLE)

            return False

    def set_preferred_method(self, method: str) -> None:
        """设置首选输入方法

        Args:
            method: 输入方法 (clipboard 或 sendinput)
        """
        self._input_service.set_preferred_method(method)
        self._config.set_setting("input.preferred_method", method)

        app_logger.log_audio_event("Input method changed", {"method": method})

    def _log_performance(self, data: dict) -> None:
        """记录整体性能日志

        Args:
            data: 包含各阶段性能数据
        """
        try:
            audio_duration = data.get("audio_duration", 0.0)
            recording_stop_time = data.get("recording_stop_time", time.time())
            transcribe_duration = data.get("transcribe_duration", 0.0)
            ai_tps = data.get("ai_tps", 0.0)

            # 计算用户等待时间（从录音结束到现在）
            wait_time = time.time() - recording_stop_time

            # 使用统一的性能日志API
            logger.performance(
                "streaming_voice_input",
                wait_time,
                audio_duration=audio_duration,
                details={
                    "wait_time": f"{wait_time:.2f}s",
                    "final_chunk_transcribe": f"{transcribe_duration:.2f}s",
                    "ai_tps": f"{ai_tps:.2f}" if ai_tps > 0 else "N/A",
                },
            )

            app_logger.log_audio_event(
                "Voice input completed",
                {
                    "audio_duration": f"{audio_duration:.1f}s",
                    "wait_time": f"{wait_time:.2f}s",
                },
            )

        except Exception as e:
            app_logger.log_error(e, "_log_performance")

    def _on_recording_started(self, data=None) -> None:
        """处理录音开始事件

        启动录音模式（保存原始剪贴板）
        重置 realtime 模式状态，准备接收新的实时文本更新
        """
        # 重置 realtime 文本追踪（用于实时文本差量更新）
        self._last_realtime_text = ""
        self._last_incremental_ai_text = ""
        self._last_streaming_ai_text = ""

        # 启动录音模式：SmartTextInput会保存原始剪贴板，并在录音期间禁用中途restore
        try:
            if hasattr(self._input_service, "start_recording_mode"):
                self._input_service.start_recording_mode()
        except Exception as e:
            app_logger.log_error(e, "start_recording_mode")

        app_logger.log_audio_event(
            "InputController: Recording started, clipboard backup initiated", {}
        )

    def _on_recording_stopped(self, data=None) -> None:
        """处理录音停止事件

        记录录音停止日志，剪贴板恢复会在文本输入完成后自动处理
        """
        app_logger.log_audio_event(
            "InputController: Recording stopped",
            {"last_realtime_text_length": len(self._last_realtime_text)},
        )

    def _on_realtime_text_updated(self, data: dict) -> None:
        """处理实时文本更新事件（realtime 模式）

        使用差量算法计算文本差异，智能更新输入的文本：
        1. 计算新文本与上次文本的差异
        2. 使用退格键删除变化的部分
        3. 输入新的差异部分

        Args:
            data: 包含 'text' 和 'timestamp' 的字典
        """
        try:
            new_text = data.get("text", "")
            self._apply_live_text_update(
                new_text=new_text,
                previous_text=self._last_realtime_text,
                update_state_attr="_last_realtime_text",
                shrink_guard_ratio=0.5,
                log_context="Realtime text",
            )

        except Exception as e:
            app_logger.log_error(e, "_on_realtime_text_updated")

    def _on_ai_incremental_text_updated(self, data: dict) -> None:
        """处理 AI 分组完成后的增量文本更新。"""
        try:
            if data.get("streaming_output_used", False):
                return
            self._apply_live_text_update(
                new_text=data.get("text", ""),
                previous_text=self._last_incremental_ai_text,
                update_state_attr="_last_incremental_ai_text",
                shrink_guard_ratio=None,
                log_context="AI incremental text",
            )
        except Exception as e:
            app_logger.log_error(e, "_on_ai_incremental_text_updated")

    def _on_ai_streaming_token(self, data: dict) -> None:
        """处理 AI 流式事件，使用累计文本做差量更新。"""
        try:
            streaming_text = data.get("streaming_text", "")
            if not streaming_text and not self._last_streaming_ai_text:
                return
            self._apply_live_text_update(
                new_text=streaming_text,
                previous_text=self._last_streaming_ai_text,
                update_state_attr="_last_streaming_ai_text",
                shrink_guard_ratio=None,
                log_context="AI streaming text",
            )
        except Exception as e:
            app_logger.log_error(e, "_on_ai_streaming_token")

    def _on_transcription_error_restore_clipboard(self, error_msg: str) -> None:
        """处理转录错误事件 - 恢复剪贴板

        转录失败时也要恢复剪贴板，避免用户原始剪贴板内容丢失

        Args:
            error_msg: 错误信息
        """
        try:
            # 即使转录失败，也要恢复剪贴板
            if hasattr(self._input_service, "stop_recording_mode"):
                self._input_service.stop_recording_mode()
                app_logger.log_audio_event(
                    "Clipboard restore triggered after transcription error",
                    {"error": error_msg[:100] if error_msg else "Unknown error"},
                )
        except Exception as e:
            app_logger.log_error(e, "_on_transcription_error_restore_clipboard")

    # ========== Lifecycle Methods (NEW API) ==========

    def _do_start(self) -> bool:
        """启动输入控制器

        Returns:
            总是返回 True
        """
        try:
            # Register event listeners (supports hot reload)
            self._register_event_listeners()

            # Log initialization
            self._log_initialization()

            app_logger.log_audio_event(
                "InputController started (event-driven mode)",
                {"component": "InputController"},
            )
            return True
        except Exception as e:
            app_logger.log_error(e, "InputController._do_start")
            return False

    def _do_stop(self) -> bool:
        """停止输入控制器

        清理状态，确保剪贴板恢复。

        Returns:
            总是返回 True
        """
        try:
            # Cleanup event listeners (supports hot reload)
            self._cleanup_event_listeners()

            # 重置 realtime 文本追踪
            self._last_realtime_text = ""
            self._last_incremental_ai_text = ""

            # 确保剪贴板恢复（防止资源泄漏）
            if hasattr(self._input_service, "stop_recording_mode"):
                self._input_service.stop_recording_mode()

            app_logger.log_audio_event(
                "InputController stopped and cleaned up",
                {"component": "InputController"},
            )
            return True
        except Exception as e:
            app_logger.log_error(e, "InputController._do_stop")
            return False
