"""Win32 RegisterHotKey implementation - no admin privileges required

This implementation uses Windows RegisterHotKey API instead of low-level keyboard hooks.

Advantages:
- No administrator privileges required
- Works across privilege boundaries (not blocked by UIPI)
- Better performance (no hook overhead)
- Official Windows API for global hotkeys

Trade-offs:
- Cannot suppress hotkey events (they still reach active window)
- Can conflict with other applications' hotkeys
"""

import queue
import threading
from typing import Callable, Dict, List, Optional

import win32con

from ..utils import HotkeyRegistrationError, app_logger
from .base.lifecycle_component import LifecycleComponent
from .interfaces import IHotkeyService


class HotkeyConflictError(Exception):
    """Hotkey already registered by another application"""

    def __init__(self, hotkey: str, error_code: int = None):
        self.hotkey = hotkey
        self.error_code = error_code

        message = f"Hotkey '{hotkey}' is already in use by another application"
        if error_code:
            message += f" (error code: {error_code})"

        super().__init__(message)

        # Suggest alternative hotkeys
        self.suggestions = self._generate_suggestions(hotkey)

    @staticmethod
    def _generate_suggestions(conflicting_hotkey: str) -> list:
        """Generate alternative hotkey suggestions

        Args:
            conflicting_hotkey: The hotkey that conflicts

        Returns:
            List of suggested alternative hotkeys
        """
        # Common alternative hotkeys that are less likely to conflict
        common_alternatives = [
            "alt+h",
            "ctrl+shift+v",
            "ctrl+alt+v",
            "f11",
            "f10",
            "alt+shift+v",
            "ctrl+shift+h",
        ]

        # Filter out the conflicting one
        normalized = conflicting_hotkey.lower().strip()
        suggestions = [h for h in common_alternatives if h != normalized]

        # Limit to top 3
        return suggestions[:3]


