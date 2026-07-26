"""核心逻辑模块初始化

重构后的核心模块，包含统一的服务组件和应用组件。
"""

from .hotkey_manager import HotkeyManager

# 接口定义（仅保留多实现接口）
from .interfaces import IAIService, IInputService, ISpeechService
from .services import StateManager
from .services.events import Events

__all__ = [
    "Events",
    "StateManager",
    # 接口 (仅保留多实现接口)
    "IAIService",
    "ISpeechService",
    "IInputService",
    # 应用组件
    "HotkeyManager",
]
