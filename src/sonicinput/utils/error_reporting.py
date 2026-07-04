"""Consistent error reporting mechanisms

Provides unified error reporting, handling, and recovery patterns
across the Sonic Input codebase.
"""

import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from ..utils import app_logger
from .common_utils import ComponentTracker, EventCounter, log_with_context
from .exceptions import ErrorSeverity, VoiceInputError, wrap_exception

T = TypeVar("T")


class ErrorReportingConfig:
    """Configuration for error reporting behavior"""

    def __init__(self):
        self.log_all_errors = True
        self.log_warnings = True
        self.console_output = False
        self.file_output = True
        self.max_error_history = 100
        self.error_notification_threshold = 5  # errors per minute
        self.auto_recovery_enabled = True
        self.user_notification_enabled = True


class ErrorReporter:
    """Centralized error reporting and handling system"""

    def __init__(self, config: Optional[ErrorReportingConfig] = None):
        self.config = config or ErrorReportingConfig()
        self._error_history: List[Dict[str, Any]] = []
        self._error_counter = EventCounter()
        self._component_tracker = ComponentTracker()
        self._lock = threading.RLock()
        self._error_handlers: Dict[str, List[Callable]] = {}
        self._recovery_handlers: Dict[str, List[Callable]] = {}

    def report_error(
        self,
        error: Union[Exception, VoiceInputError],
        component: str = "unknown",
        context: Optional[Dict[str, Any]] = None,
        attempt_recovery: bool = True,
    ) -> bool:
        """Report an error with optional recovery attempt

        Args:
            error: Exception or VoiceInputError to report
            component: Component where error occurred
            context: Additional context information
            attempt_recovery: Whether to attempt automatic recovery

        Returns:
            True if error was handled/recovered, False otherwise
        """
        # Wrap standard exceptions in VoiceInputError
        if not isinstance(error, VoiceInputError):
            error = wrap_exception(error)

        # Add component context
        if context:
            error.context.update(context)
        error.context["reporting_component"] = component

        # Record error in history
        self._record_error(error, component)

        # Log the error
        self._log_error(error, component)

        return True

    def _record_error(self, error: VoiceInputError, component: str) -> None:
        """Record error in history with size management"""
        with self._lock:
            error_record = {
                **error.to_dict(),
                "component": component,
                "stack_trace": traceback.format_exc()
                if error.original_exception
                else None,
            }

            self._error_history.append(error_record)

            # Manage history size
            if len(self._error_history) > self.config.max_error_history:
                self._error_history = self._error_history[
                    -self.config.max_error_history :
                ]

    def _log_error(self, error: VoiceInputError, component: str) -> None:
        """Log error using the application logger"""
        log_data = error.to_dict()
        log_data["component"] = component

        if error.severity == ErrorSeverity.CRITICAL:
            app_logger.log_error(error, f"CRITICAL_{component}")
        elif error.severity == ErrorSeverity.HIGH:
            app_logger.log_error(error, f"HIGH_{component}")
        else:
            app_logger.log_audio_event(f"Error in {component}", log_data)


# Global error reporter instance
_global_error_reporter: Optional[ErrorReporter] = None
_reporter_lock = threading.RLock()


def get_error_reporter() -> ErrorReporter:
    """Get the global error reporter instance"""
    global _global_error_reporter
    with _reporter_lock:
        if _global_error_reporter is None:
            _global_error_reporter = ErrorReporter()
        return _global_error_reporter


def setup_error_reporter(
    config: Optional[ErrorReportingConfig] = None,
) -> ErrorReporter:
    """Setup the global error reporter with configuration"""
    global _global_error_reporter
    with _reporter_lock:
        _global_error_reporter = ErrorReporter(config)
        return _global_error_reporter


def report_error(
    error: Union[Exception, VoiceInputError],
    component: str = "unknown",
    context: Optional[Dict[str, Any]] = None,
    attempt_recovery: bool = True,
) -> bool:
    """Report an error using the global error reporter"""
    return get_error_reporter().report_error(
        error, component, context, attempt_recovery
    )


def report_warning(
    message: str, component: str = "unknown", context: Optional[Dict[str, Any]] = None
) -> None:
    """Report a warning using the global error reporter"""
    warning_data = {
        "message": message,
        "component": component,
        "context": context or {},
        "timestamp": datetime.now().isoformat(),
        "type": "warning",
    }
    log_with_context(f"Warning: {message}", warning_data, component)


@contextmanager
def error_context(
    component: str,
    context: Optional[Dict[str, Any]] = None,
    suppress_exceptions: bool = False,
    return_on_error: Any = None,
):
    """Context manager for automatic error reporting

    Args:
        component: Component name for error reporting
        context: Additional context information
        suppress_exceptions: Whether to suppress exceptions after reporting
        return_on_error: Value to return if exception occurs and is suppressed

    Usage:
        with error_context("my_component"):
            risky_operation()

        # Or with suppression:
        result = None
        with error_context("my_component", suppress_exceptions=True, return_on_error=False):
            result = risky_operation()
    """
    try:
        yield
    except Exception as e:
        report_error(e, component, context)
        if suppress_exceptions:
            return return_on_error
        else:
            raise


def safe_call(
    func: Callable[..., T],
    *args,
    component: str = "unknown",
    context: Optional[Dict[str, Any]] = None,
    default_return: Optional[T] = None,
    **kwargs,
) -> Optional[T]:
    """Safely call a function with automatic error reporting

    Args:
        func: Function to call
        *args: Function arguments
        component: Component name for error reporting
        context: Additional context information
        default_return: Value to return on error
        **kwargs: Function keyword arguments

    Returns:
        Function result or default_return on error
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        report_error(e, component, context)
        return default_return


def setup_default_error_reporting() -> None:
    """Setup default error reporting configuration"""
    config = ErrorReportingConfig()
    setup_error_reporter(config)
