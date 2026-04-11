"""录音控制器

负责录音的启动、停止和状态管理。
"""

import inspect
import time
import uuid
from typing import Optional

from ...utils import ErrorMessageTranslator, app_logger
from ..base.lifecycle_component import LifecycleComponent
from ..interfaces import (
    IAudioService,
    IConfigService,
    IEventService,
    IRecordingController,
    ISpeechService,
    IStateManager,
)
from ..interfaces.state import RecordingState
from ..services.config import ConfigKeys
from ..services.events import Events
from ..services.storage import HistoryStorageService
from .audio_callback_router import AudioCallbackRouter
from .logging_helper import ControllerLogging
from .streaming_mode_manager import StreamingModeManager


class RecordingController(LifecycleComponent, IRecordingController):
    """录音控制器实现

    职责：
    - 管理录音的启动和停止
    - 协调 StreamingModeManager 和 AudioCallbackRouter
    - 管理录音状态转换
    - 发送录音事件
    - 保存音频到历史记录
    """

    def __init__(
        self,
        audio_service: IAudioService,
        config_service: IConfigService,
        event_service: IEventService,
        state_manager: IStateManager,
        speech_service: ISpeechService,
        history_service: HistoryStorageService,
    ):
        super().__init__("RecordingController")

        self._audio_service = audio_service
        self._config = config_service
        self._events = event_service
        self._state_manager = (
            state_manager  # Renamed to avoid conflict with LifecycleComponent._state
        )
        self._speech_service = speech_service
        self._history_service = history_service

        # 录音时长追踪（用于性能统计）
        self._recording_start_time: Optional[float] = None
        self._recording_stop_time: Optional[float] = None
        self._last_audio_duration: float = 0.0

        # 创建子组件
        self._streaming_manager = StreamingModeManager(
            config_service=config_service,
            speech_service=speech_service,
        )

        self._callback_router = AudioCallbackRouter(
            audio_service=audio_service,
            event_service=event_service,
            speech_service=speech_service,
            history_service=history_service,
        )

        ControllerLogging.log_initialization("RecordingController")

    @property
    def streaming_manager(self):
        """获取流式模式管理器（供其他控制器共享）"""
        return self._streaming_manager

    def _do_start(self) -> bool:
        """启动录音控制器

        Returns:
            True 如果启动成功
        """
        # 启动子组件
        if not self._streaming_manager.start():
            app_logger.log_error(None, "Failed to start StreamingModeManager")
            return False

        if not self._callback_router.start():
            app_logger.log_error(None, "Failed to start AudioCallbackRouter")
            self._streaming_manager.stop()
            return False

        app_logger.log_audio_event(
            "RecordingController started", {"component": self._component_name}
        )
        return True

    def _do_stop(self) -> bool:
        """停止录音控制器

        Returns:
            True 如果停止成功
        """
        # 停止子组件
        self._callback_router.stop()
        self._streaming_manager.stop()

        app_logger.log_audio_event(
            "RecordingController stopped", {"component": self._component_name}
        )
        return True

    def start_recording(self, device_id: Optional[int] = None) -> None:
        """开始录音"""
        if self.is_recording() or self._state_manager.is_processing():
            app_logger.log_audio_event(
                "Cannot start recording - already recording or processing",
                {
                    "is_recording": self.is_recording(),
                    "is_processing": self._state_manager.is_processing(),
                    "app_state": self._state_manager.get_app_state().name,
                    "recording_state": self._state_manager.get_recording_state().name,
                },
            )
            return

        try:
            # 从配置获取设备ID
            if device_id is None:
                device_id = self._config.get_setting(ConfigKeys.AUDIO_DEVICE_ID)

            # 获取当前流式模式
            streaming_mode = self._streaming_manager.get_current_mode()
            provider = self._config.get_setting(
                ConfigKeys.TRANSCRIPTION_PROVIDER, "local"
            )

            app_logger.log_audio_event(
                "Recording starting with streaming mode",
                {"mode": streaming_mode, "provider": provider},
            )

            if (
                provider == "local"
                and streaming_mode == "realtime"
                and not self._ensure_local_realtime_model_ready()
            ):
                return

            # 启动流式会话（如果支持）
            if streaming_mode != "disabled":
                if not self._streaming_manager.start_streaming_session():
                    app_logger.log_audio_event(
                        "Failed to start streaming session",
                        {"mode": streaming_mode, "provider": provider},
                    )
                    self._events.emit(
                        Events.RECORDING_ERROR,
                        "Unable to start streaming transcription session",
                    )
                    return

            # 根据模式注册回调
            if streaming_mode == "chunked":
                self._callback_router.register_chunked_callback()
            elif streaming_mode == "realtime":
                self._callback_router.register_realtime_callback()
            else:  # disabled
                self._callback_router.register_basic_callback()

            # 启动录音
            self._audio_service.start_recording(device_id)

            # 记录录音开始时间
            self._recording_start_time = time.time()

            # 更新状态
            ControllerLogging.log_state_change(
                "recording",
                RecordingState.IDLE,
                RecordingState.RECORDING,
                {"device_id": device_id},
            )
            self._state_manager.set_recording_state(RecordingState.RECORDING)

            # 发送事件
            self._events.emit(Events.RECORDING_STARTED)

            app_logger.log_audio_event(
                "Recording started",
                {
                    "device_id": device_id,
                    "streaming_mode": streaming_mode,
                    "streaming_enabled": streaming_mode != "disabled",
                },
            )

        except Exception as e:
            app_logger.log_error(e, "start_recording")
            # 转换为用户友好消息
            error_info = ErrorMessageTranslator.translate(e, "recording")
            self._events.emit(Events.RECORDING_ERROR, error_info["user_message"])

    def _ensure_local_realtime_model_ready(self) -> bool:
        """确保本地 realtime 录音在开始前已有可用模型。"""
        if not self._speech_service or not hasattr(
            self._speech_service, "is_model_loaded"
        ):
            self._events.emit(
                Events.RECORDING_ERROR,
                "Local speech service is not available for realtime recording",
            )
            return False

        if self._speech_service.is_model_loaded:
            return True

        if not hasattr(self._speech_service, "load_model"):
            self._events.emit(
                Events.RECORDING_ERROR,
                "Local speech service cannot load realtime model",
            )
            return False

        model_name = self._config.get_setting(
            ConfigKeys.TRANSCRIPTION_LOCAL_MODEL, "paraformer"
        )
        app_logger.log_audio_event(
            "Loading local model before realtime recording",
            {"model_name": model_name},
        )

        try:
            load_model_signature = inspect.signature(self._speech_service.load_model)
            if "download_if_missing" in load_model_signature.parameters:
                load_success = self._speech_service.load_model(
                    model_name,
                    download_if_missing=True,
                )
            else:
                load_success = self._speech_service.load_model(model_name)

            if load_success:
                return True
        except Exception as e:
            app_logger.log_error(e, "ensure_local_realtime_model_ready")
            self._events.emit(
                Events.RECORDING_ERROR,
                "Failed to load local model for realtime recording",
            )
            return False

        self._events.emit(
            Events.RECORDING_ERROR,
            "Failed to load local model for realtime recording",
        )
        return False

    def stop_recording(self) -> None:
        """停止录音"""
        if not self.is_recording():
            app_logger.log_audio_event("No recording in progress", {})
            return

        try:
            app_logger.log_audio_event("Stopping recording", {})

            # 停止录音服务（返回音频数据和实际时长）
            audio_data, actual_duration = self._audio_service.stop_recording()

            # 记录停止时间
            self._recording_stop_time = time.time()
            wall_clock_duration = self._recording_stop_time - self._recording_start_time

            # 使用实际音频时长（而非墙上时间）
            self._last_audio_duration = actual_duration

            # 记录时长差异（用于诊断）
            if abs(wall_clock_duration - actual_duration) > 1.0:
                app_logger.log_audio_event(
                    "Duration mismatch detected",
                    {
                        "actual_audio_duration": actual_duration,
                        "wall_clock_duration": wall_clock_duration,
                        "difference_seconds": abs(
                            wall_clock_duration - actual_duration
                        ),
                    },
                )

            # 更新状态
            ControllerLogging.log_state_change(
                "recording",
                RecordingState.RECORDING,
                RecordingState.IDLE,
                {"duration": f"{self._last_audio_duration:.1f}s"},
            )
            self._state_manager.set_recording_state(RecordingState.IDLE)

            # 发送录音停止事件
            self._events.emit(Events.RECORDING_STOPPED, len(audio_data))

            # 提交最后音频块（如果是本地提供商）
            self._submit_final_audio(audio_data)

            # 注意：不在这里停止流式会话！
            # transcription_controller 会在获取转录结果时调用 stop_streaming()
            # 如果在这里提前停止，pending chunks 会被清空，导致转录失败
            # 关键修复：移除此处的 stop_streaming_session() 调用
            # self._streaming_manager.stop_streaming_session()

            # 注销回调
            self._callback_router.unregister_callbacks()

            # 保存音频并发送转录请求
            self._save_and_request_transcription(audio_data)

            app_logger.log_audio_event(
                "Recording stopped",
                {
                    "audio_duration": f"{self._last_audio_duration:.1f}s",
                    "final_chunk_length": len(audio_data),
                },
            )

        except Exception as e:
            ControllerLogging.log_state_change(
                "recording",
                RecordingState.RECORDING,
                RecordingState.IDLE,
                {"reason": "error_recovery"},
                is_forced=True,
            )
            self._state_manager.set_recording_state(RecordingState.IDLE)
            app_logger.log_error(e, "stop_recording")
            self._events.emit(Events.RECORDING_ERROR, str(e))

    def toggle_recording(self) -> None:
        """切换录音状态"""
        if self.is_recording():
            self.stop_recording()
        else:
            self.start_recording()

    def is_recording(self) -> bool:
        """是否正在录音"""
        return self._state_manager.get_recording_state() == RecordingState.RECORDING

    def get_last_audio_duration(self) -> float:
        """获取最后一次录音的时长（用于性能统计）"""
        return self._last_audio_duration

    def get_recording_stop_time(self) -> Optional[float]:
        """获取最后一次录音停止时间（用于性能统计）"""
        return self._recording_stop_time

    def _submit_final_audio(self, audio_data) -> None:
        """提交最后的音频块到流式转录

        Args:
            audio_data: 完整音频数据（用于 realtime 模式）
        """
        # 获取当前流式模式
        streaming_mode = self._streaming_manager.get_current_mode()

        # 如果流式模式被禁用，跳过
        if streaming_mode == "disabled":
            return

        if not self._speech_service:
            app_logger.log_audio_event(
                "Cannot add final audio - speech service not available", {}
            )
            return

        try:
            if streaming_mode == "realtime":
                # realtime 模式的文本已在录音过程中持续推送并输入。
                # 停止时重新喂入完整音频会导致重复识别和历史最终文本错乱。
                app_logger.log_audio_event(
                    "Skipping final realtime audio submission",
                    {"audio_length": len(audio_data)},
                )
                return
            else:  # chunked
                # chunked 模式：只发送剩余未发送的增量音频
                if hasattr(self._audio_service, "get_remaining_audio_for_streaming"):
                    remaining_audio = (
                        self._audio_service.get_remaining_audio_for_streaming()
                    )
                    if len(remaining_audio) > 0 and hasattr(
                        self._speech_service, "add_streaming_chunk"
                    ):
                        self._speech_service.add_streaming_chunk(remaining_audio)
                        app_logger.log_audio_event(
                            "Final streaming chunk added (remaining audio only)",
                            {"audio_length": len(remaining_audio)},
                        )
                    else:
                        app_logger.log_audio_event(
                            "No remaining audio to send for final chunk", {}
                        )
        except Exception as e:
            app_logger.log_error(e, "submit_final_audio")

    def _save_and_request_transcription(self, audio_data) -> None:
        """保存音频文件并发送转录请求

        Args:
            audio_data: 音频数据
        """
        # 保存音频文件到历史记录
        record_id = str(uuid.uuid4())
        audio_file_path = None

        try:
            # 生成音频文件路径
            audio_file_path = self._history_service.generate_audio_file_path()

            # 保存音频文件
            if hasattr(self._audio_service, "save_to_file"):
                save_success = self._audio_service.save_to_file(audio_file_path)
                if save_success:
                    app_logger.log_audio_event(
                        "Audio file saved to history",
                        {
                            "record_id": record_id,
                            "file_path": audio_file_path,
                            "duration": f"{self._last_audio_duration:.1f}s",
                        },
                    )
                else:
                    app_logger.log_audio_event(
                        "Failed to save audio file", {"record_id": record_id}
                    )
                    audio_file_path = None
            else:
                app_logger.log_audio_event(
                    "AudioService does not support save_to_file", {}
                )
                audio_file_path = None
        except Exception as e:
            app_logger.log_error(e, "save_audio_file_to_history")
            audio_file_path = None

        # 发送转录请求事件（由 TranscriptionController 监听）
        self._events.emit(
            Events.TRANSCRIPTION_REQUEST,
            {
                "audio_duration": self._last_audio_duration,
                "recording_stop_time": self._recording_stop_time,
                "record_id": record_id,
                "audio_file_path": audio_file_path,
            },
        )
