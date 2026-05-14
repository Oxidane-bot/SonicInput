"""Enhanced utilities module with unified logging system"""

from .dependency_diagnostics import dependency_diagnostics  # noqa: F401
from .environment_validator import environment_validator  # noqa: F401
from .exceptions import *  # noqa: F403, F401
from .startup_diagnostics import startup_diagnostics  # noqa: F401

# Import unified logging system (新)
# 注意：不导入from .logger避免循环导入
try:
    from .unified_logger import (  # noqa: F401
        LogCategory,
        LogLevel,
        TraceContext,
        app_logger_compat,
        logger,
        unified_logger,
    )

    UNIFIED_LOGGING_AVAILABLE = True

    # 向后兼容：保留旧接口别名
    app_logger = app_logger_compat
    optimized_logger = logger
    structured_logger = logger
except ImportError as e:
    print(f"Warning: Could not import unified_logger: {e}")
    UNIFIED_LOGGING_AVAILABLE = False
    logger = None
    app_logger = None
    optimized_logger = None
    structured_logger = None

# 兼容旧的函数接口
if UNIFIED_LOGGING_AVAILABLE:

    def log_component_lifecycle(
        component: str, event: str, state: str = None, details: dict = None
    ):
        """兼容接口"""
        ctx = {"event_type": "lifecycle", "lifecycle_event": event}
        if state:
            ctx["state"] = state
        if details:
            ctx.update(details)
        logger.info(
            f"Lifecycle: {component} {event}", LogCategory.STARTUP, ctx, component
        )

    def log_configuration_change(
        setting: str, old_value, new_value, component: str = "config"
    ):
        """兼容接口"""
        ctx = {
            "event_type": "config_change",
            "setting": setting,
            "old_value": old_value,
            "new_value": new_value,
        }
        logger.info(f"Config Change: {setting}", LogCategory.STARTUP, ctx, component)

    def log_performance_milestone(
        operation: str, duration: float, threshold: float = 1.0, component: str = None
    ):
        """兼容接口"""
        if duration >= threshold:
            logger.performance(operation, duration, details={"threshold": threshold})


# 保留旧的导入兼容（避免立即破坏）
ENHANCED_LOGGING_AVAILABLE = UNIFIED_LOGGING_AVAILABLE

# Import error message translation
try:
    from .error_messages import (  # noqa: F401
        ErrorMessageTranslator,
        get_user_friendly_error,
    )

    ERROR_MESSAGES_AVAILABLE = True
except ImportError:
    ERROR_MESSAGES_AVAILABLE = False

# Import error reporting utilities
try:
    from .error_reporting import (  # noqa: F401
        error_context,
        get_error_reporter,
        report_error,
        report_warning,
        safe_call,
        setup_error_reporter,
    )

    ERROR_REPORTING_AVAILABLE = True
except ImportError:
    ERROR_REPORTING_AVAILABLE = False

# Import common utility helpers
try:
    from .common_utils import (  # noqa: F401
        ComponentTracker,
        EventCounter,
        PerformanceTracker,
        SafeTimer,
        ThreadSafeContainer,
        TimestampTracker,
        log_with_context,
        safe_file_operation,
    )

    UTILITY_MODULES_AVAILABLE = True
except ImportError:
    UTILITY_MODULES_AVAILABLE = False

__all__ = [  # noqa: F405
    # Core exceptions
    "VoiceInputError",
    "AudioRecordingError",
    "WhisperLoadError",
    "OpenRouterAPIError",
    "GroqAPIError",
    "NVIDIAAPIError",
    "OpenAICompatibleAPIError",
    "AIOutputTruncatedError",
    "TextInputError",
    "ConfigurationError",
    "HotkeyRegistrationError",
    "GPUError",
    "ComponentInitializationError",
    "ComponentStateError",
    "NetworkError",
    "ValidationError",
    # Core utilities
    "environment_validator",
    "startup_diagnostics",
    "dependency_diagnostics",
]

# Add unified logging to exports if available
if UNIFIED_LOGGING_AVAILABLE:
    __all__.extend(
        [
            # 新的统一接口
            "logger",
            "unified_logger",
            "LogLevel",
            "LogCategory",
            "TraceContext",
            # 兼容旧接口
            "app_logger",
            "optimized_logger",
            "structured_logger",
            "log_component_lifecycle",
            "log_configuration_change",
            "log_performance_milestone",
        ]
    )

# Add error message translation to exports if available
if ERROR_MESSAGES_AVAILABLE:
    __all__.extend(
        [
            "ErrorMessageTranslator",
            "get_user_friendly_error",
        ]
    )

# Add error reporting to exports if available
if ERROR_REPORTING_AVAILABLE:
    __all__.extend(
        [
            "get_error_reporter",
            "setup_error_reporter",
            "report_error",
            "report_warning",
            "error_context",
            "safe_call",
        ]
    )

# Add utility modules to exports if available
if UTILITY_MODULES_AVAILABLE:
    __all__.extend(
        [
            "ThreadSafeContainer",
            "TimestampTracker",
            "ComponentTracker",
            "EventCounter",
            "SafeTimer",
            "PerformanceTracker",
            "safe_file_operation",
            "log_with_context",
        ]
    )


def get_utils_status() -> dict:
    """Get status of available utility modules"""
    return {
        "enhanced_logging": ENHANCED_LOGGING_AVAILABLE,
        "error_reporting": ERROR_REPORTING_AVAILABLE,
        "utility_modules": UTILITY_MODULES_AVAILABLE,
        "core_modules": True,
    }
