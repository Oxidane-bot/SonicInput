"""简化的动态事件系统

核心功能：
1. 事件发布/订阅（emit/subscribe）
2. 优先级支持（HIGH > NORMAL > LOW）
3. 一次性监听器（once）
4. 动态事件类型注册
5. 线程安全保证

简化说明：
- 移除了未使用的插件系统
- 移除了未使用的验证系统
- 简化了统计和命名空间系统
- 保留了所有核心功能，减少了代码复杂度
"""

import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from ..base.lifecycle_component import LifecycleComponent
from ..interfaces import EventPriority, IEventService
from .events import EVENT_METADATA, iter_event_names


# 延迟导入logger以避免循环依赖
def _get_logger():
    """懒加载logger"""
    try:
        from ...utils import app_logger

        return app_logger
    except ImportError:
        return None


@dataclass
class EventMetadata:
    """事件元数据"""

    name: str
    description: str = ""
    version: str = "1.0.0"
    namespace: str = "default"
    deprecated: bool = False
    deprecation_message: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"


@dataclass
class EventListener:
    """事件监听器信息"""

    id: str
    callback: Callable
    priority: EventPriority
    created_at: float = field(default_factory=time.time)
    call_count: int = 0
    last_called: float = 0.0
    failure_count: int = 0
    last_error: str = ""
    is_once: bool = False
    namespace: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)


