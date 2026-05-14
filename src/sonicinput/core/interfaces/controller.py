"""控制器接口定义

定义各个业务控制器的接口，用于拆分 VoiceInputApp 的职责。
"""

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np


class IRecordingController(ABC):
    """录音控制器接口

    负责录音的启动、停止和音频数据处理。
    """

    @abstractmethod
    def start_recording(self, device_id: Optional[int] = None) -> None:
        """开始录音

        Args:
            device_id: 音频设备ID
        """
        pass

    @abstractmethod
    def stop_recording(self) -> None:
        """停止录音"""
        pass

    @abstractmethod
    def toggle_recording(self) -> None:
        """切换录音状态"""
        pass

    @abstractmethod
    def is_recording(self) -> bool:
        """是否正在录音"""
        pass


class ITranscriptionController(ABC):
    """转录控制器接口

    负责音频转文本的处理逻辑。
    """

    @abstractmethod
    def process_transcription(self, audio_data: np.ndarray) -> None:
        """处理转录

        Args:
            audio_data: 音频数据
        """
        pass

    @abstractmethod
    def process_streaming_transcription(self) -> None:
        """处理流式转录（等待所有块完成并拼接）"""
        pass

    @abstractmethod
    def start_streaming_mode(self) -> None:
        """启动流式转录模式"""
        pass


class IAIProcessingController(ABC):
    """AI处理控制器接口

    负责AI文本优化处理。
    """

    @abstractmethod
    def process_with_ai(
        self,
        text: str,
        record_id: Optional[str] = None,
        update_history: bool = True,
        emit_events: bool = True,
    ) -> str:
        """使用AI优化文本

        Args:
            text: 原始文本
            record_id: 历史记录ID（可选）
            update_history: 是否更新历史记录
            emit_events: 是否发送实时 UI 事件

        Returns:
            优化后的文本
        """
        pass

    @abstractmethod
    def is_ai_enabled(self) -> bool:
        """AI是否启用"""
        pass


class IInputController(ABC):
    """输入控制器接口

    负责文本输入到活动窗口。
    """

    @abstractmethod
    def input_text(self, text: str) -> bool:
        """输入文本

        Args:
            text: 要输入的文本

        Returns:
            是否输入成功
        """
        pass

    @abstractmethod
    def set_preferred_method(self, method: str) -> None:
        """设置首选输入方法

        Args:
            method: 输入方法 (clipboard 或 sendinput)
        """
        pass
