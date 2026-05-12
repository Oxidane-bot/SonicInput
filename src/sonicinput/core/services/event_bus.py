"""统一事件总线 - 重构后的新实现

重构目标：
- 支持动态事件类型注册
- 支持事件插件系统
- 支持事件验证和命名空间
- 保持高性能和线程安全

新的特性：
1. 动态事件注册 - 运行时注册新事件类型
2. 事件插件系统 - 扩展事件处理能力
3. 事件验证 - 数据完整性检查
4. 命名空间 - 避免事件名称冲突
5. 事件元数据 - 丰富的描述信息

使用方法：
```python
# 创建事件系统
event_bus = DynamicEventSystem()

# 注册事件类型
event_bus.register_event_type(
    "my_custom_event",
    description="我的自定义事件",
    namespace="my_module"
)

# 订阅事件
listener_id = event_bus.subscribe("my_custom_event", callback)

# 发出事件
event_bus.emit("my_custom_event", {"data": "value"})

# 添加插件
event_bus.add_plugin(MyEventPlugin())
```

注意：新的API更强大且灵活，不再受限于预定义的事件枚举。
"""

# 直接导入动态事件系统
from .dynamic_event_system import (
    DynamicEventSystem,
    EventMetadata,
)
from .events import Events

# 主要API - 直接使用动态事件系统
EventBus = DynamicEventSystem


# 导出便利的事件名称常量

__all__ = [
    "EventBus",
    "DynamicEventSystem",
    "EventMetadata",
    "Events",
]
