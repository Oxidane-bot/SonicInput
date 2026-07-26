"""状态管理接口定义"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")


class AppState(Enum):
    """应用程序状态枚举"""

    STARTING = "starting"
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    INPUT_READY = "input_ready"
    ERROR = "error"
    STOPPING = "stopping"


class RecordingState(Enum):
    """录音状态枚举"""

    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    STOPPING = "stopping"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class IStateManager(ABC):
    """状态管理器接口

    提供线程安全的全局状态管理功能。
    """

    @abstractmethod
    def set_state(self, key: str, value: Any) -> None:
        """设置状态值

        Args:
            key: 状态键名
            value: 状态值
        """
        pass

    @abstractmethod
    def get_state(self, key: str, default: Optional[T] = None) -> T:
        """获取状态值

        Args:
            key: 状态键名
            default: 默认值

        Returns:
            状态值，不存在时返回默认值
        """
        pass

    @abstractmethod
    def subscribe(self, key: str, callback: Callable[[Any, Any], None]) -> str:
        """订阅状态变更

        Args:
            key: 状态键名
            callback: 回调函数，参数为 (旧值, 新值)

        Returns:
            订阅ID，用于取消订阅
        """
        pass

    @abstractmethod
    def unsubscribe(self, key: str, subscription_id: str) -> bool:
        """取消状态订阅

        Args:
            key: 状态键名
            subscription_id: 订阅ID

        Returns:
            是否取消成功
        """
        pass

    @abstractmethod
    def unsubscribe_all(self, key: str) -> int:
        """取消指定状态的所有订阅

        Args:
            key: 状态键名

        Returns:
            取消的订阅数量
        """
        pass

    @abstractmethod
    def set_app_state(self, state: AppState) -> None:
        """设置应用程序状态

        Args:
            state: 应用程序状态
        """
        pass

    @abstractmethod
    def get_app_state(self) -> AppState:
        """获取应用程序状态

        Returns:
            当前应用程序状态
        """
        pass

    @abstractmethod
    def set_recording_state(self, state: RecordingState) -> None:
        """设置录音状态

        Args:
            state: 录音状态
        """
        pass

    @abstractmethod
    def get_recording_state(self) -> RecordingState:
        """获取录音状态

        Returns:
            当前录音状态
        """
        pass

    @abstractmethod
    def is_recording(self) -> bool:
        """是否正在录音

        Returns:
            是否正在录音
        """
        pass

    @abstractmethod
    def is_processing(self) -> bool:
        """是否正在处理

        Returns:
            是否正在处理
        """
        pass

    @abstractmethod
    def is_ready_for_input(self) -> bool:
        """是否准备好接收输入

        Returns:
            是否准备好接收输入
        """
        pass

    @property
    @abstractmethod
    def total_subscribers(self) -> int:
        """总订阅者数量"""
        pass
