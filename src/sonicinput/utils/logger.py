"""Deprecated logging module - kept for backwards compatibility

This module is deprecated. Use unified_logger instead:
    from sonicinput.utils import logger
"""

# Re-export from unified_logger for backwards compatibility.
# unified_logger only depends on the standard library, so this import cannot
# fail with ImportError; app_logger is always a concrete LegacyLoggerAdapter.
from .unified_logger import app_logger_compat as app_logger  # noqa: F401

__all__ = ["app_logger"]
