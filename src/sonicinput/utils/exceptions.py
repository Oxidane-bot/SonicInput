"""Enhanced exception hierarchy for Sonic Input

Provides structured error handling with context information,
error codes, and recovery suggestions.
"""

import time
from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorSeverity(Enum):
    """Error severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better classification"""

    INITIALIZATION = "initialization"
    CONFIGURATION = "configuration"
    AUDIO = "audio"
    AI_SERVICE = "ai_service"
    UI = "ui"
    SYSTEM = "system"
    NETWORK = "network"
    VALIDATION = "validation"
    LIFECYCLE = "lifecycle"
    HOTKEY = "hotkey"
    GPU = "gpu"


class VoiceInputError(Exception):
    """Enhanced base exception for Sonic Input

    Provides structured error information including:
    - Error codes for programmatic handling
    - Context information for debugging
    - Severity levels for appropriate response
    - Recovery suggestions for user guidance
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        recovery_suggestions: Optional[List[str]] = None,
        original_exception: Optional[Exception] = None,
    ):
        """
        Args:
            message: Human-readable error message
            error_code: Unique error code for programmatic handling
            category: Error category for classification
            severity: Error severity level
            context: Additional context information
            recovery_suggestions: List of suggested recovery actions
            original_exception: Original exception if this is a wrapper
        """
        super().__init__(message)

        self.message = message
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.recovery_suggestions = recovery_suggestions or []
        self.original_exception = original_exception
        self.timestamp = time.time()  # Set timestamp first
        self.error_code = (
            error_code or self._generate_error_code()
        )  # Then generate error code

        # Add component information if available
        if "component" not in self.context:
            self.context["component"] = self.__class__.__name__

    def _generate_error_code(self) -> str:
        """Generate a default error code based on class name"""
        class_name = self.__class__.__name__
        return f"{class_name.upper()}_{int(self.timestamp)}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context,
            "recovery_suggestions": self.recovery_suggestions,
            "timestamp": self.timestamp,
            "exception_type": self.__class__.__name__,
            "original_exception": str(self.original_exception)
            if self.original_exception
            else None,
        }

    def get_user_message(self) -> str:
        """Get user-friendly error message with recovery suggestions"""
        user_msg = self.message
        if self.recovery_suggestions:
            suggestions = "\n".join(
                f"• {suggestion}" for suggestion in self.recovery_suggestions
            )
            user_msg += f"\n\nSuggested actions:\n{suggestions}"
        return user_msg

    def is_recoverable(self) -> bool:
        """Check if error is potentially recoverable"""
        return (
            len(self.recovery_suggestions) > 0
            and self.severity != ErrorSeverity.CRITICAL
        )


# =============================================================================
# Audio-related Exceptions
# =============================================================================


class AudioRecordingError(VoiceInputError):
    """音频录制相关异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AUDIO,
            severity=kwargs.pop("severity", ErrorSeverity.HIGH),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Check microphone connection and permissions",
                    "Verify audio device is not in use by another application",
                    "Try selecting a different audio device in settings",
                ],
            ),
            **kwargs,
        )


# =============================================================================
# AI Service Exceptions
# =============================================================================


class WhisperLoadError(VoiceInputError):
    """Whisper模型加载异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AI_SERVICE,
            severity=kwargs.pop("severity", ErrorSeverity.HIGH),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Check internet connection for model download",
                    "Verify sufficient disk space for model files",
                    "Try selecting a smaller model in settings",
                    "Restart the application",
                ],
            ),
            **kwargs,
        )


class OpenRouterAPIError(VoiceInputError):
    """OpenRouter API相关异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AI_SERVICE,
            severity=kwargs.pop("severity", ErrorSeverity.MEDIUM),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Check your OpenRouter API key in settings",
                    "Verify internet connection",
                    "Check OpenRouter service status",
                    "Ensure sufficient API credits",
                ],
            ),
            **kwargs,
        )


