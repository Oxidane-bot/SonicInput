"""Hotkey Manager Factory - Selects appropriate backend based on configuration

This module provides a factory function to create the appropriate hotkey manager
based on user configuration and system capabilities.

Available backends:
- win32: Uses RegisterHotKey API (recommended, no admin privileges required)
- pynput: Uses low-level keyboard hooks (requires admin for best experience)
- auto: Automatically selects best backend (admin -> pynput, else win32)
"""

from typing import Any, Callable, Optional

import sys

from ..utils import app_logger
from .interfaces import IHotkeyService


class HotkeyBackendError(Exception):
    """Error creating hotkey backend"""

    pass


def create_hotkey_manager(
    callback: Callable[[str], None], backend: str = "auto", config: Optional[Any] = None
) -> IHotkeyService:
    """Create hotkey manager with specified backend

    Args:
        callback: Callback function when hotkey is triggered
        backend: Backend type ("win32", "pynput", or "auto")
        config: Optional configuration service for reading settings

    Returns:
        IHotkeyService instance

    Raises:
        HotkeyBackendError: If backend creation fails
    """
    # Determine backend
    actual_backend = backend

    if backend == "auto":
        # Prefer pynput when running as admin (best for global hooks), else win32
        is_admin = False
        if sys.platform.startswith("win"):
            try:
                import ctypes

                is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            except Exception:
                is_admin = False

        actual_backend = "pynput" if is_admin else "win32"
        app_logger.log_audio_event(
            "Auto-selecting hotkey backend",
            {"selected": actual_backend, "is_admin": is_admin},
        )

    # Create backend
    try:
        if actual_backend == "win32":
            from .hotkey_manager_win32 import Win32HotkeyManager

            manager: IHotkeyService = Win32HotkeyManager(callback)
            app_logger.log_audio_event(
                "Created Win32 hotkey manager",
                {"backend": "win32", "admin_required": False},
            )
            return manager

        elif actual_backend == "pynput":
            from .hotkey_manager_pynput import PynputHotkeyManager

            manager = PynputHotkeyManager(callback)
            app_logger.log_audio_event(
                "Created pynput hotkey manager",
                {"backend": "pynput", "admin_recommended": True},
            )
            return manager

        else:
            raise HotkeyBackendError(
                f"Unknown hotkey backend: {actual_backend}. "
                f"Valid options: 'win32', 'pynput', 'auto'"
            )

    except ImportError as e:
        error_msg = f"Failed to import {actual_backend} hotkey backend: {str(e)}"
        app_logger.log_error(e, "create_hotkey_manager")

        # Fallback logic
        if backend == "auto":
            # Try the other backend when auto is selected
            if actual_backend == "pynput":
                try:
                    from .hotkey_manager_win32 import Win32HotkeyManager

                    app_logger.log_audio_event(
                        "Falling back to win32 hotkey manager",
                        {"original_backend": actual_backend},
                    )
                    return Win32HotkeyManager(callback)
                except ImportError:
                    pass
            elif actual_backend == "win32":
                try:
                    from .hotkey_manager_pynput import PynputHotkeyManager

                    app_logger.log_audio_event(
                        "Falling back to pynput hotkey manager",
                        {"original_backend": actual_backend},
                    )
                    return PynputHotkeyManager(callback)
                except ImportError:
                    pass

        raise HotkeyBackendError(error_msg)

    except Exception as e:
        error_msg = f"Failed to create {actual_backend} hotkey manager: {str(e)}"
        app_logger.log_error(e, "create_hotkey_manager")
        raise HotkeyBackendError(error_msg)


# Re-export for backward compatibility
from .hotkey_manager_pynput import PynputHotkeyManager as HotkeyManager  # noqa: E402

__all__ = [
    "create_hotkey_manager",
    "HotkeyBackendError",
    "HotkeyManager",  # For backward compatibility
]
