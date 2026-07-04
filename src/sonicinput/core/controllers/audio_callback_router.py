"""音频回调路由器

负责根据流式模式路由音频数据到适当的处理器。
"""

from typing import Optional

import numpy as np

from ...utils import app_logger
from ..base.lifecycle_component import LifecycleComponent
from ..interfaces import (
    IAudioService,
    IEventService,
    ISpeechService,
)
from ..services.events import Events
from ..services.storage import HistoryStorageService


class AudioCallbackRouter(LifecycleComponent):
    """音频回调路由器

    职责：
    - 注册/注销音频回调函数
    - 根据流式模式路由音频数据
    - chunked 模式：使用 30 秒块回调
    - realtime 模式：使用持续音频流回调
    - disabled 模式：仅音频电平回调（用于波形显示）
    """

    def __init__(
        self,
        audio_service: IAudioService,
        event_service: IEventService,
        speech_service: ISpeechService,
        history_service: HistoryStorageService,
    ):
        """初始化音频回调路由器

        Args:
            audio_service: 音频服务
            event_service: 事件服务
            speech_service: 语音服务
            history_service: 历史记录服务
        """
        super().__init__("AudioCallbackRouter")

        self._audio_service = audio_service
        self._events = event_service
        self._speech_service = speech_service
        self._history_service = history_service

        # 当前注册的回调类型
        self._current_callback_type: Optional[str] = None

    def _do_start(self) -> bool:
        """启动回调路由器

        Returns:
            True 如果启动成功
        """
        app_logger.log_audio_event(
            "AudioCallbackRouter started", {"component": self._component_name}
        )
        return True

    def _do_stop(self) -> bool:
        """停止回调路由器并注销所有回调

        Returns:
            True 如果停止成功
        """
        self.unregister_callbacks()

        app_logger.log_audio_event(
            "AudioCallbackRouter stopped", {"component": self._component_name}
        )
        return True

    def register_chunked_callback(self) -> None:
        """注册 chunked 模式回调

        - 30 秒块回调：用于流式转录
        - 音频数据回调：用于实时波形显示
        """
        # 设置 chunk callback（30 秒块）
        if hasattr(self._audio_service, "chunk_callback") and hasattr(
            self._speech_service, "add_streaming_chunk"
        ):

            def streaming_chunk_callback(audio_data):
                """流式转录块回调"""
                try:
                    self._speech_service.add_streaming_chunk(audio_data)
                    app_logger.log_audio_event(
                        "Streaming chunk added",
                        {"audio_length": len(audio_data)},
                    )
                except Exception as e:
                    app_logger.log_error(e, "streaming_chunk_callback")

            self._audio_service.chunk_callback = streaming_chunk_callback
            app_logger.log_audio_event("Chunked mode: chunk callback set", {})
        else:
            setattr(self._audio_service, "chunk_callback", None)
            app_logger.log_audio_event("Chunked mode: chunk callback not available", {})

        # 设置音频数据回调（用于实时波形显示）
        if hasattr(self._audio_service, "set_callback"):
            self._audio_service.set_callback(self._on_audio_data)

        self._current_callback_type = "chunked"

    def register_realtime_callback(self) -> None:
        """注册 realtime 模式回调

        - 持续音频流回调：用于边到边流式转录
        - 同时更新音频电平（用于波形显示）
        """
        if hasattr(self._speech_service, "streaming_coordinator"):

            def realtime_audio_callback(audio_data):
                """实时音频流回调"""
                try:
                    # 发送到 streaming coordinator 的 realtime 处理
                    self._speech_service.streaming_coordinator.add_realtime_audio(
                        audio_data
                    )

                    # 同时更新音频电平（用于波形显示）
                    if len(audio_data) > 0:
                        level = self._compute_audio_level(audio_data)
                        self._events.emit(Events.AUDIO_LEVEL_UPDATE, level)

                except Exception as e:
                    app_logger.log_error(e, "realtime_audio_callback")

            # 清除 chunk_callback（realtime 不使用分块）
            if hasattr(self._audio_service, "chunk_callback"):
                self._audio_service.chunk_callback = None

            # 设置持续音频回调
            if hasattr(self._audio_service, "set_callback"):
                self._audio_service.set_callback(realtime_audio_callback)
                app_logger.log_audio_event("Realtime mode: audio callback set", {})
        else:
            app_logger.log_audio_event(
                "Realtime mode: streaming coordinator not available", {}
            )
            # Fallback: 使用基本音频回调
            if hasattr(self._audio_service, "set_callback"):
                self._audio_service.set_callback(self._on_audio_data)

        self._current_callback_type = "realtime"

    def register_basic_callback(self) -> None:
        """注册基本音频回调（disabled 模式或云提供商）

        仅用于波形显示，不进行流式转录。
        """
        # 清除 chunk_callback
        if hasattr(self._audio_service, "chunk_callback"):
            self._audio_service.chunk_callback = None

        # 设置基本音频回调
        if hasattr(self._audio_service, "set_callback"):
            self._audio_service.set_callback(self._on_audio_data)

        self._current_callback_type = "basic"

        app_logger.log_audio_event("Basic audio callback registered (no streaming)", {})

    def unregister_callbacks(self) -> None:
        """注销所有音频回调"""
        if hasattr(self._audio_service, "chunk_callback"):
            self._audio_service.chunk_callback = None

        if hasattr(self._audio_service, "set_callback"):
            self._audio_service.set_callback(None)

        app_logger.log_audio_event("All audio callbacks unregistered", {})
        self._current_callback_type = None

    def _on_audio_data(self, audio_data: np.ndarray) -> None:
        """基本音频数据回调

        用于波形显示（不进行流式转录）

        Args:
            audio_data: 音频数据块
        """
        try:
            if len(audio_data) > 0:
                # 计算音频电平
                level = self._compute_audio_level(audio_data)
                # 发送音频电平更新事件（UI可以监听此事件更新波形）
                self._events.emit(Events.AUDIO_LEVEL_UPDATE, level)

        except Exception as e:
            app_logger.log_error(e, "_on_audio_data")

    @staticmethod
    def _compute_audio_level(audio_data: np.ndarray) -> float:
        """计算音频RMS电平。

        使用点积避免 ``audio_data**2`` 的额外临时数组分配。
        """
        samples = np.asarray(audio_data, dtype=np.float32)
        sample_count = samples.size
        if sample_count == 0:
            return 0.0

        mean_square = float(np.dot(samples, samples)) / sample_count
        return float(np.sqrt(mean_square))
