"""智能文本输入策略选择器"""

from typing import Dict, Optional

from ..core.base.lifecycle_component import LifecycleComponent
from ..core.interfaces import IInputService
from ..core.interfaces.config import IConfigService
from ..core.services.config import ConfigKeys
from ..utils import TextInputError, app_logger
from .clipboard_input import ClipboardInput
from .sendinput import SendInputMethod


class SmartTextInput(LifecycleComponent, IInputService):
    """智能文本输入管理器"""

    def __init__(self, config_service: IConfigService):
        super().__init__("SmartTextInput")
        self.config_service = config_service
        self.clipboard_input = ClipboardInput()
        self.sendinput_method = SendInputMethod()

        # Load settings from config service
        self.preferred_method = self.config_service.get_setting(
            ConfigKeys.INPUT_PREFERRED_METHOD, "sendinput"
        )
        self.fallback_enabled = self.config_service.get_setting(
            ConfigKeys.INPUT_FALLBACK_ENABLED, True
        )

        # 故障转移增强：记录方法失败历史
        self._method_failures = {}
        self._last_failure_time = {}

        # 录音期间剪贴板管理（避免中途restore覆盖原始剪贴板）
        self._recording_mode = False
        self._original_clipboard = ""

    def input_text(self, text: str, force_method: Optional[str] = None) -> bool:
        """智能输入文本"""
        if not text:
            return True

        # 确定使用的输入方法
        method = force_method or self._determine_best_method()

        app_logger.log_audio_event(
            "Starting text input",
            {
                "text_length": len(text),
                "method": method,
                "force_method": force_method is not None,
            },
        )

        # 尝试主要方法
        success = self._try_input_method(text, method)

        if success:
            return True

        # 如果启用了回退且主要方法失败，尝试备用方法
        if self.fallback_enabled and not force_method:
            fallback_method = "sendinput" if method == "clipboard" else "clipboard"

            app_logger.log_audio_event(
                "Trying fallback method", {"fallback_method": fallback_method}
            )

            success = self._try_input_method(text, fallback_method)

            if success:
                app_logger.log_audio_event(
                    "Fallback method succeeded", {"method": fallback_method}
                )
                return True

        # 所有方法都失败
        app_logger.log_error(
            TextInputError(f"All input methods failed for text: {text[:50]}..."),
            "input_text",
        )
        return False

    def _determine_best_method(self) -> str:
        """智能确定最佳输入方法（基于失败历史）"""
        import time

        # 检查首选方法最近的失败情况
        current_time = time.time()

        # 如果首选方法在过去5分钟内失败超过3次，切换到备用方法
        if (
            self.preferred_method in self._method_failures
            and self._method_failures[self.preferred_method] >= 3
            and current_time - self._last_failure_time.get(self.preferred_method, 0)
            < 300
        ):
            # 选择备用方法
            fallback_method = (
                "clipboard" if self.preferred_method == "sendinput" else "sendinput"
            )
            app_logger.log_audio_event(
                "Switching to fallback method due to repeated failures",
                {
                    "failed_method": self.preferred_method,
                    "fallback_method": fallback_method,
                    "failure_count": self._method_failures[self.preferred_method],
                },
            )
            return fallback_method

        # 否则使用首选方法
        return self.preferred_method

    def _try_input_method(self, text: str, method: str) -> bool:
        """尝试特定的输入方法"""
        try:
            if method == "clipboard":
                return self._try_clipboard_method(text)
            elif method == "sendinput":
                return self._try_sendinput_method(text)
            else:
                app_logger.log_error(
                    TextInputError(f"Unknown input method: {method}"),
                    "_try_input_method",
                )
                return False

        except Exception as e:
            app_logger.log_error(e, f"_try_input_method_{method}")
            # 增强错误恢复：记录失败方法以便智能选择下次尝试
            self._record_method_failure(method, str(e))
            return False

    def _try_clipboard_method(self, text: str) -> bool:
        """尝试剪贴板输入方法"""
        try:
            # 先测试剪贴板访问
            if not self.clipboard_input.test_clipboard_access():
                app_logger.log_error(
                    TextInputError("Clipboard access test failed"),
                    "_try_clipboard_method",
                )
                return False

            # 执行剪贴板输入
            return self.clipboard_input.input_via_clipboard(text)

        except Exception as e:
            app_logger.log_error(e, "_try_clipboard_method")
            return False

    def _try_sendinput_method(self, text: str) -> bool:
        """尝试SendInput输入方法"""
        try:
            # 先测试SendInput能力
            if not self.sendinput_method.test_sendinput_capability():
                app_logger.log_error(
                    TextInputError("SendInput capability test failed"),
                    "_try_sendinput_method",
                )
                return False

            # 执行SendInput输入
            return self.sendinput_method.input_via_sendinput(text)

        except Exception as e:
            app_logger.log_error(e, "_try_sendinput_method")
            return False

    def _backup_clipboard(self) -> str:
        """备份剪贴板内容"""
        return self.clipboard_input.backup_clipboard()

    def set_preferred_method(self, method: str) -> None:
        """设置首选输入方法"""
        if method not in ["clipboard", "sendinput"]:
            raise ValueError(f"Invalid method: {method}")

        self.preferred_method = method

        # 持久化到配置
        self.config_service.set_setting("input.preferred_method", method)

        app_logger.log_audio_event("Preferred method set", {"method": method})

    def set_fallback_enabled(self, enabled: bool) -> None:
        """设置是否启用回退机制"""
        self.fallback_enabled = enabled

        # 持久化到配置
        self.config_service.set_setting("input.fallback_enabled", enabled)

        app_logger.log_audio_event("Fallback setting changed", {"enabled": enabled})

    def start_recording_mode(self) -> None:
        """开始录音模式 - 保存原始剪贴板，禁用中途restore"""
        self._recording_mode = True
        self._original_clipboard = self.clipboard_input.backup_clipboard()

        # 通知ClipboardInput进入录音模式（禁用中途restore）
        self.clipboard_input.set_recording_mode(True)

        # 记录剪贴板备份信息（支持新旧格式）
        if isinstance(self._original_clipboard, dict):
            clip_info = f"{len(self._original_clipboard)} formats"
        else:
            clip_info = f"{len(self._original_clipboard)} chars"

        app_logger.log_audio_event(
            "Recording mode started, clipboard saved", {"clipboard_info": clip_info}
        )

    def stop_recording_mode(self) -> None:
        """停止录音模式 - 恢复原始剪贴板"""
        if not self._recording_mode:
            return

        # 先禁用ClipboardInput的录音模式，恢复正常的backup/restore行为
        self.clipboard_input.set_recording_mode(False)

        # 延迟恢复剪贴板，给文本输入时间完成
        import threading
        import time

        restore_delay = self.config_service.get_setting(
            ConfigKeys.INPUT_CLIPBOARD_RESTORE_DELAY, 1.0
        )

        # 关键修复：将剪贴板内容传递给线程，而不是引用实例变量
        # 避免主线程清空变量后，线程无法恢复
        clipboard_to_restore = self._original_clipboard

        def delayed_restore():
            time.sleep(restore_delay)

            if clipboard_to_restore:
                try:
                    self.clipboard_input.restore_clipboard(clipboard_to_restore)

                    # 记录恢复信息（支持新旧格式）
                    if isinstance(clipboard_to_restore, dict):
                        clip_info = f"{len(clipboard_to_restore)} formats"
                    else:
                        clip_info = f"{len(clipboard_to_restore)} chars"

                    app_logger.log_audio_event(
                        "Recording mode stopped, clipboard restored successfully",
                        {"clipboard_info": clip_info},
                    )
                except Exception as e:
                    app_logger.log_error(e, "delayed_restore_clipboard")

        # 使用普通线程（非daemon），确保进程退出前仍有机会完成恢复。
        # 不在这里 join，避免阻塞输入完成事件链路。
        restore_thread = threading.Thread(target=delayed_restore, daemon=False)
        restore_thread.start()
        app_logger.log_audio_event(
            "Clipboard restore scheduled in background",
            {"restore_delay": restore_delay},
        )

        self._recording_mode = False
        self._original_clipboard = ""

    def set_clipboard_restore_delay(self, delay: float) -> None:
        """设置剪贴板恢复延迟"""
        self.clipboard_input.set_restore_delay(delay)

    def set_typing_delay(self, delay: float) -> None:
        """设置SendInput字符间延迟"""
        self.sendinput_method.set_typing_delay(delay)

    def test_all_methods(self) -> Dict[str, bool]:
        """测试所有输入方法"""
        results = {}

        # 测试剪贴板方法
        try:
            results["clipboard"] = self.clipboard_input.test_clipboard_access()
        except Exception:
            results["clipboard"] = False

        # 测试SendInput方法
        try:
            results["sendinput"] = self.sendinput_method.test_sendinput_capability()
        except Exception:
            results["sendinput"] = False

        app_logger.log_audio_event("Input methods tested", results)

        return results

    def _record_method_failure(self, method: str, error_msg: str):
        """记录方法失败信息"""
        import time

        current_time = time.time()
        self._method_failures[method] = self._method_failures.get(method, 0) + 1
        self._last_failure_time[method] = current_time

        app_logger.log_audio_event(
            "Input method failure recorded",
            {
                "method": method,
                "error_message": error_msg,
                "failure_count": self._method_failures[method],
                "time_since_last_failure": current_time
                - self._last_failure_time.get(method, current_time),
            },
        )

        # 如果失败次数过多，清理旧的失败记录（避免永久性禁用）
        if current_time - self._last_failure_time[method] > 1800:  # 30分钟后清理
            if self._method_failures[method] > 10:
                self._method_failures[method] = max(
                    1, self._method_failures[method] // 2
                )
                app_logger.log_audio_event(
                    "Reduced failure count for method",
                    {
                        "method": method,
                        "old_count": self._method_failures[method] * 2,
                        "new_count": self._method_failures[method],
                    },
                )

    def _do_start(self) -> bool:
        """Initialize input system"""
        try:
            app_logger.log_audio_event(
                "Smart text input initialized",
                {
                    "preferred_method": self.preferred_method,
                    "fallback_enabled": self.fallback_enabled,
                },
            )
            return True
        except Exception as e:
            app_logger.log_error(e, "_do_start")
            return False

    def _do_stop(self) -> bool:
        """Cleanup input resources"""
        try:
            # Stop recording mode if active
            if self._recording_mode:
                self.stop_recording_mode()

            # Clear failure tracking
            self._method_failures.clear()
            self._last_failure_time.clear()

            app_logger.log_audio_event("Smart text input stopped")
            return True
        except Exception as e:
            app_logger.log_error(e, "_do_stop")
            return False
