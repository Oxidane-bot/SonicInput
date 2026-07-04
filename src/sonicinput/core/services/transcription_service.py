"""转录服务 - 重构后的新实现

重构目标：
- 将1098行的单一大类拆分为5个专职组件
- 每个组件职责单一，高内聚低耦合
- 接口更简洁，使用更方便
- 便于测试和扩展

新的架构：
1. TranscriptionCore - 纯转录功能
2. ModelManager - 模型生命周期管理
3. StreamingCoordinator - 流式转录协调
4. TaskQueueManager - 任务队列管理
5. ErrorRecoveryService - 错误恢复服务

使用方法：
```python
# 创建服务
service = RefactoredTranscriptionService(speech_service_factory, event_service)

# 基本转录
result = service.transcribe_sync(audio_data, language="zh", temperature=0.0)

# 异步转录
task_id = service.transcribe(audio_data, callback=on_result, error_callback=on_error)

# 流式转录
service.start_streaming()
chunk_id = service.add_streaming_chunk(audio_chunk)
# ... 继续添加块
stats = service.stop_streaming()
```

注意：这个API与旧版本不同，是为了更好的设计而故意修改的。
如需兼容旧代码，请修改调用方而不是在这里做适配。
"""

# 直接导入重构后的实现
# 导出任务相关类型
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import numpy as np

from .error_recovery_service import ErrorCategory, ErrorRecoveryService, ErrorSeverity
from .model_manager import ModelManager, ModelState
from .streaming_coordinator import StreamingChunk, StreamingCoordinator
from .task_queue_manager import TaskPriority, TaskQueueManager, TaskStatus

# 导出新的类名和类型
from .transcription_core import TranscriptionCore
from .transcription_service_refactored import RefactoredTranscriptionService


class TranscriptionTaskType(Enum):
    """转录任务类型"""

    TRANSCRIBE = "transcribe"
    LOAD_MODEL = "load_model"
    UNLOAD_MODEL = "unload_model"
    RELOAD_MODEL = "reload_model"
    SHUTDOWN = "shutdown"


@dataclass
class TranscriptionTask:
    """转录任务"""

    task_type: TranscriptionTaskType
    audio_data: Optional[np.ndarray] = None
    language: Optional[str] = None
    temperature: float = 0.0
    callback: Optional[Callable] = None
    error_callback: Optional[Callable] = None
    model_name: Optional[str] = None
    task_id: Optional[str] = None


@dataclass
class TranscriptionResult:
    """转录结果"""

    success: bool
    text: str = ""
    language: Optional[str] = None
    confidence: float = 0.0
    segments: Optional[list] = None
    transcription_time: float = 0.0
    error: Optional[str] = None
    recovery_suggestions: Optional[list] = None

    def __post_init__(self):
        if self.segments is None:
            self.segments = []
        if self.recovery_suggestions is None:
            self.recovery_suggestions = []


# 主要API - 直接使用重构后的实现
TranscriptionService = RefactoredTranscriptionService

__all__ = [
    "TranscriptionService",
    "RefactoredTranscriptionService",
    # 组件类
    "TranscriptionCore",
    "ModelManager",
    "StreamingCoordinator",
    "TaskQueueManager",
    "ErrorRecoveryService",
    # 数据类型
    "TranscriptionTask",
    "TranscriptionResult",
    "TranscriptionTaskType",
    "ModelState",
    "TaskPriority",
    "TaskStatus",
    "StreamingChunk",
    "ErrorSeverity",
    "ErrorCategory",
]
