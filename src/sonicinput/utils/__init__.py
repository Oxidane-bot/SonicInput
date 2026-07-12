"""Shared diagnostics, exceptions, and logging."""

from .dependency_diagnostics import dependency_diagnostics  # noqa: F401
from .environment_validator import environment_validator  # noqa: F401
from .error_messages import ErrorMessageTranslator, get_user_friendly_error
from .exceptions import *  # noqa: F403, F401
from .startup_diagnostics import startup_diagnostics  # noqa: F401

# Import the unified logging system.
from .unified_logger import (  # noqa: F401
    LogCategory,
    LogLevel,
    TraceContext,
    app_logger_compat,
    logger,
    unified_logger,
)

app_logger = app_logger_compat

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
    "ErrorMessageTranslator",
    "get_user_friendly_error",
]

__all__.extend(
    [
        "logger",
        "unified_logger",
        "LogLevel",
        "LogCategory",
        "TraceContext",
        "app_logger",
    ]
)