class DynamicEventSystem(LifecycleComponent, IEventService):
    """简化的动态事件系统

    提供高性能的事件发布/订阅机制，支持优先级、线程安全等核心功能。
    完全兼容原有的EventBus接口，移除了未使用的高级特性以提高性能和可维护性。
    """

    def __init__(self):
        """初始化动态事件系统"""
        # Initialize LifecycleComponent
        super().__init__("EventBus")

        # 基础数据结构
        self._listeners: Dict[str, List[EventListener]] = defaultdict(list)
        self._lock = threading.RLock()
        self._enabled = True

        # 动态事件系统特性
        self._event_metadata: Dict[str, EventMetadata] = {}
        self._event_namespaces: Dict[str, Set[str]] = defaultdict(set)
        self._registered_events: Set[str] = set()

        # 性能优化：缓存机制
        self._sorted_listeners_cache: Dict[str, List[EventListener]] = {}
        self._listener_version: Dict[str, int] = {}
        self._listener_failure_count = 0

        # 获取logger
        self.logger = _get_logger()

    def _do_start(self) -> bool:
        """Start event system

        Returns:
            True if start successful
        """
        try:
            # Register builtin events
            self._register_builtin_events()

            if self.logger:
                self.logger.log_audio_event(
                    "DynamicEventSystem initialized",
                    {"builtin_events": len(self._registered_events)},
                )

            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to start EventBus: {e}")
            return False

    def _do_stop(self) -> bool:
        """Stop event system and cleanup subscriptions

        Returns:
            True if stop successful
        """
        try:
            # Clear all listeners
            self.clear_all_listeners()

            # Clear event metadata and registrations
            with self._lock:
                self._event_metadata.clear()
                self._event_namespaces.clear()
                self._registered_events.clear()
                self._sorted_listeners_cache.clear()
                self._listener_version.clear()

            if self.logger:
                self.logger.log_audio_event("DynamicEventSystem cleaned up", {})

            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to stop EventBus: {e}")
            return False

    def _register_builtin_events(self) -> None:
        """Register builtin events."""
        for event_name in iter_event_names():
            metadata_spec = EVENT_METADATA.get(event_name)
            if metadata_spec:
                metadata = EventMetadata(name=event_name, **metadata_spec)
            else:
                metadata = EventMetadata(name=event_name)
            self.register_event_type(event_name, metadata)

    def register_event_type(
        self,
        event_name: str,
        metadata: Optional[EventMetadata] = None,
    ) -> None:
        """注册事件类型

        Args:
            event_name: 事件名称
            metadata: 事件元数据
        """
        with self._lock:
            if event_name in self._registered_events:
                if self.logger:
                    self.logger.warning(
                        f"Event '{event_name}' already registered, updating metadata"
                    )

            # 创建默认元数据
            if metadata is None:
                metadata = EventMetadata(name=event_name)

            # 注册事件
            self._event_metadata[event_name] = metadata
            self._event_namespaces[metadata.namespace].add(event_name)
            self._registered_events.add(event_name)

            # 清除缓存
            self._invalidate_cache_for_event(event_name)

            if self.logger:
                self.logger.log_audio_event(
                    "Event type registered",
                    {
                        "event_name": event_name,
                        "namespace": metadata.namespace,
                        "description": metadata.description,
                    },
                )

    def unregister_event_type(self, event_name: str) -> None:
        """注销事件类型

        Args:
            event_name: 事件名称
        """
        with self._lock:
            if event_name not in self._registered_events:
                if self.logger:
                    self.logger.warning(f"Event '{event_name}' not registered")
                return

            # 检查是否有监听器
            if event_name in self._listeners and self._listeners[event_name]:
                if self.logger:
                    self.logger.warning(
                        f"Cannot unregister event '{event_name}' - has active listeners"
                    )
                return

            # 移除事件
            metadata = self._event_metadata.get(event_name)
            if metadata:
                self._event_namespaces[metadata.namespace].discard(event_name)
                del self._event_metadata[event_name]

            self._registered_events.discard(event_name)

            # 清除缓存
            self._invalidate_cache_for_event(event_name)

            if self.logger:
                self.logger.log_audio_event(
                    "Event type unregistered", {"event_name": event_name}
                )

    def emit(
        self,
        event_name: str,
        data: Any = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """发出事件（兼容原有接口）

        Args:
            event_name: 事件名称
            data: 事件数据
            priority: 事件优先级
        """
        if not self._enabled:
            return

        start_time = time.time()

        # 检查事件是否已注册
        if event_name not in self._registered_events:
            # 自动注册未定义的事件
            self.register_event_type(event_name)

            if self.logger:
                self.logger.info(f"Auto-registered event '{event_name}'")

        try:
            # 获取监听器
            listeners = self._get_sorted_listeners(event_name)

            if not listeners:
                return

            # 执行监听器
            for listener in listeners:
                try:
                    # 执行回调
                    listener.callback(data)

                    # 更新监听器统计
                    listener.call_count += 1
                    listener.last_called = time.time()

                    # 如果是一次性监听器，移除它
                    if listener.is_once:
                        self._remove_listener(event_name, listener.id)

                except Exception as e:
                    listener.failure_count += 1
                    listener.last_error = str(e)
                    self._listener_failure_count += 1
                    if self.logger:
                        self.logger.error(
                            f"Error in event listener for '{event_name}' "
                            f"(listener_id={listener.id}): {e}"
                        )

                    # 继续处理其他监听器

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error emitting event '{event_name}': {e}")

        # 记录处理时间（仅记录慢事件）
        total_time = time.time() - start_time
        if self.logger and total_time > 0.1:
            self.logger.info(f"Event '{event_name}' processed in {total_time:.3f}s")

    def subscribe(
        self,
        event_name: str,
        callback: Callable[[Any], None],
        priority: EventPriority = EventPriority.NORMAL,
        is_once: bool = False,
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """订阅事件（增强版）

        Args:
            event_name: 事件名称
            callback: 回调函数
            priority: 优先级
            is_once: 是否为一次性监听器
            namespace: 命名空间
            metadata: 监听器元数据

        Returns:
            监听器ID
        """
        with self._lock:
            listener_id = str(uuid.uuid4())

            listener = EventListener(
                id=listener_id,
                callback=callback,
                priority=priority,
                is_once=is_once,
                namespace=namespace,
                metadata=metadata or {},
            )

            self._listeners[event_name].append(listener)

            self._bump_listener_version(event_name)

            if self.logger:
                self.logger.log_audio_event(
                    "Event listener added",
                    {
                        "event_name": event_name,
                        "listener_id": listener_id,
                        "priority": priority.name,
                        "is_once": is_once,
                        "namespace": namespace,
                    },
                )

            return listener_id

    def unsubscribe(self, event_name: str, listener_id: str) -> bool:
        """取消订阅事件

        Args:
            event_name: 事件名称
            listener_id: 监听器ID

        Returns:
            True如果成功取消
        """
        with self._lock:
            return self._remove_listener(event_name, listener_id)

    def _remove_listener(self, event_name: str, listener_id: str) -> bool:
        """移除监听器（内部方法）"""
        if event_name not in self._listeners:
            return False

        original_count = len(self._listeners[event_name])
        self._listeners[event_name] = [
            listener
            for listener in self._listeners[event_name]
            if listener.id != listener_id
        ]

        removed = len(self._listeners[event_name]) < original_count

        if removed:
            self._bump_listener_version(event_name)

        return removed

    def unsubscribe_all(self, event_name: str) -> int:
        """取消所有订阅

        Args:
            event_name: 事件名称

        Returns:
            移除的监听器数量
        """
        with self._lock:
            if event_name not in self._listeners:
                return 0

            count = len(self._listeners[event_name])
            self._listeners[event_name].clear()

            self._bump_listener_version(event_name)

            if self.logger:
                self.logger.log_audio_event(
                    "All event listeners removed",
                    {"event_name": event_name, "count": count},
                )

            return count

    def _get_sorted_listeners(self, event_name: str) -> List[EventListener]:
        """获取排序后的监听器列表（带缓存）"""
        version = self._listener_version.get(event_name, 0)
        cache_key = f"{event_name}_{version}"

        if cache_key in self._sorted_listeners_cache:
            return self._sorted_listeners_cache[cache_key].copy()

        # 排序监听器
        listeners = self._listeners.get(event_name, []).copy()
        listeners.sort(key=lambda x: x.priority.value, reverse=True)

        # 缓存结果
        self._sorted_listeners_cache[cache_key] = listeners.copy()
        self._listener_version[event_name] = len(self._listeners[event_name])

        return listeners

    def _bump_listener_version(self, event_name: str) -> None:
        """Advance listener cache version after subscription changes."""
        self._listener_version[event_name] = (
            self._listener_version.get(event_name, 0) + 1
        )
        self._invalidate_cache_for_event(event_name)

    def _invalidate_cache_for_event(self, event_name: str) -> None:
        """清除指定事件的缓存"""
        keys_to_remove = [
            key
            for key in self._sorted_listeners_cache.keys()
            if key.startswith(f"{event_name}_")
        ]
        for key in keys_to_remove:
            del self._sorted_listeners_cache[key]

    def get_registered_events(self, namespace: Optional[str] = None) -> List[str]:
        """获取已注册的事件列表

        Args:
            namespace: 命名空间过滤

        Returns:
            事件名称列表
        """
        with self._lock:
            if namespace:
                return list(self._event_namespaces.get(namespace, set()))
            return list(self._registered_events)

    def get_event_metadata(self, event_name: str) -> Optional[EventMetadata]:
        """获取事件元数据

        Args:
            event_name: 事件名称

        Returns:
            事件元数据
        """
        return self._event_metadata.get(event_name)

    def get_event_stats(self) -> Dict[str, Any]:
        """获取事件统计（简化版）"""
        with self._lock:
            return {
                "total_events": len(self._registered_events),
                "total_listeners": sum(
                    len(listeners) for listeners in self._listeners.values()
                ),
                "events_with_listeners": len(
                    [e for e in self._listeners if self._listeners[e]]
                ),
                "listener_failures": self._listener_failure_count,
            }

    def enable(self) -> None:
        """启用事件系统"""
        self._enabled = True

        if self.logger:
            self.logger.log_audio_event("DynamicEventSystem enabled", {})

    def disable(self) -> None:
        """禁用事件系统"""
        self._enabled = False

        if self.logger:
            self.logger.log_audio_event("DynamicEventSystem disabled", {})

    def is_enabled(self) -> bool:
        """检查事件系统是否启用"""
        return self._enabled

    # IEventService接口的额外方法
    def on(
        self,
        event_name: str,
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> str:
        """监听事件（IEventService接口）"""
        return self.subscribe(event_name, callback, priority)

    def off(self, event_name: str, listener_id: str) -> bool:
        """取消监听事件（IEventService接口）"""
        return self.unsubscribe(event_name, listener_id)

    def once(
        self,
        event_name: str,
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> str:
        """一次性监听事件（IEventService接口）"""
        return self.subscribe(event_name, callback, priority, is_once=True)

    def get_listener_count(self, event_name: str) -> int:
        """获取监听器数量（IEventService接口）"""
        with self._lock:
            return len(self._listeners.get(event_name, []))

    def get_event_names(self) -> List[str]:
        """获取所有事件名称（IEventService接口）"""
        with self._lock:
            return list(self._listeners.keys())

    def total_listeners(self) -> int:
        """获取监听器总数（IEventService接口）"""
        with self._lock:
            return sum(len(listeners) for listeners in self._listeners.values())

    def clear_listeners(self, event_name: str = None) -> int:
        """清除监听器（IEventService接口）"""
        if event_name:
            return self.unsubscribe_all(event_name)
        else:
            self.clear_all_listeners()
            return 0

    def clear_all_listeners(self) -> None:
        """清除所有监听器"""
        with self._lock:
            for event_name in list(self._listeners.keys()):
                self.unsubscribe_all(event_name)

        if self.logger:
            self.logger.log_audio_event("All event listeners cleared", {})
