"""Windows SendInput文本输入方法 - Refactored with ctypes"""

import ctypes
from ctypes import wintypes

import win32gui

from ..utils import TextInputError, app_logger

# Define constants from Windows API
INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
VK_BACK = 0x08

# Define structures for SendInput
wintypes.ULONG_PTR = wintypes.WPARAM


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUT_UNION(ctypes.Union):
    _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", _INPUT_UNION))


class SendInputMethod:
    """使用Windows SendInput API的文本输入方法 (ctypes version)"""

    def __init__(self):
        self.max_length = 4096  # Increased max length
        app_logger.log_audio_event("SendInput method (ctypes) initialized", {})

    @staticmethod
    def _build_virtual_key_inputs(virtual_key: int) -> tuple[INPUT, INPUT]:
        keydown = INPUT(
            type=INPUT_KEYBOARD,
            union=_INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=virtual_key,
                    wScan=0,
                    dwFlags=0,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        keyup = INPUT(
            type=INPUT_KEYBOARD,
            union=_INPUT_UNION(
                ki=KEYBDINPUT(
                    wVk=virtual_key,
                    wScan=0,
                    dwFlags=KEYEVENTF_KEYUP,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        return keydown, keyup

    def input_via_sendinput(self, text: str) -> bool:
        """使用 modern SendInput API 输入文本 (优化版)"""
        if not text:
            return True

        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                app_logger.log_warning(
                    "No foreground window found, but attempting SendInput anyway."
                )

            if len(text) > self.max_length:
                original_len = len(text)
                text = text[: self.max_length]
                app_logger.log_audio_event(
                    "Text truncated for SendInput",
                    {
                        "original_length": original_len,
                        "truncated_length": self.max_length,
                    },
                )

            send_units = []
            index = 0
            while index < len(text):
                char = text[index]
                code_point = ord(char)
                if char == "\b":
                    send_units.append(("vk", VK_BACK))
                    index += 1
                    continue
                if 0xD800 <= code_point <= 0xDBFF:
                    if index + 1 < len(text):
                        next_code = ord(text[index + 1])
                        if 0xDC00 <= next_code <= 0xDFFF:
                            index += 2
                            continue
                    index += 1
                    continue
                if 0xDC00 <= code_point <= 0xDFFF:
                    index += 1
                    continue
                send_units.append(("unicode", char))
                index += 1

            num_events = len(send_units) * 2
            if num_events == 0:
                return True

            input_array = (INPUT * num_events)()
            event_index = 0

            for unit_type, unit_value in send_units:
                if unit_type == "vk":
                    keydown_input, keyup_input = self._build_virtual_key_inputs(
                        unit_value
                    )
                    input_array[event_index] = keydown_input
                    input_array[event_index + 1] = keyup_input
                    event_index += 2
                    continue

                char_code = ord(unit_value)

                # Key down event
                keydown_input = input_array[event_index]
                keydown_input.type = INPUT_KEYBOARD
                keydown_input.union.ki = KEYBDINPUT(
                    wVk=0,
                    wScan=char_code,
                    dwFlags=KEYEVENTF_UNICODE,
                    time=0,
                    dwExtraInfo=0,
                )

                # Key up event
                keyup_input = input_array[event_index + 1]
                keyup_input.type = INPUT_KEYBOARD
                keyup_input.union.ki = KEYBDINPUT(
                    wVk=0,
                    wScan=char_code,
                    dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                    time=0,
                    dwExtraInfo=0,
                )
                event_index += 2
            n_sent = ctypes.windll.user32.SendInput(
                num_events, ctypes.byref(input_array), ctypes.sizeof(INPUT)
            )

            if n_sent != num_events:
                raise TextInputError(
                    f"SendInput failed: only {n_sent}/{num_events} events were sent."
                )

            app_logger.log_audio_event(
                "Text input via SendInput (ctypes) successful",
                {
                    "text_length": len(text),
                    "sent_length": len(send_units),
                    "events_count": num_events,
                },
            )
            return True

        except Exception as e:
            app_logger.log_error(e, "input_via_sendinput_ctypes")
            if not isinstance(e, TextInputError):
                # Wrap the original exception
                raise TextInputError(
                    f"An unexpected error occurred during SendInput: {e}"
                ) from e
            return False

    def test_sendinput_capability(self) -> bool:
        """Tests the modern SendInput functionality."""
        try:
            # Send a space and then a backspace to test.
            self.input_via_sendinput(" ")

            keydown, keyup = self._build_virtual_key_inputs(VK_BACK)
            input_array = (INPUT * 2)(keydown, keyup)
            ctypes.windll.user32.SendInput(
                2, ctypes.byref(input_array), ctypes.sizeof(INPUT)
            )

            app_logger.log_audio_event(
                "SendInput capability test (ctypes) successful.", {}
            )
            return True
        except Exception as e:
            app_logger.log_error(e, "test_sendinput_capability_ctypes")
            return False

    def set_typing_delay(self, delay: float) -> None:
        """设置字符间延迟 (Note: not used in this implementation)"""
        # This method is kept for API compatibility but does nothing in this implementation.
        if delay > 0:
            app_logger.log_warning(
                "typing_delay is set but not used by the modern SendInput implementation."
            )

    def get_foreground_window_info(self) -> dict:
        """获取前台窗口信息"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                window_text = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)
                return {
                    "hwnd": hwnd,
                    "title": window_text,
                    "class_name": class_name,
                    "has_focus": True,
                }
            else:
                return {"hwnd": 0, "has_focus": False}
        except Exception as e:
            app_logger.log_error(e, "get_foreground_window_info")
            return {"hwnd": 0, "has_focus": False}

    def _is_surrogate_pair(self, char: str, index: int, text: str) -> bool:
        """检查字符是否是代理对的一部分（用于emoji等Unicode字符）"""
        try:
            # 检查是否是高代理项
            if 0xD800 <= ord(char) <= 0xDBFF:
                # 检查是否有对应的低代理项
                if index + 1 < len(text):
                    next_char = text[index + 1]
                    return 0xDC00 <= ord(next_char) <= 0xDFFF
            return False
        except Exception as e:
            app_logger.log_error(
                e,
                "surrogate_pair_check_failed",
                {
                    "context": "Failed to check Unicode surrogate pair",
                    "char": repr(char),
                    "index": index,
                },
            )
            return False
