"""剪贴板输入方法"""

import ctypes
import time
from typing import Any, Dict, Optional, Tuple, Union

import pyperclip
import win32api
import win32clipboard
import win32con
import win32gui

from ..utils import TextInputError, app_logger


class ClipboardInput:
    """基于剪贴板的文本输入

    架构说明：
    - 支持全格式备份/恢复（文本、图片、富文本等）
    - 自动跳过 GDI 句柄格式（CF_BITMAP 等），让 Windows 从实际数据自动合成
    - 录音模式下禁用中途备份/恢复，避免覆盖外层保存的原始剪贴板
    - 使用重试机制（10 次 × 50ms）处理剪贴板竞争
    """

    # Windows GDI 句柄格式（无法跨进程/时间恢复）
    HANDLE_FORMATS = {
        2: "CF_BITMAP",  # HBITMAP - GDI 位图句柄
        3: "CF_METAFILEPICT",  # HGLOBAL (metafile) - 图元文件句柄
        9: "CF_PALETTE",  # HPALETTE - 调色板句柄
        14: "CF_ENHMETAFILE",  # HENHMETAFILE - 增强型图元文件句柄
    }
    REGISTERED_FORMAT_START = 0xC000

    # 标准格式名（用于日志）
    STANDARD_FORMAT_NAMES = {
        1: "CF_TEXT",
        2: "CF_BITMAP",
        3: "CF_METAFILEPICT",
        7: "CF_OEMTEXT",
        8: "CF_DIB",
        9: "CF_PALETTE",
        13: "CF_UNICODETEXT",
        14: "CF_ENHMETAFILE",
        16: "CF_LOCALE",
        17: "CF_DIBV5",
    }

    # 仅恢复这些标准格式（文本 + 主要图像格式）
    SAFE_STANDARD_RESTORE_FORMATS = {1, 7, 8, 13, 16, 17}

    # 注册格式白名单（保留常见富文本/网页/图像格式）
    SAFE_REGISTERED_FORMAT_NAMES = {
        "html format",
        "rich text format",
        "rtf",
        "png",
        "jfif",
        "gif",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/bmp",
        "bitmap",
    }
    SAFE_REGISTERED_FORMAT_KEYWORDS = (
        "html",
        "rtf",
        "rich text",
        "image",
        "png",
        "jpeg",
        "jpg",
        "gif",
        "bitmap",
        "dib",
    )
    MAX_RESTORABLE_FORMAT_SIZE_BYTES = 32 * 1024 * 1024  # 32MB

    def __init__(self):
        self.original_clipboard = ""
        self.restore_delay = 0.1  # 恢复剪贴板内容的延迟
        self._recording_mode = False  # 录音模式标志（禁用中途restore）

        app_logger.log_audio_event("Clipboard input initialized", {})

    def _open_clipboard_with_retry(
        self, hwnd=None, max_attempts=10, delay=0.05
    ) -> bool:
        """使用重试逻辑打开剪贴板

        Args:
            hwnd: 窗口句柄（None表示使用桌面窗口）
            max_attempts: 最大重试次数
            delay: 重试延迟（秒）

        Returns:
            是否成功打开剪贴板
        """
        for attempt in range(max_attempts):
            try:
                win32clipboard.OpenClipboard(hwnd)
                return True
            except Exception as e:
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                else:
                    app_logger.log_audio_event(
                        "Failed to open clipboard after retries",
                        {"attempts": attempt + 1, "hwnd": hwnd, "error": str(e)},
                    )
                    app_logger.log_error(e, "_open_clipboard_with_retry")
                    return False
        return False

    def _backup_all_formats(self) -> Dict[int, bytes]:
        """备份所有格式的剪贴板数据（使用 win32clipboard API）

        Returns:
            字典，键为格式ID，值为该格式的数据（bytes）
        """
        formats = {}

        # 特殊格式：无法备份/恢复
        SKIP_FORMATS = {
            0x0080,  # CF_OWNERDISPLAY
            0x0082,  # CF_DSPTEXT
            0x0083,  # CF_DSPBITMAP
            0x008E,  # CF_DSPMETAFILEPICT
            0x0084,  # CF_DSPENHMETAFILE
        }

        # 合成的文本格式（如果有Unicode，这些会自动生成）
        SYNTHESIZED_TEXT = {1, 7}  # CF_TEXT, CF_OEMTEXT

        try:
            # 使用重试逻辑打开剪贴板
            if not self._open_clipboard_with_retry():
                app_logger.log_audio_event("Failed to open clipboard for backup", {})
                return formats

            try:
                fmt = 0
                format_count = 0
                has_unicode_text = False

                # 第一遍：检查是否有Unicode文本
                temp_fmt = 0
                while True:
                    temp_fmt = win32clipboard.EnumClipboardFormats(temp_fmt)
                    if temp_fmt == 0:
                        break
                    if temp_fmt == 13:  # CF_UNICODETEXT
                        has_unicode_text = True
                        break

                # 第二遍：备份格式
                while True:
                    fmt = win32clipboard.EnumClipboardFormats(fmt)
                    if fmt == 0:
                        break

                    # 跳过特殊格式
                    if fmt in SKIP_FORMATS:
                        app_logger.log_audio_event(
                            "Skipping special format",
                            {"format": fmt, "reason": "cannot_restore"},
                        )
                        continue

                    # 跳过合成文本格式（如果有Unicode）
                    if has_unicode_text and fmt in SYNTHESIZED_TEXT:
                        app_logger.log_audio_event(
                            "Skipping synthesized text format",
                            {"format": fmt, "reason": "will_auto_synthesize"},
                        )
                        continue

                    try:
                        data = win32clipboard.GetClipboardData(fmt)
                        if data is not None:  # 跳过延迟渲染格式
                            # 关键修复：跳过 GDI 句柄类型，因为句柄无法跨进程/时间恢复
                            # Windows 会从实际数据（如 CF_DIB）自动合成句柄格式（如 CF_BITMAP）
                            if fmt in self.HANDLE_FORMATS or isinstance(data, int):
                                format_name = self.HANDLE_FORMATS.get(
                                    fmt, f"Unknown({fmt})"
                                )
                                app_logger.log_audio_event(
                                    f"Skipping handle-type format: {format_name}",
                                    {
                                        "format": fmt,
                                        "reason": "handle_type",
                                        "handle_value": data
                                        if isinstance(data, int)
                                        else "N/A",
                                    },
                                )
                                continue

                            formats[fmt] = data
                            format_count += 1
                        else:
                            app_logger.log_audio_event(
                                "Skipping delayed-rendered format", {"format": fmt}
                            )
                    except Exception as e:
                        # 某些格式可能无法读取，记录警告但继续
                        app_logger.log_audio_event(
                            f"Failed to backup clipboard format {fmt}",
                            {"error": str(e), "result": "backup_exception"},
                        )

                app_logger.log_audio_event(
                    "All clipboard formats backed up",
                    {
                        "format_count": format_count,
                        "formats": list(formats.keys()),
                        "has_unicode": has_unicode_text,
                    },
                )

            finally:
                win32clipboard.CloseClipboard()

        except Exception as e:
            app_logger.log_error(e, "_backup_all_formats")

        return formats

    def _get_clipboard_format_name(self, fmt: int) -> str:
        """获取剪贴板格式名称（标准格式或注册格式）。"""
        standard_name = self.STANDARD_FORMAT_NAMES.get(fmt)
        if standard_name:
            return standard_name

        if fmt >= self.REGISTERED_FORMAT_START:
            try:
                name = win32clipboard.GetClipboardFormatName(fmt)
                if name:
                    return name
            except Exception:
                pass
            return f"Registered({fmt})"

        return f"Format({fmt})"

    def _is_allowed_registered_format(self, format_name: str) -> bool:
        """判断注册格式是否在可安全恢复集合中。"""
        normalized = format_name.strip().lower()
        if normalized in self.SAFE_REGISTERED_FORMAT_NAMES:
            return True
        return any(
            keyword in normalized for keyword in self.SAFE_REGISTERED_FORMAT_KEYWORDS
        )

    def _can_restore_format(self, fmt: int, data: Any) -> Tuple[bool, str]:
        """判断格式是否可安全恢复，避免触发 Win32 堆损坏。"""
        if data is None:
            return False, "data_none"

        # 明确排除 GDI 句柄类格式和句柄值
        if fmt in self.HANDLE_FORMATS:
            return False, "handle_format"
        if isinstance(data, int):
            return False, "handle_value"

        # 标准格式：仅允许安全子集
        if fmt < self.REGISTERED_FORMAT_START:
            if fmt not in self.SAFE_STANDARD_RESTORE_FORMATS:
                return False, "standard_not_allowlisted"

            if fmt == 13 and not isinstance(data, str):  # CF_UNICODETEXT
                return False, f"unicode_requires_str:{type(data).__name__}"
            if fmt in {1, 7} and not isinstance(
                data, (bytes, str)
            ):  # CF_TEXT/CF_OEMTEXT
                return False, f"text_requires_bytes_or_str:{type(data).__name__}"
            if fmt in {8, 17} and not isinstance(data, (bytes, bytearray)):  # DIB/DIBV5
                return False, f"dib_requires_bytes:{type(data).__name__}"
            if fmt == 16 and not isinstance(data, (bytes, bytearray)):  # CF_LOCALE
                return False, f"locale_requires_bytes:{type(data).__name__}"

            if isinstance(data, (bytes, bytearray)) and len(data) == 0:
                return False, "empty_binary_data"
            return True, "safe_standard"

        # 注册格式：仅放行白名单格式名，且必须是 bytes-like
        if not isinstance(data, (bytes, bytearray)):
            return False, f"registered_requires_bytes:{type(data).__name__}"

        data_size = len(data)
        if data_size == 0:
            return False, "registered_empty_data"
        if data_size > self.MAX_RESTORABLE_FORMAT_SIZE_BYTES:
            return False, f"registered_too_large:{data_size}"

        format_name = self._get_clipboard_format_name(fmt)
        if not self._is_allowed_registered_format(format_name):
            return False, f"registered_not_allowlisted:{format_name}"

        return True, f"safe_registered:{format_name}"

    def backup_clipboard(self) -> Union[str, Dict[int, bytes]]:
        """备份当前剪贴板内容 - 支持所有格式

        Returns:
            如果只有文本，返回字符串；否则返回字典（格式ID -> 数据）
        """
        try:
            # 使用 win32clipboard 备份所有格式
            all_formats = self._backup_all_formats()

            if not all_formats:
                # 剪贴板为空
                app_logger.log_audio_event(
                    "Clipboard is empty", {"elevated": self._is_elevated()}
                )
                self.original_clipboard = ""
                return ""

            # 保存完整格式数据
            self.original_clipboard = all_formats

            # 尝试获取文本内容用于日志
            text_content = ""
            try:
                text_content = pyperclip.paste()
            except Exception:
                pass

            app_logger.log_audio_event(
                "Clipboard backed up (all formats)",
                {
                    "format_count": len(all_formats),
                    "has_text": bool(text_content),
                    "text_length": len(text_content) if text_content else 0,
                    "elevated": self._is_elevated(),
                },
            )

            return all_formats

        except Exception as e:
            app_logger.log_error(e, "backup_clipboard")
            self.original_clipboard = ""
            return ""

    def _sort_formats_by_dependency(
        self, formats: Dict[int, bytes]
    ) -> Dict[int, bytes]:
        """按格式依赖关系排序

        某些格式有依赖关系，需要按正确顺序恢复：
        - CF_DIB (8) 应该在 CF_BITMAP (2) 之前
        - CF_UNICODETEXT (13) 应该在 CF_TEXT (1) 之前
        - 图像格式应该在文本格式之前

        Args:
            formats: 未排序的格式字典

        Returns:
            按依赖关系排序后的格式字典
        """
        # 定义格式优先级（数字越小优先级越高）
        FORMAT_PRIORITY = {
            8: 1,  # CF_DIB - 设备无关位图（最高优先级）
            17: 2,  # CF_DIBV5 - DIB v5
            2: 3,  # CF_BITMAP - 位图
            13: 4,  # CF_UNICODETEXT - Unicode文本
            16: 5,  # CF_LOCALE - 区域设置
            1: 6,  # CF_TEXT - ANSI文本
            7: 7,  # CF_OEMTEXT - OEM文本
        }

        def get_priority(fmt: int) -> int:
            """获取格式优先级，未知格式放在中间"""
            return FORMAT_PRIORITY.get(fmt, 50)

        # 按优先级排序
        sorted_items = sorted(formats.items(), key=lambda x: get_priority(x[0]))
        sorted_formats = dict(sorted_items)

        app_logger.log_audio_event(
            "Formats sorted by dependency",
            {
                "original_order": list(formats.keys()),
                "sorted_order": list(sorted_formats.keys()),
            },
        )

        return sorted_formats

    def _validate_format_restored(self, fmt: int, original_data: bytes) -> bool:
        """验证格式是否真正恢复到剪贴板

        通过读回格式数据并与原始数据对比来验证

        Args:
            fmt: 格式ID
            original_data: 原始数据

        Returns:
            是否成功恢复
        """
        try:
            # 读回刚才设置的格式
            restored_data = win32clipboard.GetClipboardData(fmt)

            # 对于某些格式，数据可能会被 Windows 修改（如添加 padding）
            # 所以我们只检查数据是否存在且大小相近
            if restored_data is None:
                app_logger.log_audio_event(
                    f"Format {fmt} validation failed: data is None",
                    {"format": fmt, "validation_result": "failed_null"},
                )
                return False

            # 关键修复：某些格式返回句柄（int）而不是 bytes，例如 CF_BITMAP
            # 对于句柄类型，只要非 None 就认为成功
            if isinstance(restored_data, int):
                app_logger.log_audio_event(
                    "Format validation passed (handle type)",
                    {
                        "format": fmt,
                        "data_type": "handle",
                        "handle_value": restored_data,
                    },
                )
                return True

            # 对于 bytes 类型，检查数据大小（允许 10% 的差异）
            if isinstance(restored_data, bytes) and isinstance(original_data, bytes):
                size_diff_ratio = abs(len(restored_data) - len(original_data)) / max(
                    len(original_data), 1
                )

                if size_diff_ratio > 0.1:
                    app_logger.log_audio_event(
                        f"Format {fmt} validation failed: size mismatch",
                        {
                            "format": fmt,
                            "original_size": len(original_data),
                            "restored_size": len(restored_data),
                            "diff_ratio": f"{size_diff_ratio:.2%}",
                            "validation_result": "failed_size",
                        },
                    )
                    return False

                app_logger.log_audio_event(
                    "Format validation passed",
                    {
                        "format": fmt,
                        "original_size": len(original_data),
                        "restored_size": len(restored_data),
                    },
                )
                return True

            # 未知类型，保守认为成功
            app_logger.log_audio_event(
                "Format validation passed (unknown type)",
                {"format": fmt, "data_type": type(restored_data).__name__},
            )
            return True

        except Exception as e:
            app_logger.log_audio_event(
                f"Format {fmt} validation failed with exception",
                {"format": fmt, "error": str(e), "validation_result": "exception"},
            )
            return False

    def _restore_all_formats(self, formats: Dict[int, bytes]) -> None:
        """恢复所有格式的剪贴板数据（使用 win32clipboard API）

        Args:
            formats: 字典，键为格式ID，值为该格式的数据（bytes）
        """
        try:
            # 关键优化：按格式依赖关系排序
            sorted_formats = self._sort_formats_by_dependency(formats)
            restorable_formats: Dict[int, Any] = {}
            skipped_formats = []

            # 恢复前先做安全筛选，避免某些注册格式导致 Win32 崩溃（0xc0000374）
            for fmt, data in sorted_formats.items():
                can_restore, reason = self._can_restore_format(fmt, data)
                if can_restore:
                    restorable_formats[fmt] = data
                else:
                    skipped_formats.append(
                        {
                            "format": fmt,
                            "name": self._get_clipboard_format_name(fmt),
                            "reason": reason,
                            "data_type": type(data).__name__,
                            "data_size": len(data)
                            if isinstance(data, (bytes, bytearray, str))
                            else "unknown",
                        }
                    )

            if skipped_formats:
                app_logger.log_audio_event(
                    "Skipping unsafe clipboard formats during restore",
                    {
                        "skipped_count": len(skipped_formats),
                        "skipped_formats": skipped_formats,
                    },
                )

            if not restorable_formats:
                app_logger.log_audio_event(
                    "No clipboard formats eligible for safe restore",
                    {
                        "original_count": len(sorted_formats),
                        "skipped_count": len(skipped_formats),
                    },
                )
                return

            # 获取窗口句柄（关键修复！）
            hwnd = None
            try:
                # 使用桌面窗口作为剪贴板所有者
                hwnd = win32gui.GetDesktopWindow()
                app_logger.log_audio_event("Got desktop window handle", {"hwnd": hwnd})
            except Exception as e:
                app_logger.log_audio_event(
                    "Failed to get desktop window, using NULL",
                    {"error": str(e), "fallback": "null_hwnd"},
                )

            # 使用重试逻辑打开剪贴板（传递窗口句柄）
            if not self._open_clipboard_with_retry(hwnd):
                app_logger.log_error(
                    Exception("Failed to open clipboard after retries"),
                    "_restore_all_formats",
                )
                return

            try:
                # EmptyClipboard必须在OpenClipboard之后调用
                # 并且OpenClipboard必须传递有效的hwnd
                win32clipboard.EmptyClipboard()

                api_success_count = 0
                validated_count = 0
                failed_formats = []
                validation_failed_formats = []

                # 按依赖关系排序后的顺序恢复格式
                for fmt, data in restorable_formats.items():
                    try:
                        payload = bytes(data) if isinstance(data, bytearray) else data
                        result = win32clipboard.SetClipboardData(fmt, payload)
                        # 验证返回值
                        if result is not None:
                            api_success_count += 1
                            app_logger.log_audio_event(
                                "Format API call succeeded",
                                {
                                    "format": fmt,
                                    "name": self._get_clipboard_format_name(fmt),
                                    "data_size": len(payload)
                                    if isinstance(payload, (bytes, bytearray, str))
                                    else "unknown",
                                },
                            )

                            # 对注册格式不做二次读取验证，降低复杂格式上的不确定性
                            if fmt >= self.REGISTERED_FORMAT_START:
                                validated_count += 1
                            # 标准格式继续验证
                            else:
                                is_valid = self._validate_format_restored(fmt, payload)
                                if is_valid:
                                    validated_count += 1
                                else:
                                    validation_failed_formats.append(fmt)
                                    app_logger.log_audio_event(
                                        f"Format {fmt} API succeeded but validation failed",
                                        {"format": fmt, "result": "validation_failed"},
                                    )
                        else:
                            failed_formats.append(fmt)
                            app_logger.log_audio_event(
                                f"SetClipboardData returned NULL for format {fmt}",
                                {"format": fmt, "result": "api_null"},
                            )
                    except Exception as e:
                        # 某些格式可能无法恢复，记录警告但继续
                        failed_formats.append(fmt)
                        app_logger.log_audio_event(
                            f"Failed to restore clipboard format {fmt}",
                            {"error": str(e), "result": "exception"},
                        )

                # 改进的日志记录：区分 API 成功和实际可用
                app_logger.log_audio_event(
                    "Clipboard formats restoration completed",
                    {
                        "total_formats": len(restorable_formats),
                        "requested_formats": len(sorted_formats),
                        "skipped_unsafe_formats": len(skipped_formats),
                        "api_success_count": api_success_count,
                        "validated_count": validated_count,
                        "api_failed_count": len(failed_formats),
                        "validation_failed_count": len(validation_failed_formats),
                        "formats": list(sorted_formats.keys()),
                        "api_failed_formats": failed_formats,
                        "validation_failed_formats": validation_failed_formats,
                    },
                )

                # 关键警告：如果验证失败的格式数量多于成功的格式
                if len(validation_failed_formats) > validated_count:
                    app_logger.log_audio_event(
                        "More formats failed validation than succeeded",
                        {
                            "validated": validated_count,
                            "validation_failed": len(validation_failed_formats),
                            "failed_formats": validation_failed_formats,
                            "severity": "warning",
                        },
                    )

            finally:
                win32clipboard.CloseClipboard()

        except Exception as e:
            app_logger.log_error(e, "_restore_all_formats")

    def restore_clipboard(self, content: Union[str, Dict[int, bytes]]) -> None:
        """恢复剪贴板内容 - 支持所有格式

        Args:
            content: 要恢复的内容，可以是字符串（旧格式兼容）或字典（所有格式）
        """
        try:
            if isinstance(content, dict):
                # 新格式：恢复所有格式
                self._restore_all_formats(content)

                # 尝试获取文本内容用于日志
                text_content = ""
                try:
                    text_content = pyperclip.paste()
                except Exception:
                    pass

                app_logger.log_audio_event(
                    "Clipboard restored (all formats)",
                    {
                        "format_count": len(content),
                        "has_text": bool(text_content),
                        "text_length": len(text_content) if text_content else 0,
                    },
                )

            else:
                # 旧格式：仅恢复文本（向后兼容）
                pyperclip.copy(content)

                app_logger.log_audio_event(
                    "Clipboard restored (text only)", {"content_length": len(content)}
                )

        except Exception as e:
            app_logger.log_error(e, "restore_clipboard")

    def send_ctrl_v(self) -> None:
        """发送Ctrl+V组合键"""
        try:
            # 按下Ctrl键
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            time.sleep(0.01)

            # 按下V键
            win32api.keybd_event(ord("V"), 0, 0, 0)
            time.sleep(0.01)

            # 释放V键
            win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.01)

            # 释放Ctrl键
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

            app_logger.log_audio_event("Ctrl+V sent", {})

        except Exception as e:
            raise TextInputError(f"Failed to send Ctrl+V: {e}")

    def input_via_clipboard(
        self, text: str, restore_delay: Optional[float] = None
    ) -> bool:
        """通过剪贴板输入文本"""
        if not text:
            return True

        restore_delay = restore_delay or self.restore_delay
        original_content: Union[str, Dict[int, bytes], None] = None

        try:
            # 录音模式：跳过backup/restore，避免覆盖外层保存的原始剪贴板
            if self._recording_mode:
                # 直接复制文本
                pyperclip.copy(text)
                time.sleep(0.05)  # 短暂延迟确保复制完成

                # 发送Ctrl+V
                self.send_ctrl_v()

                app_logger.log_audio_event(
                    "Text input via clipboard (recording mode)",
                    {"text_length": len(text), "skipped_restore": True},
                )
                return True

            # 正常模式：保持原有逻辑（backup + restore）
            # 备份原始剪贴板内容
            original_content = self.backup_clipboard()

            # 将文本复制到剪贴板
            pyperclip.copy(text)
            time.sleep(0.05)  # 短暂延迟确保复制完成

            # 发送Ctrl+V
            self.send_ctrl_v()

            # 延迟后恢复原始剪贴板内容
            if restore_delay > 0:
                time.sleep(restore_delay)
                self.restore_clipboard(original_content)

            app_logger.log_audio_event(
                "Text input via clipboard successful",
                {"text_length": len(text), "restore_delay": restore_delay},
            )

            return True

        except Exception as e:
            app_logger.log_error(e, "input_via_clipboard")

            # 尝试恢复剪贴板（仅非录音模式）
            if not self._recording_mode and original_content is not None:
                try:
                    self.restore_clipboard(original_content)
                except (OSError, RuntimeError):
                    pass  # 剪贴板访问失败或已被其他程序占用

            return False

    def set_restore_delay(self, delay: float) -> None:
        """设置剪贴板恢复延迟"""
        self.restore_delay = max(0.0, delay)

        app_logger.log_audio_event(
            "Clipboard restore delay set", {"delay": self.restore_delay}
        )

    def set_recording_mode(self, enabled: bool) -> None:
        """设置录音模式（禁用中途restore避免覆盖原始剪贴板）

        Args:
            enabled: True=启用录音模式（跳过中途restore），False=正常模式
        """
        self._recording_mode = enabled
        app_logger.log_audio_event(
            "Recording mode changed", {"enabled": enabled, "will_skip_restore": enabled}
        )

    def clear_clipboard(self) -> None:
        """清空剪贴板"""
        try:
            pyperclip.copy("")
            app_logger.log_audio_event("Clipboard cleared", {})
        except Exception as e:
            app_logger.log_error(e, "clear_clipboard")

    def get_clipboard_content(self) -> str:
        """获取当前剪贴板内容"""
        try:
            return pyperclip.paste()
        except Exception as e:
            app_logger.log_error(e, "get_clipboard_content")
            return ""

    def _is_elevated(self) -> bool:
        """检查当前进程是否以管理员权限运行"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception as e:
            app_logger.log_audio_event(
                "Failed to check if running as administrator", {"error": str(e)}
            )
            app_logger.log_error(e, "check_elevated_privileges")
            return False

    def test_clipboard_access(self) -> bool:
        """增强的剪贴板访问测试"""
        # 关键修复：录音模式下跳过测试（避免污染原始剪贴板）
        if self._recording_mode:
            app_logger.log_audio_event(
                "Skipping clipboard test in recording mode", {"recording_mode": True}
            )
            return True  # 假设剪贴板可用

        # 基础访问测试
        basic_test = self._check_clipboard_access_level()
        if not basic_test:
            return False

        # 测试Unicode内容支持
        try:
            unicode_test = "测试🎵voice input"  # 包含中文和emoji
            pyperclip.copy(unicode_test)
            result = pyperclip.paste()

            # 清理
            pyperclip.copy("")

            return result == unicode_test
        except Exception as e:
            app_logger.log_audio_event(
                "Unicode clipboard test failed",
                {"error": str(e), "result": "test_exception"},
            )
            return basic_test  # 至少基础测试通过
