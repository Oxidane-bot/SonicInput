"""热键服务 - 支持配置热重载

此服务封装热键管理器（Win32 或 Pynput），提供配置热重载能力。

核心功能：
- 管理热键注册和监听
- 支持后端切换（win32/pynput）
- 实现新架构的热重载协议（IHotReloadable）
- 处理热键变更和后端变更

设计理念：
- 服务层封装：隐藏底层管理器实现细节
- 配置驱动：根据配置自动选择和切换后端
- 热重载友好：通过 HotReloadManager 统一管理
"""

from typing import Any, Callable, Dict, List, Optional

from ...utils import app_logger
from ..base.lifecycle_component import LifecycleComponent
from ..interfaces.config import IConfigService
from ..interfaces.hotkey import IHotkeyService
from ..services.config import ConfigKeys


class HotkeyService(LifecycleComponent):
    """热键服务（支持配置热重载）

    封装热键管理器，提供配置热重载能力。
    实现 IConfigReloadable 协议（结构化类型）。
    """

    def __init__(
        self,
        config_service: IConfigService,
        callback: Callable[[str], None],
    ):
        """初始化热键服务

        Args:
            config_service: 配置服务
            callback: 热键触发回调函数
        """
        super().__init__("HotkeyService")
        self._config_service = config_service

        self._callback = callback
        self._manager: Optional[IHotkeyService] = None
        self._current_backend: str = ""
        self._current_keys: List[str] = []

    def _do_start(self) -> bool:
        """启动服务：创建热键管理器并开始监听

        Returns:
            True if start successful
        """
        try:
            # 读取配置
            if not self._config_service:
                app_logger.log_error(
                    Exception("Config service is not initialized"),
                    "HotkeyService._do_start",
                )
                return False

            # 使用 get_setting 获取配置
            backend: str = self._config_service.get_setting(
                ConfigKeys.HOTKEYS_BACKEND, "pynput"
            )
            keys: List[str] = self._config_service.get_setting(
                ConfigKeys.HOTKEYS_KEYS, []
            )

            # 创建管理器
            self._create_manager(backend)

            # 注册热键
            if keys and self._manager:
                for key in keys:
                    try:
                        self._manager.register_hotkey(key, "toggle_recording")
                    except Exception as e:
                        app_logger.log_error(
                            e, f"HotkeyService.start: Failed to register {key}"
                        )

            # 保存当前状态
            self._current_backend = backend
            self._current_keys = keys

            # 开始监听热键
            if self._manager:
                success = self._manager.start_listening()
                if success:
                    app_logger.log_audio_event(
                        "HotkeyService started",
                        {
                            "backend": backend,
                            "keys": keys,
                            "manager_type": type(self._manager).__name__,
                        },
                    )
                    return True
                else:
                    app_logger.log_audio_event(
                        "HotkeyService failed to start listening",
                        {"backend": self._current_backend},
                    )
                    return False
            return False

        except Exception as e:
            app_logger.log_error(e, "HotkeyService._do_start")
            return False

    def _do_stop(self) -> bool:
        """停止服务：停止监听热键并清理资源

        Returns:
            True if stop successful
        """
        try:
            if self._manager:
                # 停止监听
                self._manager.stop_listening()

                # 注销所有热键
                if hasattr(self._manager, "unregister_all_hotkeys"):
                    self._manager.unregister_all_hotkeys()

                app_logger.log_audio_event(
                    "HotkeyService stopped and cleaned up",
                    {"backend": self._current_backend},
                )

                # 清理管理器引用
                self._manager = None

            return True
        except Exception as e:
            app_logger.log_error(e, "HotkeyService._do_stop")
            return False

    def _create_manager(self, backend: str) -> None:
        """创建热键管理器

        Args:
            backend: 后端类型（"win32" 或 "pynput"）
        """
        if backend == "win32":
            from ..hotkey_manager_win32 import Win32HotkeyManager

            self._manager = Win32HotkeyManager(self._callback)
            app_logger.log_audio_event(
                "Created Win32 hotkey manager", {"backend": "win32"}
            )
        elif backend == "pynput":
            from ..hotkey_manager_pynput import PynputHotkeyManager

            self._manager = PynputHotkeyManager(self._callback)
            app_logger.log_audio_event(
                "Created Pynput hotkey manager", {"backend": "pynput"}
            )
        else:
            raise ValueError(f"Unsupported hotkey backend: {backend}")

    # ========== IHotReloadable 协议实现 ==========

    def get_config_dependencies(self) -> List[str]:
        """声明此服务依赖的配置键

        Returns:
            配置键列表
        """
        return ["hotkeys.keys", "hotkeys.backend"]

    def on_config_changed(
        self, changed_keys: List[str], new_config: Dict[str, Any]
    ) -> bool:
        """处理配置变更通知（IHotReloadable 协议）

        由 HotReloadManager 调用，实现统一的热重载流程

        Args:
            changed_keys: 变更的配置键列表
            new_config: 新的完整配置字典

        Returns:
            True 如果重载成功，False 如果失败
        """
        try:
            app_logger.log_audio_event(
                "HotkeyService: Config change notification received",
                {"changed_keys": changed_keys},
            )

            # 获取新热键配置
            hotkeys_config = new_config.get("hotkeys", {})
            new_keys = hotkeys_config.get("keys", [])
            new_backend = hotkeys_config.get("backend", "pynput")

            # 检查是否需要切换后端
            backend_changed = new_backend != self._current_backend

            if backend_changed:
                app_logger.log_audio_event(
                    "Hotkey backend changed, recreating manager",
                    {"old": self._current_backend, "new": new_backend},
                )

                # 停止旧管理器
                if self._manager:
                    try:
                        if hasattr(self._manager, "unregister_all_hotkeys"):
                            self._manager.unregister_all_hotkeys()
                        if hasattr(self._manager, "stop_listening"):
                            self._manager.stop_listening()
                    except Exception as e:
                        app_logger.log_error(e, "Failed to cleanup old hotkey manager")

                # 创建新管理器
                self._create_manager(new_backend)

                # 先启动新管理器（确保消息循环就绪）
                if self._manager:
                    if hasattr(self._manager, "start_listening"):
                        if not self._manager.start_listening():
                            app_logger.log_error(
                                Exception("Failed to start new hotkey manager"),
                                "start_hotkey_manager_failed",
                            )
                            return False

                    # 消息循环就绪后再注册热键
                    for key in new_keys:
                        try:
                            self._manager.register_hotkey(key, "toggle_recording")
                        except Exception as e:
                            app_logger.log_error(e, f"Failed to register hotkey: {key}")
                            # 继续尝试注册其他热键，用户可能只有一个热键冲突

                # 更新状态
                self._current_backend = new_backend
                self._current_keys = new_keys

                app_logger.log_audio_event(
                    "Hotkey backend switched successfully",
                    {"backend": new_backend, "keys": new_keys},
                )

            else:
                # 仅热键变更，使用 reload() 方法
                app_logger.log_audio_event(
                    "Reloading hotkeys (same backend)",
                    {"backend": self._current_backend, "new_keys": new_keys},
                )

                if self._manager and hasattr(self._manager, "reload"):
                    self._manager.reload(new_keys)
                    self._current_keys = new_keys

                    app_logger.log_audio_event(
                        "Hotkeys reloaded successfully", {"keys": new_keys}
                    )
                else:
                    app_logger.log_error(None, "Hotkey manager doesn't support reload")
                    return False

            return True

        except Exception as e:
            app_logger.log_error(e, "HotkeyService.on_config_changed")
            return False

    # ========== 公共接口 ==========

    @property
    def is_listening(self) -> bool:
        """是否正在监听热键"""
        if self._manager:
            return self._manager.is_listening
        return False

    def get_registered_hotkeys(self) -> Dict[str, str]:
        """获取已注册的热键

        Returns:
            热键映射字典
        """
        if self._manager:
            return self._manager.get_registered_hotkeys()
        return {}

    @property
    def current_backend(self) -> str:
        """当前使用的后端"""
        return self._current_backend
