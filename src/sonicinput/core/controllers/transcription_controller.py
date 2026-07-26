"""转录控制器

负责音频转文本的处理逻辑。
"""

import time
from datetime import datetime
from typing import Optional

from ...utils import ErrorMessageTranslator, app_logger
from ..base.lifecycle_component import LifecycleComponent
from ..interfaces import (
    HistoryRecord,
    IConfigService,
    IEventService,
    IStateManager,
    ISyncTranscriptionService,
    ITranscriptionController,
)
from ..interfaces.state import AppState
from ..quality.transcript_quality_validator import TranscriptQualityValidator
from ..services.config import ConfigKeys
from ..services.events import Events
from ..services.storage import HistoryStorageService
from .base_controller import BaseController
from .logging_helper import ControllerLogging


class TranscriptionController(
    BaseController, LifecycleComponent, ITranscriptionController
):
    """转录控制器实现

    职责：
    - 处理音频转录
    - 管理流式转录
    - 通过 EventBus 发送转录事件
    """

    _LOW_QUALITY_CHUNKED_FALLBACK_MIN_DURATION_SECONDS = 8.0

    def _to_bool_config(self, value: object, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _long_recording_path_decision_context(
        self,
        streaming_mode: str,
    ) -> dict[str, object]:
        provider = str(
            self._config.get_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "local") or ""
        ).strip()
        prefer_file = self._config.get_setting(
            ConfigKeys.TRANSCRIPTION_LONG_RECORDING_PREFER_FILE_FOR_CLOUD,
            True,
        )
        prefer_enabled = self._to_bool_config(prefer_file, default=True)
        threshold = self._config.get_setting(
            ConfigKeys.TRANSCRIPTION_LONG_RECORDING_FILE_THRESHOLD_SECONDS,
            90.0,
        )
        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError):
            threshold_value = 90.0

        return {
            "record_id": self._current_record_id,
            "streaming_mode": streaming_mode,
            "provider": provider,
            "audio_duration": self._audio_duration,
            "audio_file_path_present": bool(self._current_audio_file_path),
            "prefer_file_for_long_cloud_recording": prefer_enabled,
            "long_recording_file_threshold_seconds": threshold_value,
            "audio_service_present": self._audio_service is not None,
        }

    def _log_transcription_path_decision(
        self,
        *,
        event: str,
        streaming_mode: str,
        selected_path: str,
        fallback_used: bool,
        fallback_type: str,
        fallback_reason: Optional[str],
        extra: Optional[dict[str, object]] = None,
    ) -> None:
        details = self._long_recording_path_decision_context(streaming_mode)
        details.update(
            {
                "selected_path": selected_path,
                "fallback_used": fallback_used,
                "fallback_type": fallback_type,
                "fallback_reason": fallback_reason,
            }
        )
        if extra:
            details.update(extra)
        app_logger.log_audio_event(event, details)

    def __init__(
        self,
        speech_service: ISyncTranscriptionService,
        config_service: IConfigService,
        event_service: IEventService,
        state_manager: IStateManager,
        history_service: HistoryStorageService,
        audio_service=None,
        streaming_manager=None,
    ):
        # Initialize LifecycleComponent FIRST (sets self._state = ComponentState)
        LifecycleComponent.__init__(self, "TranscriptionController")
        # Initialize BaseController SECOND (overwrites self._state = state_manager)
        BaseController.__init__(self, config_service, event_service, state_manager)

        # Controller-specific services
        self._speech_service = speech_service
        self._audio_service = audio_service  # 添加音频服务引用，用于fallback
        self._history_service = history_service
        self._streaming_manager = streaming_manager

        # 性能追踪数据（从 RecordingController 接收）
        self._audio_duration: float = 0.0
        self._recording_stop_time: float = 0.0

        # 历史记录追踪数据（从 RecordingController 接收）
        self._current_record_id: Optional[str] = None
        self._current_audio_file_path: Optional[str] = None

        # NOTE: Event listener registration moved to _do_start() for hot reload support
        # NOTE: Initialization logging moved to _do_start() for hot reload support

    def _register_event_listeners(self) -> None:
        """Register event listeners for transcription events

        NOTE: Called from _do_start() to support hot reload.
        Uses _track_listener() to enable proper cleanup.
        """
        self._track_listener(
            Events.TRANSCRIPTION_REQUEST, self._on_transcription_request
        )

    def _on_transcription_request(self, data: dict) -> None:
        """处理转录请求事件

        Args:
            data: 包含 audio_duration, recording_stop_time, record_id, audio_file_path
        """
        self._audio_duration = data.get("audio_duration", 0.0)
        self._recording_stop_time = data.get("recording_stop_time", time.time())
        self._current_record_id = data.get("record_id")
        self._current_audio_file_path = data.get("audio_file_path")

        app_logger.log_audio_event(
            "Transcription request received",
            {
                "record_id": self._current_record_id,
                "audio_file_path": self._current_audio_file_path,
                "audio_duration": self._audio_duration,
            },
        )

        # 启动流式转录处理
        self.process_streaming_transcription()

    def process_streaming_transcription(self) -> None:
        """处理流式转录（使用新的TranscriptionService API）"""
        streaming_mode = "unknown"
        transcription_path = "standard"
        transcription_decision_reason = None
        fallback_used = False
        fallback_type = "none"
        fallback_reason = None
        transcribe_start = time.time()
        try:
            ControllerLogging.log_state_change(
                "app",
                AppState.IDLE,
                AppState.PROCESSING,
                {"mode": "streaming_transcription"},
            )
            self._state_manager.set_app_state(AppState.PROCESSING)
            self._events.emit(Events.TRANSCRIPTION_STARTED)

            # 使用新的TranscriptionService API
            transcribe_start = time.time()

            # 获取当前���式模式
            streaming_mode = self._streaming_manager.get_current_mode()

            # 根据流式模式决定转录路径（统一处理本地和云提供商）
            if self._should_prefer_file_transcription_for_long_cloud_recording(
                streaming_mode
            ):
                self._log_transcription_path_decision(
                    event="Transcription path decision",
                    streaming_mode=streaming_mode,
                    selected_path="cloud_file_long_recording",
                    fallback_used=False,
                    fallback_type="none",
                    fallback_reason=None,
                    extra={"decision_reason": "long_cloud_recording_prefer_file"},
                )
                app_logger.log_audio_event(
                    "Long cloud recording prefers file transcription path",
                    {
                        "streaming_mode": streaming_mode,
                        "audio_duration": self._audio_duration,
                    },
                )
                self._cleanup_streaming_session_without_transcription()
                text = self._transcribe_from_file_for_cloud()
                transcription_path = "cloud_file_long_recording"
                transcription_decision_reason = "long_cloud_recording_prefer_file"
                stats = {
                    "mode": streaming_mode,
                    "path": "cloud_file_long_recording",
                }
                if text is None:
                    text = ""
                elif not isinstance(text, str):
                    text = str(text)
            elif streaming_mode in ["chunked", "realtime"]:
                # 流式转录路径（本地和云提供商都支持）
                app_logger.log_audio_event(
                    "Stopping streaming transcription",
                    {"streaming_mode": streaming_mode},
                )

                # 停止流式转录并获取转录文本和统计信息
                result = self._speech_service.stop_streaming()

                # 从返回结果中提取文本和统计信息
                text = result.get("text", "")
                stats = result.get("stats", {})
                if text is None:
                    text = ""
                elif not isinstance(text, str):
                    text = str(text)
                transcription_path = (
                    "streaming_realtime"
                    if streaming_mode == "realtime"
                    else "streaming_chunked"
                )
                transcription_decision_reason = "streaming_stop_result"
                self._log_transcription_path_decision(
                    event="Transcription path decision",
                    streaming_mode=streaming_mode,
                    selected_path=transcription_path,
                    fallback_used=False,
                    fallback_type="none",
                    fallback_reason=None,
                    extra={"decision_reason": "streaming_stop_result"},
                )

                app_logger.log_audio_event(
                    "Streaming transcription stopped",
                    {"text_length": len(text), "stats": stats, "mode": streaming_mode},
                )
            else:
                # disabled 模式：使用文件转录
                app_logger.log_audio_event(
                    "Streaming disabled, using file-based transcription",
                    {"streaming_mode": streaming_mode},
                )
                text = self._transcribe_from_file_for_cloud()
                transcription_path = "cloud_file"
                transcription_decision_reason = "streaming_disabled_file_transcription"
                self._log_transcription_path_decision(
                    event="Transcription path decision",
                    streaming_mode=streaming_mode,
                    selected_path="cloud_file",
                    fallback_used=False,
                    fallback_type="none",
                    fallback_reason=None,
                    extra={"decision_reason": "streaming_disabled_file_transcription"},
                )
                stats = {}
                if text is None:
                    text = ""
                elif not isinstance(text, str):
                    text = str(text)

            # Chunked 模式下如果最终文本为空（含仅空白），执行 fallback。
            # 本地提供商走同步转录；云提供商走文件转录。
            if streaming_mode == "chunked" and not text.strip():
                if self._audio_service:
                    app_logger.log_audio_event(
                        "No text from chunked streaming, falling back to sync transcription",
                        {"streaming_mode": streaming_mode, "fallback": "local_sync"},
                    )
                    text = self._sync_transcribe_last_audio()
                    transcription_path = "local_sync_fallback"
                    transcription_decision_reason = "empty_chunked_result"
                    fallback_used = True
                    fallback_type = "local_sync"
                    fallback_reason = "empty_chunked_result"
                    self._log_transcription_path_decision(
                        event="Transcription fallback engaged",
                        streaming_mode=streaming_mode,
                        selected_path=transcription_path,
                        fallback_used=True,
                        fallback_type=fallback_type,
                        fallback_reason=fallback_reason,
                        extra={"decision_reason": "empty_chunked_result"},
                    )
                else:
                    app_logger.log_audio_event(
                        "No text from chunked streaming, falling back to file transcription",
                        {"streaming_mode": streaming_mode, "fallback": "cloud_file"},
                    )
                    text = self._transcribe_from_file_for_cloud()
                    transcription_path = "cloud_file_fallback"
                    transcription_decision_reason = "empty_chunked_result"
                    fallback_used = True
                    fallback_type = "cloud_file"
                    fallback_reason = "empty_chunked_result"
                    self._log_transcription_path_decision(
                        event="Transcription fallback engaged",
                        streaming_mode=streaming_mode,
                        selected_path=transcription_path,
                        fallback_used=True,
                        fallback_type=fallback_type,
                        fallback_reason=fallback_reason,
                        extra={"decision_reason": "empty_chunked_result"},
                    )
            elif self._should_fallback_for_low_quality_chunked_result(
                text=text,
                streaming_mode=streaming_mode,
            ):
                if self._audio_service:
                    app_logger.log_audio_event(
                        "Low-quality text from chunked streaming, falling back to sync transcription",
                        {
                            "streaming_mode": streaming_mode,
                            "fallback": "local_sync",
                            "audio_duration": self._audio_duration,
                            "text_preview": text[:50],
                        },
                    )
                    text = self._sync_transcribe_last_audio()
                    transcription_path = "local_sync_fallback"
                    transcription_decision_reason = "low_quality_chunked_result"
                    fallback_used = True
                    fallback_type = "local_sync"
                    fallback_reason = "low_quality_chunked_result"
                    self._log_transcription_path_decision(
                        event="Transcription fallback engaged",
                        streaming_mode=streaming_mode,
                        selected_path=transcription_path,
                        fallback_used=True,
                        fallback_type=fallback_type,
                        fallback_reason=fallback_reason,
                        extra={"decision_reason": "low_quality_chunked_result"},
                    )
                else:
                    app_logger.log_audio_event(
                        "Low-quality text from chunked streaming, falling back to file transcription",
                        {
                            "streaming_mode": streaming_mode,
                            "fallback": "cloud_file",
                            "audio_duration": self._audio_duration,
                            "text_preview": text[:50],
                        },
                    )
                    text = self._transcribe_from_file_for_cloud()
                    transcription_path = "cloud_file_fallback"
                    transcription_decision_reason = "low_quality_chunked_result"
                    fallback_used = True
                    fallback_type = "cloud_file"
                    fallback_reason = "low_quality_chunked_result"
                    self._log_transcription_path_decision(
                        event="Transcription fallback engaged",
                        streaming_mode=streaming_mode,
                        selected_path=transcription_path,
                        fallback_used=True,
                        fallback_type=fallback_type,
                        fallback_reason=fallback_reason,
                        extra={"decision_reason": "low_quality_chunked_result"},
                    )

            transcribe_duration = time.time() - transcribe_start

            app_logger.log_audio_event(
                "Transcription completed",
                {
                    "text_length": len(text),
                    "duration": f"{transcribe_duration:.3f}s",
                    "text_preview": text[:50] + "..." if len(text) > 50 else text,
                    "mode": streaming_mode,
                },
            )

            # 保存历史记录（转录阶段）
            if self._current_record_id and self._current_audio_file_path:
                self._save_transcription_record(
                    text=text,
                    status="success",
                    error=None,
                    streaming_mode=streaming_mode,
                    transcription_path=transcription_path,
                    transcription_decision_reason=transcription_decision_reason,
                    transcription_duration=transcribe_duration,
                    used_fallback=fallback_used,
                    fallback_type=fallback_type,
                    fallback_reason=fallback_reason,
                )

            # 发送转录完成事件（包含 streaming_mode）
            self._events.emit(
                Events.TRANSCRIPTION_COMPLETED,
                {
                    "text": text,
                    "audio_duration": self._audio_duration,
                    "transcribe_duration": transcribe_duration,
                    "recording_stop_time": self._recording_stop_time,
                    "record_id": self._current_record_id,
                    "streaming_mode": streaming_mode,
                },
            )

            # 重置状态
            ControllerLogging.log_state_change(
                "app",
                AppState.PROCESSING,
                AppState.IDLE,
                {"duration": f"{transcribe_duration:.3f}s"},
            )
            self._state_manager.set_app_state(AppState.IDLE)

        except Exception as e:
            app_logger.log_error(e, "process_streaming_transcription")
            transcribe_duration = max(0.0, time.time() - transcribe_start)

            # 保存失败的历史记录
            if self._current_record_id and self._current_audio_file_path:
                self._save_transcription_record(
                    text="",
                    status="failed",
                    error=str(e),
                    streaming_mode=streaming_mode,
                    transcription_path=transcription_path,
                    transcription_decision_reason=transcription_decision_reason,
                    transcription_duration=transcribe_duration,
                    used_fallback=fallback_used,
                    fallback_type=fallback_type,
                    fallback_reason=fallback_reason,
                )

            # 转换为用户友好消息
            error_info = ErrorMessageTranslator.translate(e, "transcription")
            self._events.emit(Events.TRANSCRIPTION_ERROR, error_info["user_message"])

            # 错误时也要重置状态，否则无法进行下一次录音
            ControllerLogging.log_state_change(
                "app",
                AppState.PROCESSING,
                AppState.IDLE,
                {"reason": "streaming_transcription_error"},
                is_forced=True,
            )
            self._state_manager.set_app_state(AppState.IDLE)

    def _transcribe_from_file_for_cloud(self) -> str:
        """云提供商：从音频文件转录（不经过流式系统）"""
        if not self._current_audio_file_path:
            app_logger.log_audio_event(
                "No audio file path available for cloud transcription", {}
            )
            return ""

        if not hasattr(self._speech_service, "transcribe_sync"):
            app_logger.log_audio_event(
                "Cloud provider doesn't support transcribe_sync", {}
            )
            return ""

        try:
            # 从文件读取音频数据
            import wave

            import numpy as np

            with wave.open(self._current_audio_file_path, "rb") as wav_file:
                frames = wav_file.readframes(wav_file.getnframes())
                audio_data = (
                    np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                )

            # 使用云提供商的 transcribe_sync
            result = self._speech_service.transcribe_sync(audio_data)
            text = result.get("text", "")

            app_logger.log_audio_event(
                "Cloud provider file-based transcription completed",
                {"text_length": len(text), "audio_file": self._current_audio_file_path},
            )
            return text
        except Exception as e:
            app_logger.log_error(e, "cloud_file_transcription")
            return ""

    def _sync_transcribe_last_audio(self) -> str:
        """同步转录最后一次录音的音频数据（本地提供商fallback）"""
        try:
            if not self._audio_service or not hasattr(
                self._audio_service, "get_audio_data"
            ):
                app_logger.log_audio_event(
                    "Audio service not available for sync transcription", {}
                )
                return ""

            # 获取最后一次录音的音频数据
            audio_data = self._audio_service.get_audio_data()
            if audio_data is None or len(audio_data) == 0:
                app_logger.log_audio_event(
                    "No audio data available for sync transcription", {}
                )
                return ""

            app_logger.log_audio_event(
                "Starting sync transcription", {"audio_length": len(audio_data)}
            )

            # 执行同步转录 - 使用新的TranscriptionService API
            result = self._speech_service.transcribe_sync(audio_data)
            text = result.get("text", "")

            app_logger.log_audio_event(
                "Sync transcription completed", {"text_length": len(text)}
            )

            return text

        except Exception as e:
            app_logger.log_error(e, "_sync_transcribe_last_audio")
            return ""

    def start_streaming_mode(self) -> None:
        """启动流式转录模式"""
        if hasattr(self._speech_service, "start_streaming_mode"):
            self._speech_service.start_streaming_mode()
            app_logger.log_audio_event("Streaming mode started", {})

    def _save_transcription_record(
        self,
        text: str,
        status: str,
        error: Optional[str],
        streaming_mode: str = "unknown",
        transcription_path: str = "standard",
        transcription_decision_reason: Optional[str] = None,
        transcription_duration: float = 0.0,
        used_fallback: bool = False,
        fallback_type: str = "none",
        fallback_reason: Optional[str] = None,
        diagnostics_collected: bool = True,
    ) -> None:
        """保存转录记录到历史数据库

        Args:
            text: 转录文本
            status: 转录状态 ("success" | "failed")
            error: 错误信息（如果有）
        """
        try:
            # 调用方保证以下两个字段非空；此处收窄类型并防御性返回
            record_id = self._current_record_id
            audio_file_path = self._current_audio_file_path
            if record_id is None or audio_file_path is None:
                return

            # 获取转录提供商
            provider = self._config.get_setting(
                ConfigKeys.TRANSCRIPTION_PROVIDER, "local"
            )

            # 创建历史记录
            record = HistoryRecord(
                id=record_id,
                timestamp=datetime.fromtimestamp(self._recording_stop_time),
                audio_file_path=audio_file_path,
                duration=self._audio_duration,
                transcription_text=text,
                transcription_provider=provider,
                transcription_status=status,
                streaming_mode=streaming_mode,
                transcription_path=transcription_path,
                transcription_decision_reason=transcription_decision_reason,
                transcription_duration=transcription_duration,
                used_fallback=used_fallback,
                fallback_type=fallback_type,
                fallback_reason=fallback_reason,
                diagnostics_collected=diagnostics_collected,
                transcription_error=error,
                ai_optimized_text=None,
                ai_provider=None,
                ai_status="pending",
                ai_error=None,
                final_text=text,  # 暂时使用转录文本，AI阶段会更新
            )

            # 保存到数据库
            save_success = self._history_service.save_record(record)

            if save_success:
                app_logger.log_audio_event(
                    "Transcription record saved",
                    {
                        "record_id": self._current_record_id,
                        "status": status,
                        "text_length": len(text),
                        "streaming_mode": streaming_mode,
                        "transcription_path": transcription_path,
                        "transcription_decision_reason": transcription_decision_reason,
                        "transcription_duration": transcription_duration,
                        "used_fallback": used_fallback,
                        "fallback_type": fallback_type,
                        "fallback_reason": fallback_reason,
                    },
                )
            else:
                app_logger.log_audio_event(
                    "Failed to save transcription record",
                    {"record_id": self._current_record_id},
                )

        except Exception as e:
            app_logger.log_error(e, "_save_transcription_record")

    def _should_fallback_for_low_quality_chunked_result(
        self,
        *,
        text: str,
        streaming_mode: str,
    ) -> bool:
        if streaming_mode != "chunked":
            return False
        if (
            self._audio_duration
            < self._LOW_QUALITY_CHUNKED_FALLBACK_MIN_DURATION_SECONDS
        ):
            return False
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return False
        return TranscriptQualityValidator.is_low_information_input(normalized_text)

    def _should_prefer_file_transcription_for_long_cloud_recording(
        self,
        streaming_mode: str,
    ) -> bool:
        if streaming_mode != "chunked":
            return False
        provider = str(
            self._config.get_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "local") or ""
        ).strip()
        if provider == "local":
            return False

        prefer_file = self._config.get_setting(
            ConfigKeys.TRANSCRIPTION_LONG_RECORDING_PREFER_FILE_FOR_CLOUD,
            True,
        )
        prefer_enabled = self._to_bool_config(prefer_file, default=True)
        if not prefer_enabled:
            return False

        threshold = self._config.get_setting(
            ConfigKeys.TRANSCRIPTION_LONG_RECORDING_FILE_THRESHOLD_SECONDS,
            90.0,
        )
        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError):
            threshold_value = 90.0
        if self._audio_duration < max(1.0, threshold_value):
            return False
        return bool(self._current_audio_file_path)

    def _cleanup_streaming_session_without_transcription(self) -> None:
        coordinator = getattr(self._speech_service, "streaming_coordinator", None)
        if coordinator is not None and hasattr(coordinator, "stop_streaming"):
            coordinator.stop_streaming()

    def _do_start(self) -> bool:
        """Start lifecycle method - Initialize transcription resources

        Returns:
            True if start successful
        """
        try:
            # Register event listeners (supports hot reload)
            self._register_event_listeners()

            # Log initialization
            self._log_initialization()

            app_logger.log_audio_event(
                "TranscriptionController started (event-driven mode)",
                {"component": "TranscriptionController"},
            )
            return True
        except Exception as e:
            app_logger.log_error(e, "TranscriptionController._do_start")
            return False

    def _do_stop(self) -> bool:
        """Stop lifecycle method - Cleanup transcription resources

        Returns:
            True if stop successful
        """
        try:
            # Cleanup event listeners (supports hot reload)
            self._cleanup_event_listeners()

            # Reset tracking data
            self._audio_duration = 0.0
            self._recording_stop_time = 0.0
            self._current_record_id = None
            self._current_audio_file_path = None

            app_logger.log_audio_event(
                "TranscriptionController stopped and cleaned up",
                {"component": "TranscriptionController"},
            )
            return True
        except Exception as e:
            app_logger.log_error(e, "TranscriptionController._do_stop")
            return False
