"""UI事件桥接器实现

负责：
- UI组件事件监听管理
- UI状态更新桥接
- 向后兼容性支持
- UI与应用逻辑解耦
"""

from typing import Any, Callable, Dict

from ...utils import app_logger
from ..interfaces import IEventService
from .events import Events


class UIEventBridge:
    """UI事件桥接器实现

    职责：
    - 管理UI组件与应用逻辑之间的事件通信
    - 提供向后兼容的UI接口
    - 解耦UI层和业务逻辑层
    - 支持自定义事件处理器注册
    """

    def __init__(self, event_service: IEventService):
        """初始化UI事件桥接器

        Args:
            event_service: 事件服务
        """
        self.events = event_service
        self._overlay = None
        self._event_handlers: Dict[str, Callable] = {}
        self._is_listening = False

        app_logger.log_audio_event("UIEventBridge initialized", {})

    def setup_overlay_events(self, overlay) -> None:
        """设置悬浮窗事件监听"""
        if overlay is None:
            return

        self._overlay = overlay

        # 如果还没有开始监听，则开始监听
        if not self._is_listening:
            self._setup_event_listeners()
            self._is_listening = True

        app_logger.log_audio_event("Overlay events setup completed", {})

    def remove_overlay_events(self) -> None:
        """移除悬浮窗事件监听"""
        self._overlay = None
        # 注意：不移除事件监听器，因为其他地方可能还在使用
        app_logger.log_audio_event("Overlay events removed", {})

    def register_custom_event_handler(self, event_name: str, handler: Callable) -> None:
        """注册自定义事件处理器"""
        self._event_handlers[event_name] = handler
        app_logger.log_audio_event(
            "Custom event handler registered", {"event_name": event_name}
        )

    def handle_recording_started(self, data: Any = None) -> None:
        """处理录音开始事件"""
        app_logger.log_audio_event(
            "UIEventBridge: handle_recording_started called",
            {"has_overlay": self._overlay is not None},
        )

        if self._overlay:
            app_logger.log_audio_event(
                "UIEventBridge: Calling overlay.show_recording()", {}
            )
            self._overlay.show_recording()
        else:
            app_logger.log_audio_event(
                "UIEventBridge: WARNING - overlay is None, cannot show recording", {}
            )

        # 执行自定义处理器
        self._execute_custom_handler(Events.RECORDING_STARTED, data)

    def handle_recording_stopped(self, data: dict) -> None:
        """处理录音停止事件"""
        if self._overlay:
            self._overlay.show_processing()

        # 执行自定义处理器
        self._execute_custom_handler(Events.RECORDING_STOPPED, data)

    def handle_model_loading_started(self, data: Any = None) -> None:
        """模型加载开始时切到 'loading model' 状态。

        覆盖场景：lazy load 在首次按热键时触发，用户已经在说话，
        但模型还没准备好（特别是首次启动需要下载几百 MB 模型）。
        显示"Loading model..."避免用户以为软件没反应。
        """
        if not self._overlay:
            return
        # 仅当 overlay 显示在 recording 状态时才覆盖（避免抢走 idle/processing 状态）
        view_model = getattr(self._overlay, "view_model", None)
        current_state = getattr(view_model, "_state", None) if view_model else None
        if current_state in ("recording", "idle", None):
            if hasattr(self._overlay, "show_model_loading"):
                self._overlay.show_model_loading()

    def handle_model_loading_completed(self, data: Any = None) -> None:
        """模型加载完成 → 如果还在录音，恢复 recording 状态"""
        if not self._overlay:
            return
        view_model = getattr(self._overlay, "view_model", None)
        current_state = getattr(view_model, "_state", None) if view_model else None
        if current_state == "model_loading":
            # 检查是否还在录音
            still_recording = False
            try:
                from ..interfaces.state import RecordingState

                state_manager = getattr(self._overlay, "_state_manager", None)
                if state_manager is not None:
                    still_recording = state_manager.get_recording_state() in (
                        RecordingState.STARTING,
                        RecordingState.RECORDING,
                    )
            except Exception:
                pass
            if still_recording:
                self._overlay.show_recording()
            else:
                self._overlay.hide_recording()

    def handle_ai_processing_started(self, data: Any = None) -> None:
        """处理AI处理开始事件"""
        if self._overlay:
            self._overlay.set_status_text("AI Processing...")

        # 执行自定义处理器
        self._execute_custom_handler(Events.AI_PROCESSING_STARTED, data)

    def handle_ai_processing_completed(self, data: Any = None) -> None:
        """处理AI处理完成事件

        Visual transition is handled when TEXT_INPUT_COMPLETED fires next; this
        handler only forwards to any custom handler registered for the event.
        """
        self._execute_custom_handler(Events.AI_PROCESSING_COMPLETED, data)

    def handle_text_input_completed(self, text: str) -> None:
        """处理文本输入完成事件"""
        if self._overlay:
            self._overlay.show_completed(delay_ms=500)

        # 执行自定义处理器
        self._execute_custom_handler(Events.TEXT_INPUT_COMPLETED, text)

    def handle_error(self, error_msg: str) -> None:
        """处理错误事件

        区分AI错误和其他错误：
        - AI错误：显示警告状态（橙色），流程会继续，使用原始转录文本
        - 其他错误：显示错误状态（红色），流程可能中断
        """
        if self._overlay:
            # 检查是否是AI相关的错误（但流程会继续）
            if "AI" in error_msg or "processing" in error_msg.lower():
                # AI错误：显示警告色（橙色），延迟1.5秒隐藏
                self._overlay.show_warning(delay_ms=1500)
                app_logger.log_audio_event(
                    "AI error handled - showing warning state", {"error_msg": error_msg}
                )
            else:
                # 其他错误：显示错误色（红色），延迟2秒隐藏
                self._overlay.show_error(delay_ms=2000)
                app_logger.log_audio_event(
                    "Critical error handled - showing error state",
                    {"error_msg": error_msg},
                )

        # 执行自定义处理器
        self._execute_custom_handler("error", error_msg)

    def handle_audio_level_update(self, level: float) -> None:
        """处理音频级别更新事件"""
        if self._overlay:
            self._overlay.update_audio_level(level)

        # 执行自定义处理器
        self._execute_custom_handler(Events.AUDIO_LEVEL_UPDATE, level)

    def handle_realtime_text_update(self, data: dict) -> None:
        """处理实时文本更新事件

        注意：根据用户需求，realtime 模式下不在 overlay 中显示实时文本。
        文本会直接通过 InputController 实时输入到应用程序。

        Args:
            data: 包含 'text' 和 'timestamp' 的字典
        """
        # Realtime 模式：不在 overlay 中显示文本（用户需求）
        # 只记录日志和执行自定义处理器

        app_logger.log_audio_event(
            "Realtime text event received (not displaying in overlay)",
            {
                "text_length": len(data.get("text", "")),
                "text_preview": data.get("text", "")[:30],
            },
        )

        # 执行自定义处理器
        self._execute_custom_handler(Events.REALTIME_TEXT_UPDATED, data)

    def _setup_event_listeners(self) -> None:
        """设置事件监听器"""
        # 成功事件
        self.events.on(Events.RECORDING_STARTED, self.handle_recording_started)
        self.events.on(Events.RECORDING_STOPPED, self.handle_recording_stopped)
        self.events.on(Events.AI_PROCESSING_STARTED, self.handle_ai_processing_started)
        self.events.on(
            Events.AI_PROCESSING_COMPLETED, self.handle_ai_processing_completed
        )
        self.events.on(Events.TEXT_INPUT_COMPLETED, self.handle_text_input_completed)
        self.events.on(Events.AUDIO_LEVEL_UPDATE, self.handle_audio_level_update)

        # Realtime 转录更新事件
        self.events.on(Events.REALTIME_TEXT_UPDATED, self.handle_realtime_text_update)

        # 模型加载事件（首次按热键触发 lazy load 时给用户反馈）
        self.events.on(Events.MODEL_LOADING_STARTED, self.handle_model_loading_started)
        self.events.on(
            Events.MODEL_LOADING_COMPLETED, self.handle_model_loading_completed
        )
        # 加载失败走通用 error 路径
        self.events.on(Events.MODEL_LOADING_FAILED, self.handle_error)

        # 错误事件
        self.events.on(Events.TRANSCRIPTION_ERROR, self.handle_error)
        self.events.on(Events.AI_PROCESSING_ERROR, self.handle_error)
        self.events.on(Events.TEXT_INPUT_ERROR, self.handle_error)

        app_logger.log_audio_event("Event listeners setup completed", {})

    def _execute_custom_handler(self, event_name: str, data: Any) -> None:
        """执行自定义事件处理器"""
        if event_name in self._event_handlers:
            try:
                self._event_handlers[event_name](data)
            except Exception as e:
                app_logger.log_error(e, f"custom_event_handler_{event_name}")

    @property
    def has_overlay(self) -> bool:
        """检查是否有关联的悬浮窗"""
        return self._overlay is not None
