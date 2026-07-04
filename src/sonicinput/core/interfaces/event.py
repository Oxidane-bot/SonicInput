"""事件服务接口定义"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, Optional


class EventPriority(Enum):
    """事件优先级"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class IEventService(ABC):
    """事件服务接口

    签名与 DynamicEventSystem 的真实契约一致:
    监听方法返回 listener_id(str),off 以 listener_id 取消并返回是否成功。
    """

    @abstractmethod
    def emit(
        self,
        event: str,
        data: Any = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """发出事件"""
        pass

    @abstractmethod
    def on(
        self,
        event: str,
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> str:
        """监听事件,返回 listener_id"""
        pass

    @abstractmethod
    def once(
        self,
        event: str,
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> str:
        """一次性监听事件,返回 listener_id"""
        pass

    @abstractmethod
    def subscribe(
        self,
        event: str,
        callback: Callable[[Any], None],
        priority: EventPriority = EventPriority.NORMAL,
        is_once: bool = False,
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """订阅事件(完整参数版),返回 listener_id"""
        pass

    @abstractmethod
    def off(self, event: str, listener_id: str) -> bool:
        """按 listener_id 取消监听,返回是否成功"""
        pass


__all__ = ["EventPriority", "IEventService"]