class GroqAPIError(VoiceInputError):
    """Groq API相关异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AI_SERVICE,
            severity=kwargs.pop("severity", ErrorSeverity.MEDIUM),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Check your Groq API key in settings",
                    "Verify internet connection",
                    "Check Groq service status",
                    "Ensure sufficient API credits",
                ],
            ),
            **kwargs,
        )


class NVIDIAAPIError(VoiceInputError):
    """NVIDIA API相关异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AI_SERVICE,
            severity=kwargs.pop("severity", ErrorSeverity.MEDIUM),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Check your NVIDIA API key in settings",
                    "Verify internet connection",
                    "Check NVIDIA service status",
                    "Ensure sufficient API credits",
                ],
            ),
            **kwargs,
        )


class OpenAICompatibleAPIError(VoiceInputError):
    """OpenAI Compatible API相关异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AI_SERVICE,
            severity=kwargs.pop("severity", ErrorSeverity.MEDIUM),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Check your API endpoint configuration",
                    "Verify API key is correct",
                    "Verify internet connection",
                    "Check API service status",
                ],
            ),
            **kwargs,
        )


class AIOutputTruncatedError(VoiceInputError):
    """AI 输出被服务端截断。"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AI_SERVICE,
            severity=kwargs.pop("severity", ErrorSeverity.MEDIUM),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Increase AI max output tokens",
                    "Use sentence splitting for long recordings",
                    "Fallback to the original transcription",
                ],
            ),
            **kwargs,
        )


# =============================================================================
# UI and Input Exceptions
# =============================================================================


class TextInputError(VoiceInputError):
    """文本输入相关异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.UI,
            severity=kwargs.pop("severity", ErrorSeverity.MEDIUM),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Try clicking in the target application first",
                    "Check if target application supports text input",
                    "Try using clipboard method instead",
                    "Verify target application is not blocking input",
                ],
            ),
            **kwargs,
        )


# =============================================================================
# Configuration and System Exceptions
# =============================================================================


class ConfigurationError(VoiceInputError):
    """配置相关异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIGURATION,
            severity=kwargs.pop("severity", ErrorSeverity.MEDIUM),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Reset to default settings",
                    "Check configuration file permissions",
                    "Verify configuration file format",
                    "Try deleting configuration file to reset",
                ],
            ),
            **kwargs,
        )


class HotkeyRegistrationError(VoiceInputError):
    """快捷键注册异常"""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.HOTKEY,
            severity=kwargs.pop("severity", ErrorSeverity.MEDIUM),
            recovery_suggestions=kwargs.pop(
                "recovery_suggestions",
                [
                    "Try a different hotkey combination",
                    "Check if hotkey is used by another application",
                    "Run application as administrator",
                    "Restart the application",
                ],
            ),
            **kwargs,
        )


# =============================================================================
# Utility Functions
# =============================================================================


def create_exception_from_context(
    exception_type: type, message: str, context: Dict[str, Any]
) -> VoiceInputError:
    """Create exception instance from context information

    Args:
        exception_type: Exception class to instantiate
        message: Error message
        context: Context information

    Returns:
        Exception instance with context
    """
    if not issubclass(exception_type, VoiceInputError):
        exception_type = VoiceInputError

    return exception_type(message=message, context=context)


def wrap_exception(
    original_exception: Exception,
    message: Optional[str] = None,
    exception_type: Optional[type] = None,
) -> VoiceInputError:
    """Wrap a standard exception in VoiceInputError hierarchy

    Args:
        original_exception: Original exception to wrap
        message: Optional custom message
        exception_type: Exception type to use for wrapping

    Returns:
        Wrapped exception
    """
    if isinstance(original_exception, VoiceInputError):
        return original_exception

    if exception_type is None:
        exception_type = VoiceInputError

    if message is None:
        message = str(original_exception)

    return exception_type(
        message=message,
        original_exception=original_exception,
        context={"original_type": type(original_exception).__name__},
    )