class Win32HotkeyManager(LifecycleComponent, IHotkeyService):
    """Windows RegisterHotKey based hotkey manager

    Uses Windows RegisterHotKey API for global hotkey detection.
    Does not require administrator privileges.
    """

    # Modifier key mapping
    MOD_ALT = win32con.MOD_ALT
    MOD_CONTROL = win32con.MOD_CONTROL
    MOD_SHIFT = win32con.MOD_SHIFT
    MOD_WIN = win32con.MOD_WIN

    # Virtual key code mapping
    VK_MAP = {
        "f1": win32con.VK_F1,
        "f2": win32con.VK_F2,
        "f3": win32con.VK_F3,
        "f4": win32con.VK_F4,
        "f5": win32con.VK_F5,
        "f6": win32con.VK_F6,
        "f7": win32con.VK_F7,
        "f8": win32con.VK_F8,
        "f9": win32con.VK_F9,
        "f10": win32con.VK_F10,
        "f11": win32con.VK_F11,
        "f12": win32con.VK_F12,
        "a": ord("A"),
        "b": ord("B"),
        "c": ord("C"),
        "d": ord("D"),
        "e": ord("E"),
        "f": ord("F"),
        "g": ord("G"),
        "h": ord("H"),
        "i": ord("I"),
        "j": ord("J"),
        "k": ord("K"),
        "l": ord("L"),
        "m": ord("M"),
        "n": ord("N"),
        "o": ord("O"),
        "p": ord("P"),
        "q": ord("Q"),
        "r": ord("R"),
        "s": ord("S"),
        "t": ord("T"),
        "u": ord("U"),
        "v": ord("V"),
        "w": ord("W"),
        "x": ord("X"),
        "y": ord("Y"),
        "z": ord("Z"),
        "0": ord("0"),
        "1": ord("1"),
        "2": ord("2"),
        "3": ord("3"),
        "4": ord("4"),
        "5": ord("5"),
        "6": ord("6"),
        "7": ord("7"),
        "8": ord("8"),
        "9": ord("9"),
        "space": win32con.VK_SPACE,
        "enter": win32con.VK_RETURN,
        "esc": win32con.VK_ESCAPE,
        "tab": win32con.VK_TAB,
        "backspace": win32con.VK_BACK,
        "delete": win32con.VK_DELETE,
        "insert": win32con.VK_INSERT,
        "home": win32con.VK_HOME,
        "end": win32con.VK_END,
        "pageup": win32con.VK_PRIOR,
        "pagedown": win32con.VK_NEXT,
        "up": win32con.VK_UP,
        "down": win32con.VK_DOWN,
        "left": win32con.VK_LEFT,
        "right": win32con.VK_RIGHT,
    }

    def __init__(self, callback: Callable[[str], None]):
        """Initialize Win32 hotkey manager

        Args:
            callback: Callback function called when hotkey is triggered
        """
        super().__init__("Win32HotkeyManager")
        self.callback = callback
        self._default_action = "toggle_recording"  # 保存默认动作
        self.registered_hotkeys: Dict[
            str, Dict
        ] = {}  # hotkey_str -> {id, action, modifiers, vk}
        self._is_listening_flag = False
        self._message_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._next_hotkey_id = 1
        self._command_queue = queue.Queue()

        app_logger.log_audio_event(
            "Win32 hotkey manager initialized (RegisterHotKey)", {}
        )

    def _do_start(self) -> bool:
        """Start Win32 hotkey listening (LifecycleComponent API)

        Returns:
            True if start successful
        """
        return self.start_listening()

    def _do_stop(self) -> bool:
        """Stop Win32 hotkey listening and cleanup (LifecycleComponent API)

        Returns:
            True if stop successful
        """
        self.stop_listening()
        return True

    @property
    def is_listening(self) -> bool:
        """Whether hotkey listening is active"""
        return self._is_listening_flag

    def _parse_hotkey(self, hotkey_str: str) -> tuple[int, int]:
        """Parse hotkey string to modifiers and virtual key code

        Args:
            hotkey_str: Hotkey string like "ctrl+shift+v" or "f12"

        Returns:
            (modifiers, virtual_key) tuple

        Raises:
            HotkeyRegistrationError: Invalid hotkey format
        """
        parts = [part.strip().lower() for part in hotkey_str.split("+")]

        modifiers = 0
        vk = 0

        for part in parts:
            if part in ("ctrl", "control"):
                modifiers |= self.MOD_CONTROL
            elif part in ("alt", "menu"):
                modifiers |= self.MOD_ALT
            elif part == "shift":
                modifiers |= self.MOD_SHIFT
            elif part in ("win", "windows", "super"):
                modifiers |= self.MOD_WIN
            elif part in self.VK_MAP:
                if vk != 0:
                    raise HotkeyRegistrationError(
                        f"Invalid hotkey '{hotkey_str}': multiple keys specified"
                    )
                vk = self.VK_MAP[part]
            else:
                raise HotkeyRegistrationError(
                    f"Invalid hotkey '{hotkey_str}': unknown key '{part}'"
                )

        if vk == 0:
            raise HotkeyRegistrationError(
                f"Invalid hotkey '{hotkey_str}': no key specified"
            )

        return modifiers, vk

    def _normalize_hotkey(self, hotkey_str: str) -> str:
        """Normalize hotkey string format

        Args:
            hotkey_str: Raw hotkey string

        Returns:
            Normalized hotkey string
        """
        parts = [part.strip().lower() for part in hotkey_str.split("+")]

        # Order: ctrl, alt, shift, win, key
        modifiers = []
        key = None

        for part in parts:
            if part in ("ctrl", "control"):
                if "ctrl" not in modifiers:
                    modifiers.append("ctrl")
            elif part in ("alt", "menu"):
                if "alt" not in modifiers:
                    modifiers.append("alt")
            elif part == "shift":
                if "shift" not in modifiers:
                    modifiers.append("shift")
            elif part in ("win", "windows", "super"):
                if "win" not in modifiers:
                    modifiers.append("win")
            else:
                key = part

        # Build normalized string
        result = "+".join(modifiers)
        if key:
            if result:
                result += "+" + key
            else:
                result = key

        return result

    def _execute_callback(self, action: str) -> None:
        """Execute hotkey callback

        Args:
            action: Action name to pass to callback
        """
        try:
            if self.callback:
                self.callback(action)
                app_logger.log_audio_event(
                    "Win32 hotkey callback completed", {"action": action}
                )
        except Exception as e:
            app_logger.log_error(e, f"win32_hotkey_callback_{action}")

    def _message_loop(self) -> None:
        """Message loop thread for receiving WM_HOTKEY messages

        Uses thread-level hotkeys (NULL window handle) instead of window-based hotkeys.
        This avoids thread affinity issues with RegisterHotKey.
        """
        try:
            # Signal that message loop is ready
            # We don't create a window - RegisterHotKey with NULL binds to the thread
            self._is_listening_flag = True

            app_logger.log_audio_event(
                "Win32 message loop started (thread-level hotkeys)", {}
            )

            # Process queued registration commands
            while not self._command_queue.empty():
                try:
                    cmd = self._command_queue.get_nowait()
                    cmd()
                except queue.Empty:
                    break
                except Exception as e:
                    # Log errors from command execution but continue processing
                    app_logger.log_error(e, "command_queue_execution")
                    # Don't break - continue processing other commands

            # Message loop - process thread messages
            import ctypes

            msg = ctypes.wintypes.MSG()

            while not self._stop_event.is_set():
                try:
                    # GetMessage returns:
                    # > 0: message retrieved (not WM_QUIT)
                    # 0: WM_QUIT received
                    # -1: error
                    result = ctypes.windll.user32.GetMessageW(
                        ctypes.byref(msg),
                        None,  # NULL window handle - get thread messages
                        0,  # min message filter
                        0,  # max message filter
                    )

                    if result == 0:  # WM_QUIT
                        break
                    elif result < 0:  # Error
                        app_logger.log_error(
                            Exception("GetMessage failed"), "win32_message_loop"
                        )
                        break

                    # Handle WM_HOTKEY messages
                    if msg.message == win32con.WM_HOTKEY:
                        hotkey_id = msg.wParam

                        # Find hotkey by ID
                        for hotkey_str, info in self.registered_hotkeys.items():
                            if info["id"] == hotkey_id:
                                action = info["action"]

                                app_logger.log_audio_event(
                                    "Win32 hotkey triggered",
                                    {
                                        "hotkey": hotkey_str,
                                        "action": action,
                                        "id": hotkey_id,
                                    },
                                )

                                app_logger.log_hotkey_event(hotkey_str, action)

                                # Execute callback in separate thread to avoid blocking message loop
                                threading.Thread(
                                    target=self._execute_callback,
                                    args=(action,),
                                    daemon=True,
                                ).start()

                                break

                    # Process queued commands (for register/unregister hotkeys)
                    while not self._command_queue.empty():
                        try:
                            cmd = self._command_queue.get_nowait()
                            cmd()
                        except queue.Empty:
                            break

                    # Process other messages
                    ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                    ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

                except Exception as e:
                    if not self._stop_event.is_set():
                        app_logger.log_error(e, "win32_message_loop")
                    break

        except Exception as e:
            app_logger.log_error(e, "win32_message_loop_init")
        finally:
            self._is_listening_flag = False

    def register_hotkey(self, hotkey: str, action: str = "toggle_recording") -> bool:
        """Register global hotkey using RegisterHotKey API

        Args:
            hotkey: Hotkey string (e.g., "ctrl+shift+v", "f12")
            action: Action name to pass to callback

        Returns:
            True if registration successful

        Raises:
            HotkeyRegistrationError: Invalid hotkey format
            HotkeyConflictError: Hotkey already in use by another application
        """
        if not hotkey:
            raise HotkeyRegistrationError("Hotkey string cannot be empty")

        # Normalize hotkey string
        normalized_hotkey = self._normalize_hotkey(hotkey)

        # Unregister if already exists
        if normalized_hotkey in self.registered_hotkeys:
            self.unregister_hotkey(normalized_hotkey)

        try:
            # Parse hotkey
            modifiers, vk = self._parse_hotkey(normalized_hotkey)

            # Assign ID
            hotkey_id = self._next_hotkey_id
            self._next_hotkey_id += 1

            # Variables to capture result/error from register_command
            registration_error = None
            registration_complete = threading.Event()

            # Register hotkey (must be done in message loop thread)
            def register_command():
                nonlocal registration_error
                try:
                    import ctypes

                    # Use NULL window handle - binds hotkey to the thread
                    success = ctypes.windll.user32.RegisterHotKey(
                        None,  # NULL window handle - bind to thread
                        hotkey_id,
                        modifiers,
                        vk,
                    )

                    error_code = (
                        ctypes.windll.kernel32.GetLastError() if not success else 0
                    )

                    # Log RegisterHotKey result
                    app_logger.log_audio_event(
                        "RegisterHotKey called",
                        {
                            "hotkey": normalized_hotkey,
                            "id": hotkey_id,
                            "modifiers": modifiers,
                            "vk": vk,
                            "success": bool(success),
                            "error_code": error_code,
                        },
                    )

                    if not success:
                        # Create conflict error with detailed info
                        registration_error = HotkeyConflictError(
                            normalized_hotkey, error_code
                        )

                        # Check if running as admin
                        import ctypes

                        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

                        # Log conflict details
                        app_logger.log_audio_event(
                            "Win32 hotkey conflict detected",
                            {
                                "hotkey": normalized_hotkey,
                                "error_code": error_code,
                                "error_message": "Hotkey already registered by another application",
                                "suggestions": registration_error.suggestions,
                                "running_as_admin": is_admin,
                                "note": "If error_code is 1409 and running_as_admin is False, the conflicting app may be running with admin privileges. Try running SonicInput as administrator.",
                            },
                        )
                        return

                    # Store registration info
                    self.registered_hotkeys[normalized_hotkey] = {
                        "id": hotkey_id,
                        "action": action,
                        "modifiers": modifiers,
                        "vk": vk,
                    }

                    app_logger.log_audio_event(
                        "Win32 hotkey registered",
                        {
                            "hotkey": normalized_hotkey,
                            "action": action,
                            "id": hotkey_id,
                            "modifiers": modifiers,
                            "vk": vk,
                        },
                    )

                except Exception as e:
                    app_logger.log_error(e, "register_hotkey_win32")
                    registration_error = e
                finally:
                    registration_complete.set()

            # Always queue command to ensure it runs in message loop thread
            self._command_queue.put(register_command)

            # If message loop is running, wake it up
            if self._is_listening_flag and self._message_thread:
                import ctypes

                # On Windows, thread.ident is the native thread ID
                # No need to call GetThreadId (which requires a HANDLE, not an ID)
                thread_id = self._message_thread.ident
                # Post a dummy message to wake up GetMessage
                ctypes.windll.user32.PostThreadMessageW(
                    thread_id, win32con.WM_NULL, 0, 0
                )

            # Wait for completion (with timeout)
            if registration_complete.wait(timeout=2.0):
                if registration_error:
                    raise registration_error

                # Verify hotkey is actually registered
                if normalized_hotkey not in self.registered_hotkeys:
                    raise HotkeyRegistrationError(
                        f"Hotkey '{normalized_hotkey}' registration failed silently"
                    )
            else:
                # Timeout - registration failed because message loop wasn't ready
                error_msg = (
                    f"Hotkey '{normalized_hotkey}' registration timed out - "
                    "message loop not ready"
                )
                app_logger.log_error(
                    Exception(error_msg),
                    "register_hotkey_timeout",
                )
                raise HotkeyRegistrationError(error_msg)

            return True

        except Exception as e:
            app_logger.log_error(e, f"register_hotkey_{normalized_hotkey}")
            raise

    def unregister_hotkey(self, hotkey: str) -> bool:
        """Unregister hotkey

        Args:
            hotkey: Hotkey string

        Returns:
            True if unregistration successful
        """
        normalized_hotkey = self._normalize_hotkey(hotkey)

        if normalized_hotkey not in self.registered_hotkeys:
            return False

        info = self.registered_hotkeys[normalized_hotkey]
        hotkey_id = info["id"]

        try:
            import ctypes

            # Use NULL window handle (thread-level hotkey)
            ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)

            del self.registered_hotkeys[normalized_hotkey]

            app_logger.log_audio_event(
                "Win32 hotkey unregistered",
                {"hotkey": normalized_hotkey, "id": hotkey_id},
            )

            return True

        except Exception as e:
            app_logger.log_error(e, f"unregister_hotkey_{normalized_hotkey}")
            return False

    def unregister_all_hotkeys(self) -> None:
        """Unregister all hotkeys"""
        hotkeys = list(self.registered_hotkeys.keys())
        for hotkey in hotkeys:
            self.unregister_hotkey(hotkey)

    def start_listening(self) -> bool:
        """Start hotkey listening

        Creates message window and starts message loop thread

        Returns:
            True if listening started successfully
        """
        if self._is_listening_flag:
            app_logger.log_audio_event("Win32 hotkey already listening", {})
            return True

        try:
            self._stop_event.clear()

            # Start message loop thread
            self._message_thread = threading.Thread(
                target=self._message_loop, daemon=True, name="Win32HotkeyMessageLoop"
            )
            self._message_thread.start()

            # Wait for window creation
            import time

            for _ in range(50):  # Wait up to 5 seconds
                if self._is_listening_flag:
                    break
                time.sleep(0.1)

            if not self._is_listening_flag:
                raise RuntimeError("Failed to start message loop")

            app_logger.log_audio_event("Win32 hotkey listening started", {})
            return True

        except Exception as e:
            app_logger.log_error(e, "start_listening_win32")
            return False

    def stop_listening(self) -> None:
        """Stop hotkey listening"""
        if not self._is_listening_flag:
            return

        try:
            # Unregister all hotkeys
            self.unregister_all_hotkeys()

            # Signal stop
            self._stop_event.set()

            # Post quit message to message loop thread
            if self._message_thread and self._message_thread.is_alive():
                import ctypes

                try:
                    thread_id = ctypes.windll.kernel32.GetThreadId(
                        self._message_thread.native_id
                        if hasattr(self._message_thread, "native_id")
                        else self._message_thread.ident
                    )
                    # Post WM_QUIT to the thread
                    ctypes.windll.user32.PostThreadMessageW(
                        thread_id, win32con.WM_QUIT, 0, 0
                    )
                except Exception as e:
                    app_logger.log_error(
                        e,
                        "hotkey_listener_cleanup",
                        {"context": "Failed to post WM_QUIT to hotkey listener thread"},
                    )

            # Wait for thread
            if self._message_thread and self._message_thread.is_alive():
                self._message_thread.join(timeout=2.0)

            self._is_listening_flag = False
            self._message_thread = None

            app_logger.log_audio_event("Win32 hotkey listening stopped", {})

        except Exception as e:
            app_logger.log_error(e, "stop_listening_win32")

    def get_registered_hotkeys(self) -> Dict[str, str]:
        """Get registered hotkeys

        Returns:
            Dict mapping hotkey string to action name
        """
        return {
            hotkey: info["action"] for hotkey, info in self.registered_hotkeys.items()
        }

    def reload(self, new_keys: List[str]) -> None:
        """重新加载热键配置

        Args:
            new_keys: 新的热键列表（如 ["f12", "alt+h"]）
        """
        app_logger.log_audio_event(
            "Reloading Win32 hotkeys",
            {"old_keys": list(self.registered_hotkeys.keys()), "new_keys": new_keys},
        )

        # 1. 注销所有旧热键
        self.unregister_all_hotkeys()

        # 2. 注册新热键
        for key_combo in new_keys:
            try:
                # 使用默认动作（通常是 toggle_recording）
                self.register_hotkey(key_combo, self._default_action)
            except Exception as e:
                app_logger.log_error(
                    e, f"Win32HotkeyManager.reload: Failed to register {key_combo}"
                )

        app_logger.log_audio_event(
            "Win32 hotkeys reloaded",
            {"active_keys": list(self.registered_hotkeys.keys())},
        )
