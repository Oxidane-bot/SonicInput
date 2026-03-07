"""核心接口定义模块

统一的接口定义，用于实现高内聚、低耦合的架构设计。
所有服务和组件都应该依赖接口而不是具体实现。
"""

from dataclasses import dataclass
from datetime import datetime

# Interfaces added after Phase 1.2 cleanup (missing definitions)
from typing import Optional

from .ai import IAIService
from .audio import IAudioService
from .config import IConfigService
from .controller import (
    IAIProcessingController,
    IInputController,
    IRecordingController,
    ITranscriptionController,
)
from .event import EventPriority, IEventService
from .hotkey import IHotkeyService
from .input import IInputService
from .lifecycle import ComponentState, ILifecycleManaged, ILifecycleManager
from .speech import ISpeechService
from .state import AppState, IStateManager, RecordingState
from .storage import ICacheService, IStorageService
from .ui import IOverlayComponent, ITrayComponent, IUIComponent


@dataclass
class HistoryRecord:
    """历史记录数据类

    完整记录包含：
    - 基础信息（id, timestamp, duration）
    - 音频文件路径
    - 转录结果（text, provider, status, error）
    - AI优化结果（optimized_text, provider, status, error）
    - 最终文本（final_text）
    """

    id: str
    timestamp: datetime
    audio_file_path: str
    duration: float
    transcription_text: str
    transcription_provider: str
    transcription_status: str
    streaming_mode: str = "unknown"
    transcription_duration: float = 0.0
    used_fallback: bool = False
    fallback_type: str = "none"
    fallback_reason: Optional[str] = None
    diagnostics_collected: bool = True
    reprocess_parent_id: Optional[str] = None
    transcription_error: Optional[str] = None
    ai_optimized_text: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_status: str = "pending"
    ai_error: Optional[str] = None
    final_text: str = ""


__all__ = [
    # 核心服务接口
    "IConfigService",
    "IAudioService",
    "ISpeechService",
    "IAIService",
    "IInputService",
    "IHotkeyService",
    "IEventService",
    "EventPriority",
    # UI组件接口
    "IUIComponent",
    "IOverlayComponent",
    "ITrayComponent",
    # 数据存储接口
    "IStorageService",
    "ICacheService",
    # 生命周期管理接口
    "ILifecycleManaged",
    "ILifecycleManager",
    # 状态管理接口
    "IStateManager",
    "AppState",
    "RecordingState",
    "ComponentState",
    # 控制器接口
    "IRecordingController",
    "ITranscriptionController",
    "IAIProcessingController",
    "IInputController",
    # Data types
    "HistoryRecord",
]
