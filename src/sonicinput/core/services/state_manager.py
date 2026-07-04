"""状态管理器

提供线程安全的全局状态管理功能，解决悬浮窗状态不一致问题。
支持状态订阅、历史记录和类型安全的状态操作。
"""

import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from ...utils import app_logger
from ..base.lifecycle_component import LifecycleComponent
from ..interfaces import EventPriority, IEventService
from ..services.events import Events
from ..interfaces.state import AppState, IStateManager, RecordingState

T = TypeVar("T")


@dataclass
class StateChange:
    """状态变更记录"""

    key: str
    old_value: Any
    new_value: Any
    timestamp: float = field(default_factory=time.time)
    source: str = ""


@dataclass
class StateSubscriber:
    """状态订阅者信息"""

    id: str
    callback: Callable[[Any, Any], None]
    created_at: float = field(default_factory=time.time)
    call_count: int = 0
    last_called: float = 0.0


class StateManager(LifecycleComponent, IStateManager):
    """状态管理器

    提供线程安全的全局状态管理功能。
    解决悬浮窗等组件的状态不一致问题。
    """

    def __init__(
        self, event_service: Optional[IEventService] = None, max_history: int = 100
    ):
        """初始化状态管理器

        Args:
            event_service: 事件服务实例，用于发送状态变更事件
            max_history: 最大状态变更历史记录数量
        """
        super().__init__("StateManager")
        self._event_service = event_service
        self._max_history = max_history
        self._states: Dict[str, Any] = {}
        self._subscribers: Dict[str, List[StateSubscriber]] = defaultdict(list)
        self._history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._lock = threading.RLock()

        app_logger.log_audio_event(
            "StateManager initialized",
            {
                "max_history": max_history,
                "event_service_enabled": self._event_service is not None,
            },
        )

    def _do_start(self) -> bool:
        """Start state manager

        Returns:
            True if start successful
        """
        try:
            # Initialize default states
            self._initialize_default_states()

            app_logger.log_audio_event("StateManager started", {})
            return True

        except Exception as e:
            app_logger.log_error(e, "StateManager_start")
            return False

    def _do_stop(self) -> bool:
        """Stop state manager and cleanup resources

        Returns:
            True if stop successful
        """
        try:
            # Unsubscribe all subscribers
            with self._lock:
                subscriber_count = sum(len(subs) for subs in self._subscribers.values())
                self._subscribers.clear()

                # Clear state history
                history_count = sum(len(hist) for hist in self._history.values())
                self._history.clear()

            app_logger.log_audio_event(
                "StateManager stopped",
                {
                    "subscribers_cleared": subscriber_count,
                    "history_cleared": history_count,
                },
            )
            return True

        except Exception as e:
            app_logger.log_error(e, "StateManager_stop")
            return False

    def _initialize_default_states(self) -> None:
        """初始化默认状态"""
        with self._lock:
            self._states.update(
                {
                    "app_state": AppState.STARTING,
                    "recording_state": RecordingState.IDLE,
                    "overlay_visible": False,
                    "overlay_position": {"x": 0, "y": 0},
                    "audio_level": 0.0,
                    "model_loaded": False,
                    "hotkey_enabled": True,
                    "last_transcription": "",
                    "processing_progress": 0.0,
                    "error_message": None,
                    "last_error_time": None,
                }
            )

    def set_state(self, key: str, value: Any) -> None:
        """设置状态值

        Args:
            key: 状态键名
            value: 状态值
        """
        with self._lock:
            old_value = self._states.get(key)

            # 如果值没有变化，直接返回
            if old_value == value:
                return

            # 更新状态
            self._states[key] = value

            # 记录状态变更
            change = StateChange(
                key=key, old_value=old_value, new_value=value, source="state_manager"
            )
            self._history[key].append(change)

            # 获取订阅者副本
            subscribers = self._subscribers[key].copy()

        # 在锁外执行回调，避免死锁
        for subscriber in subscribers:
            try:
                subscriber.callback(old_value, value)

                # 更新订阅者统计
                with self._lock:
                    subscriber.call_count += 1
                    subscriber.last_called = time.time()

            except Exception as e:
                app_logger.log_error(e, f"state_subscriber_{key}_{subscriber.id}")

        # 发送状态变更事件
        if self._event_service:
            self._event_service.emit(
                Events.STATE_CHANGED,
                {
                    "key": key,
                    "old_value": old_value,
                    "new_value": value,
                    "timestamp": datetime.now().isoformat(),
                },
                EventPriority.NORMAL,
            )

        app_logger.log_audio_event(
            "State changed",
            {
                "key": key,
                "old_value": str(old_value),
                "new_value": str(value),
                "subscribers_notified": len(subscribers),
            },
        )

    def get_state(self, key: str, default: Optional[T] = None) -> T:
        """获取状态值

        Args:
            key: 状态键名
            default: 默认值

        Returns:
            状态值，不存在时返回默认值
        """
        with self._lock:
            return cast(T, self._states.get(key, default))

    def has_state(self, key: str) -> bool:
        """检查状态是否存在

        Args:
            key: 状态键名

        Returns:
            状态是否存在
        """
        with self._lock:
            return key in self._states

    def delete_state(self, key: str) -> bool:
        """删除状态

        Args:
            key: 状态键名

        Returns:
            是否删除成功
        """
        with self._lock:
            if key in self._states:
                old_value = self._states[key]
                del self._states[key]

                # 记录删除操作
                change = StateChange(
                    key=key, old_value=old_value, new_value=None, source="state_manager"
                )
                self._history[key].append(change)

                app_logger.log_audio_event(
                    "State deleted", {"key": key, "old_value": str(old_value)}
                )

                return True
            return False

    def clear_all_states(self) -> None:
        """清除所有状态"""
        with self._lock:
            count = len(self._states)
            self._states.clear()
            self._history.clear()

            app_logger.log_audio_event("All states cleared", {"cleared_count": count})

    def get_all_states(self) -> Dict[str, Any]:
        """获取所有状态

        Returns:
            状态字典的副本
        """
        with self._lock:
            return self._states.copy()

    def subscribe(self, key: str, callback: Callable[[Any, Any], None]) -> str:
        """订阅状态变更

        Args:
            key: 状态键名
            callback: 回调函数，参数为 (旧值, 新值)

        Returns:
            订阅ID，用于取消订阅
        """
        subscription_id = str(uuid.uuid4())
        subscriber = StateSubscriber(id=subscription_id, callback=callback)

        with self._lock:
            self._subscribers[key].append(subscriber)

        app_logger.log_audio_event(
            "State subscription added",
            {
                "key": key,
                "subscription_id": subscription_id,
                "total_subscribers": len(self._subscribers[key]),
            },
        )

        return subscription_id

    def unsubscribe(self, key: str, subscription_id: str) -> bool:
        """取消状态订阅

        Args:
            key: 状态键名
            subscription_id: 订阅ID

        Returns:
            是否取消成功
        """
        with self._lock:
            if key not in self._subscribers:
                return False

            for subscriber in self._subscribers[key]:
                if subscriber.id == subscription_id:
                    self._subscribers[key].remove(subscriber)

                    app_logger.log_audio_event(
                        "State subscription removed",
                        {
                            "key": key,
                            "subscription_id": subscription_id,
                            "remaining_subscribers": len(self._subscribers[key]),
                        },
                    )

                    # 如果没有订阅者了，删除键
                    if not self._subscribers[key]:
                        del self._subscribers[key]

                    return True

        return False

    def unsubscribe_all(self, key: str) -> int:
        """取消指定状态的所有订阅

        Args:
            key: 状态键名

        Returns:
            取消的订阅数量
        """
        with self._lock:
            if key not in self._subscribers:
                return 0

            count = len(self._subscribers[key])
            del self._subscribers[key]

            app_logger.log_audio_event(
                "All state subscriptions removed", {"key": key, "removed_count": count}
            )

            return count

    def set_app_state(self, state: AppState) -> None:
        """设置应用程序状态

        Args:
            state: 应用程序状态
        """
        old_state = self.get_app_state()
        self.set_state("app_state", state)

        # 发送专门的应用状态变更事件
        if self._event_service and old_state != state:
            self._event_service.emit(
                Events.APP_STATE_CHANGED,
                {
                    "old_state": old_state.value,
                    "new_state": state.value,
                    "timestamp": datetime.now().isoformat(),
                },
                EventPriority.HIGH,
            )

    def get_app_state(self) -> AppState:
        """获取应用程序状态

        Returns:
            当前应用程序状态
        """
        return self.get_state("app_state", AppState.IDLE)

    def set_recording_state(self, state: RecordingState) -> None:
        """设置录音状态

        Args:
            state: 录音状态
        """
        old_state = self.get_recording_state()
        self.set_state("recording_state", state)

        # 发送专门的录音状态变更事件
        if self._event_service and old_state != state:
            self._event_service.emit(
                Events.RECORDING_STATE_CHANGED,
                {
                    "old_state": old_state.value,
                    "new_state": state.value,
                    "timestamp": datetime.now().isoformat(),
                },
                EventPriority.HIGH,
            )

    def get_recording_state(self) -> RecordingState:
        """获取录音状态

        Returns:
            当前录音状态
        """
        return self.get_state("recording_state", RecordingState.IDLE)

    def is_recording(self) -> bool:
        """是否正在录音

        Returns:
            是否正在录音
        """
        recording_state = self.get_recording_state()
        return recording_state in [RecordingState.STARTING, RecordingState.RECORDING]

    def is_processing(self) -> bool:
        """是否正在处理

        Returns:
            是否正在处理
        """
        app_state = self.get_app_state()
        recording_state = self.get_recording_state()
        return (
            app_state == AppState.PROCESSING
            or recording_state == RecordingState.PROCESSING
        )

    def is_ready_for_input(self) -> bool:
        """是否准备好接收输入

        Returns:
            是否准备好接收输入
        """
        app_state = self.get_app_state()
        return app_state == AppState.INPUT_READY

    def get_state_history(self, key: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取状态变更历史

        Args:
            key: 状态键名
            limit: 历史记录限制数量

        Returns:
            状态变更历史列表
        """
        with self._lock:
            if key not in self._history:
                return []

            history = list(self._history[key])[-limit:]
            return [
                {
                    "key": change.key,
                    "old_value": change.old_value,
                    "new_value": change.new_value,
                    "timestamp": change.timestamp,
                    "timestamp_iso": datetime.fromtimestamp(
                        change.timestamp
                    ).isoformat(),
                    "source": change.source,
                }
                for change in history
            ]

    def get_state_statistics(self) -> Dict[str, Any]:
        """获取状态统计信息

        Returns:
            状态统计信息
        """
        with self._lock:
            return {
                "total_states": len(self._states),
                "total_subscribers": self.total_subscribers,
                "total_history_entries": sum(
                    len(history) for history in self._history.values()
                ),
                "states_with_subscribers": len(self._subscribers),
                "current_app_state": self.get_app_state().value,
                "current_recording_state": self.get_recording_state().value,
                "is_recording": self.is_recording(),
                "is_processing": self.is_processing(),
                "is_ready_for_input": self.is_ready_for_input(),
                "timestamp": datetime.now().isoformat(),
            }

    def reset_to_idle(self) -> None:
        """重置到空闲状态"""
        with self._lock:
            self.set_app_state(AppState.IDLE)
            self.set_recording_state(RecordingState.IDLE)
            self.set_state("processing_progress", 0.0)
            self.set_state("error_message", None)
            self.set_state("last_error_time", None)

            app_logger.log_audio_event("State reset to idle", {})

    @property
    def total_subscribers(self) -> int:
        """总订阅者数量"""
        with self._lock:
            return sum(len(subscribers) for subscribers in self._subscribers.values())
