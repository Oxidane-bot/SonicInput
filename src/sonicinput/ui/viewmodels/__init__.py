"""Fluent 设置视图模型的领域 mixin 包

FluentSettingsViewModel(qml_bridge.py)按领域拆分为多个 mixin,
QML/测试可见的 API(Property/Slot 名称)保持不变。
"""

from .base import SettingsViewModelBase
from .batch_reprocess import BatchReprocessViewModelMixin
from .history import HistoryViewModelMixin
from .hotkeys import HotkeyViewModelMixin
from .review import ReviewViewModelMixin

__all__ = [
    "SettingsViewModelBase",
    "BatchReprocessViewModelMixin",
    "HistoryViewModelMixin",
    "HotkeyViewModelMixin",
    "ReviewViewModelMixin",
]
