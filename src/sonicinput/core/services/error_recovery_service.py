"""错误恢复服务 - 负责转录错误的恢复和处理"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ...utils import app_logger
from ..base.lifecycle_component import LifecycleComponent


class ErrorSeverity(Enum):
    """错误严重程度"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """错误类别"""

    MODEL_ERROR = "model_error"
    AUDIO_ERROR = "audio_error"
    NETWORK_ERROR = "network_error"
    SYSTEM_ERROR = "system_error"
    CONFIG_ERROR = "config_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class RecoveryAction:
    """恢复动作"""

    action_id: str
    description: str
    severity: ErrorSeverity
    action_func: Callable[[], bool]
    auto_recovery: bool = True
    max_attempts: int = 3
    cooldown_period: float = 5.0


@dataclass
class ErrorInfo:
    """错误信息"""

    error_id: str
    exception: Exception
    category: ErrorCategory
    severity: ErrorSeverity
    timestamp: float
    context: Dict[str, Any]
    recovery_attempts: int = 0
    resolved: bool = False


class ErrorRecoveryService(LifecycleComponent):
    """错误恢复服务

    负责错误分类、恢复策略执行和错误统计。
    与具体的业务逻辑解耦，专注于错误处理。
    """

    def __init__(self, event_service=None):
        """初始化错误恢复服务

        Args:
            event_service: 事件服务（可选）
        """
        super().__init__("ErrorRecoveryService")
        self.event_service = event_service

        # 错误跟踪
        self._error_history: List[ErrorInfo] = []
        self._recovery_actions: Dict[str, RecoveryAction] = {}
        self._last_recovery_time: Dict[str, float] = {}

        # 错误统计
        self._error_stats = {
            "total_errors": 0,
            "resolved_errors": 0,
            "auto_recoveries": 0,
            "manual_recoveries": 0,
            "by_category": {},
            "by_severity": {},
        }

    def _do_start(self) -> bool:
        """启动错误恢复服务

        恢复动作必须由持有实际恢复依赖的调用方显式注册。
        """
        app_logger.log_audio_event("ErrorRecoveryService started", {})
        return True

    def _do_stop(self) -> bool:
        """停止错误恢复服务

        清理错误历史和恢复动作
        """
        self.clear_error_history()
        self._recovery_actions.clear()
        self._last_recovery_time.clear()
        app_logger.log_audio_event("ErrorRecoveryService stopped", {})
        return True

    def register_recovery_action(self, action: RecoveryAction) -> None:
        """注册恢复动作

        Args:
            action: 恢复动作对象
        """
        self._recovery_actions[action.action_id] = action
        app_logger.log_audio_event(
            "Recovery action registered",
            {
                "action_id": action.action_id,
                "description": action.description,
                "auto_recovery": action.auto_recovery,
            },
        )

    def handle_error(
        self, exception: Exception, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """处理错误

        Args:
            exception: 异常对象
            context: 错误上下文

        Returns:
            错误处理结果
        """
        # 分析错误
        error_info = self._analyze_error(exception, context)

        # 记录错误
        self._record_error(error_info)

        # 获取恢复建议
        recovery_suggestions = self._get_recovery_suggestions(error_info)

        # 尝试自动恢复
        auto_recovery_result = None
        if error_info.severity in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]:
            auto_recovery_result = self._attempt_auto_recovery(error_info)

        # 构建结果
        result = {
            "error_id": error_info.error_id,
            "category": error_info.category.value,
            "severity": error_info.severity.value,
            "message": str(exception),
            "recovery_suggestions": recovery_suggestions,
            "auto_recovery": auto_recovery_result,
            "timestamp": error_info.timestamp,
        }

        # 发送错误事件
        self._emit_error_event(
            "error_occurred", {"error_info": error_info, "result": result}
        )

        return result

    def _analyze_error(
        self, exception: Exception, context: Optional[Dict[str, Any]]
    ) -> ErrorInfo:
        """分析错误

        Args:
            exception: 异常对象
            context: 错误上下文

        Returns:
            错误信息对象
        """
        error_id = f"error_{int(time.time() * 1000)}"
        error_str = str(exception).lower()

        # 分类错误
        category = self._categorize_error(error_str)
        severity = self._assess_severity(error_str, category)

        return ErrorInfo(
            error_id=error_id,
            exception=exception,
            category=category,
            severity=severity,
            timestamp=time.time(),
            context=context or {},
        )

    def _categorize_error(self, error_str: str) -> ErrorCategory:
        """错误分类

        Args:
            error_str: 错误消息

        Returns:
            错误类别
        """
        # 模型相关错误
        if any(
            keyword in error_str
            for keyword in ["model", "whisper", "cuda", "gpu", "checkpoint"]
        ):
            return ErrorCategory.MODEL_ERROR

        # 音频相关错误
        elif any(
            keyword in error_str
            for keyword in ["audio", "device", "pyaudio", "alsa", "microphone"]
        ):
            return ErrorCategory.AUDIO_ERROR

        # 网络相关错误
        elif any(
            keyword in error_str
            for keyword in ["network", "connection", "timeout", "http", "api"]
        ):
            return ErrorCategory.NETWORK_ERROR

        # 配置相关错误
        elif any(
            keyword in error_str
            for keyword in ["config", "setting", "parameter", "invalid"]
        ):
            return ErrorCategory.CONFIG_ERROR

        # 系统相关错误
        elif any(
            keyword in error_str
            for keyword in ["system", "memory", "disk", "permission"]
        ):
            return ErrorCategory.SYSTEM_ERROR

        return ErrorCategory.UNKNOWN_ERROR

    def _assess_severity(
        self, error_str: str, category: ErrorCategory
    ) -> ErrorSeverity:
        """评估错误严重程度

        Args:
            error_str: 错误消息
            category: 错误类别

        Returns:
            错误严重程度
        """
        # 关键词映射到严重程度
        critical_keywords = ["critical", "fatal", "crash", "corruption"]
        high_keywords = ["failed", "error", "exception", "timeout", "unavailable"]
        medium_keywords = ["warning", "deprecated", "retry"]
        low_keywords = ["info", "notice", "minor"]

        if any(keyword in error_str for keyword in critical_keywords):
            return ErrorSeverity.CRITICAL
        elif any(keyword in error_str for keyword in high_keywords):
            return ErrorSeverity.HIGH
        elif any(keyword in error_str for keyword in medium_keywords):
            return ErrorSeverity.MEDIUM
        elif any(keyword in error_str for keyword in low_keywords):
            return ErrorSeverity.LOW

        # 基于类别的默认严重程度
        default_severity = {
            ErrorCategory.MODEL_ERROR: ErrorSeverity.HIGH,
            ErrorCategory.AUDIO_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.NETWORK_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.SYSTEM_ERROR: ErrorSeverity.HIGH,
            ErrorCategory.CONFIG_ERROR: ErrorSeverity.LOW,
            ErrorCategory.UNKNOWN_ERROR: ErrorSeverity.MEDIUM,
        }

        return default_severity.get(category, ErrorSeverity.MEDIUM)

    def _record_error(self, error_info: ErrorInfo) -> None:
        """记录错误

        Args:
            error_info: 错误信息
        """
        self._error_history.append(error_info)

        # 更新统计
        self._error_stats["total_errors"] += 1

        # 按类别统计
        category = error_info.category.value
        if category not in self._error_stats["by_category"]:
            self._error_stats["by_category"][category] = 0
        self._error_stats["by_category"][category] += 1

        # 按严重程度统计
        severity = error_info.severity.value
        if severity not in self._error_stats["by_severity"]:
            self._error_stats["by_severity"][severity] = 0
        self._error_stats["by_severity"][severity] += 1

        # 限制历史记录长度
        if len(self._error_history) > 1000:
            self._error_history = self._error_history[-500:]

        app_logger.log_error(
            error_info.exception, f"recorded_error_{error_info.category.value}"
        )

    def _get_recovery_suggestions(self, error_info: ErrorInfo) -> List[str]:
        """获取恢复建议

        Args:
            error_info: 错误信息

        Returns:
            恢复建议列表
        """
        suggestions = []

        # 基于错误类别的通用建议
        if error_info.category == ErrorCategory.MODEL_ERROR:
            suggestions.extend(
                [
                    "检查模型文件是否存在",
                    "尝试重新加载模型",
                    "检查GPU驱动和CUDA版本",
                    "尝试切换到CPU模式",
                ]
            )

        elif error_info.category == ErrorCategory.AUDIO_ERROR:
            suggestions.extend(
                [
                    "检查音频设备连接",
                    "尝试重新初始化音频设备",
                    "检查音频权限设置",
                    "尝试使用默认音频设备",
                ]
            )

        elif error_info.category == ErrorCategory.NETWORK_ERROR:
            suggestions.extend(
                ["检查网络连接", "验证API密钥和配置", "稍后重试", "检查防火墙设置"]
            )

        elif error_info.category == ErrorCategory.SYSTEM_ERROR:
            suggestions.extend(
                ["检查系统资源使用情况", "重启应用程序", "检查文件权限", "清理临时文件"]
            )

        # 基于错误消息的特定建议
        error_str = str(error_info.exception).lower()

        if "out of memory" in error_str:
            suggestions.append("关闭其他应用程序释放内存")
            suggestions.append("尝试使用较小的模型")

        elif "device unavailable" in error_str:
            suggestions.append("检查音频设备是否被其他程序占用")
            suggestions.append("尝试重新插拔音频设备")

        elif "invalid api key" in error_str:
            suggestions.append("验证API密钥配置")
            suggestions.append("检查API账户余额")

        return suggestions

    def _attempt_auto_recovery(self, error_info: ErrorInfo) -> Optional[Dict[str, Any]]:
        """尝试自动恢复

        Args:
            error_info: 错误信息

        Returns:
            恢复结果，如果不进行自动恢复则返回None
        """
        # 根据错误类别选择恢复动作
        recovery_actions = self._get_recovery_actions_for_error(error_info)

        for action in recovery_actions:
            if not action.auto_recovery:
                continue

            # 检查冷却时间
            if not self._check_cooldown(action.action_id):
                continue

            # 检查尝试次数
            if error_info.recovery_attempts >= action.max_attempts:
                continue

            # 执行恢复动作
            success = self._execute_recovery_action(action, error_info)

            if success:
                self._error_stats["auto_recoveries"] += 1
                error_info.resolved = True

                return {
                    "action_id": action.action_id,
                    "description": action.description,
                    "success": True,
                    "attempt": error_info.recovery_attempts,
                }

        return None

    def _get_recovery_actions_for_error(
        self, error_info: ErrorInfo
    ) -> List[RecoveryAction]:
        """根据错误获取恢复动作

        Args:
            error_info: 错误信息

        Returns:
            恢复动作列表
        """
        action_ids = []

        if error_info.category == ErrorCategory.MODEL_ERROR:
            if (
                "gpu" in str(error_info.exception).lower()
                or "cuda" in str(error_info.exception).lower()
            ):
                action_ids.append("switch_to_cpu")
            action_ids.append("reload_model")

        elif error_info.category == ErrorCategory.AUDIO_ERROR:
            action_ids.extend(["reset_audio_device", "fallback_audio_device"])

        elif error_info.category == ErrorCategory.SYSTEM_ERROR:
            if "memory" in str(error_info.exception).lower():
                action_ids.append("clear_cache")

        return [
            action
            for action_id in action_ids
            if (action := self._recovery_actions.get(action_id)) is not None
        ]

    def _check_cooldown(self, action_id: str) -> bool:
        """检查冷却时间

        Args:
            action_id: 动作ID

        Returns:
            True如果可以执行
        """
        action = self._recovery_actions.get(action_id)
        if not action:
            return False

        last_time = self._last_recovery_time.get(action_id, 0)
        return (time.time() - last_time) >= action.cooldown_period

    def _execute_recovery_action(
        self, action: RecoveryAction, error_info: ErrorInfo
    ) -> bool:
        """执行恢复动作

        Args:
            action: 恢复动作
            error_info: 错误信息

        Returns:
            True如果恢复成功
        """
        try:
            app_logger.log_audio_event(
                "Attempting auto recovery",
                {
                    "action_id": action.action_id,
                    "error_id": error_info.error_id,
                    "attempt": error_info.recovery_attempts + 1,
                },
            )

            # 更新冷却时间
            self._last_recovery_time[action.action_id] = time.time()

            # 更新尝试次数
            error_info.recovery_attempts += 1

            # 执行恢复动作
            success = action.action_func()

            if success:
                app_logger.log_audio_event(
                    "Auto recovery successful",
                    {"action_id": action.action_id, "error_id": error_info.error_id},
                )

                # 发送恢复成功事件
                self._emit_error_event(
                    "error_auto_resolved",
                    {"error_id": error_info.error_id, "action_id": action.action_id},
                )

            return success

        except Exception as e:
            app_logger.log_error(e, "execute_recovery_action")
            return False

    def _emit_error_event(self, event_name: str, data: Dict[str, Any]) -> None:
        """发送错误事件

        Args:
            event_name: 事件名称
            data: 事件数据
        """
        if self.event_service:
            try:
                self.event_service.emit(event_name, data)
            except Exception as e:
                app_logger.log_error(e, "emit_error_event")

    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计

        Returns:
            错误统计字典
        """
        stats = self._error_stats.copy()
        stats.update(
            {
                "recent_errors": len(
                    [e for e in self._error_history if time.time() - e.timestamp < 3600]
                ),
                "total_errors_in_history": len(self._error_history),
                "recovery_actions_count": len(self._recovery_actions),
            }
        )
        return stats

    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的错误

        Args:
            limit: 返回的错误数量限制

        Returns:
            最近错误列表
        """
        recent_errors = sorted(
            self._error_history, key=lambda e: e.timestamp, reverse=True
        )[:limit]

        return [
            {
                "error_id": e.error_id,
                "category": e.category.value,
                "severity": e.severity.value,
                "message": str(e.exception),
                "timestamp": e.timestamp,
                "recovery_attempts": e.recovery_attempts,
                "resolved": e.resolved,
            }
            for e in recent_errors
        ]

    def clear_error_history(self) -> None:
        """清理错误历史"""
        self._error_history.clear()
        app_logger.log_audio_event("Error history cleared", {})
