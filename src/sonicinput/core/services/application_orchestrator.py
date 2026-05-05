"""应用编排器实现

负责：
- 应用启动流程编排
- 服务依赖协调
- 生命周期阶段管理
- 错误处理和回滚
- 配置热重载协调
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ...utils import VoiceInputError, app_logger
from ..interfaces import (
    IAudioService,
    IConfigService,
    IEventService,
    IHotkeyService,
    IInputService,
    ISpeechService,
    IStateManager,
)
from ..services.config import ConfigKeys
from .events import Events
from .hot_reload_manager import HotReloadManager


class InitializationPhase(Enum):
    """初始化阶段枚举"""

    NOT_STARTED = "not_started"
    CORE_SERVICES = "core_services"
    CONTROLLERS = "controllers"
    HOTKEY_SETUP = "hotkey_setup"
    MODEL_LOADING = "model_loading"
    COMPLETED = "completed"


class ApplicationOrchestrator:
    """应用编排器实现

    职责：
    - 管理应用启动的各个阶段
    - 协调服务之间的依赖关系
    - 提供阶段化的初始化流程
    - 处理启动过程中的错误和回滚
    """

    def __init__(
        self,
        config_service: IConfigService,
        event_service: IEventService,
        state_manager: IStateManager,
        hot_reload_manager: Optional[HotReloadManager] = None,
    ):
        """初始化应用编排器

        Args:
            config_service: 配置服务
            event_service: 事件服务
            state_manager: 状态管理器
            hot_reload_manager: 热重载管理器（可选）
        """
        self.config = config_service
        self.events = event_service
        self.state = state_manager
        self.hot_reload_manager = hot_reload_manager or HotReloadManager()

        # 初始化状态
        self._current_phase = InitializationPhase.NOT_STARTED
        self._startup_complete = False
        self._initialization_error: Optional[Exception] = None
        self._lazy_model_load_state = "idle"

        # 回调管理
        self._startup_callbacks: Dict[str, List[Callable]] = {}
        self._shutdown_callbacks: List[Callable] = []

        # 服务引用（运行时设置）
        self._audio_service: Optional[IAudioService] = None
        self._speech_service: Optional[ISpeechService] = None
        self._input_service: Optional[IInputService] = None
        self._hotkey_service: Optional[IHotkeyService] = None
        self._history_service: Optional[Any] = None

        # 控制器引用（运行时设置）
        self._controllers: Dict[str, Any] = {}

        # 注册 config_changed_detailed 事件监听，实现统一的热重载
        self.events.on(Events.CONFIG_CHANGED_DETAILED, self._on_config_changed)

        app_logger.log_audio_event("ApplicationOrchestrator initialized", {})

    def set_services(
        self,
        audio_service: IAudioService,
        speech_service: ISpeechService,
        input_service: IInputService,
        hotkey_service: IHotkeyService,
        history_service: Optional[Any] = None,
    ) -> None:
        """设置服务引用并注册到热重载管理器"""
        self._audio_service = audio_service
        self._speech_service = speech_service
        self._input_service = input_service
        self._hotkey_service = hotkey_service
        self._history_service = history_service

        # 注册支持热重载的服务
        self._register_hot_reload_services()

    def set_controllers(self, **controllers) -> None:
        """设置控制器引用"""
        self._controllers.update(controllers)

    def orchestrate_startup(self) -> None:
        """编排应用启动流程"""
        if self._startup_complete:
            return

        try:
            app_logger.log_audio_event("Application startup orchestrated", {})

            # 按阶段初始化
            self._execute_phase(
                InitializationPhase.CORE_SERVICES, self._init_core_services
            )
            self._execute_phase(InitializationPhase.CONTROLLERS, self._init_controllers)
            self._execute_phase(InitializationPhase.HOTKEY_SETUP, self._init_hotkeys)
            # 懒加载模型：首次录制时才加载，跳过启动时的 MODEL_LOADING 阶段
            # 首次 RECORDING_STARTED 事件会触发 _load_model_async()
            self._init_model_loading()

            # 标记启动完成
            self._current_phase = InitializationPhase.COMPLETED
            self._startup_complete = True

            # 触发启动完成事件
            self.events.emit(Events.APP_STARTUP_COMPLETED)
            app_logger.log_audio_event("Application startup completed successfully", {})

        except Exception as e:
            self._initialization_error = e
            app_logger.log_error(e, "orchestrate_startup")

            # 尝试回滚
            self._rollback_initialization()
            raise VoiceInputError(f"Application startup failed: {e}")

    def orchestrate_shutdown(self) -> None:
        """编排应用关闭流程"""
        try:
            app_logger.log_audio_event("Application shutdown orchestrated", {})

            # 执行关闭回调
            for callback in self._shutdown_callbacks:
                try:
                    callback()
                except Exception as e:
                    app_logger.log_error(e, "shutdown_callback")

            # 停止录音
            recording_controller = self._controllers.get("recording")
            if (
                recording_controller
                and hasattr(recording_controller, "is_recording")
                and recording_controller.is_recording()
            ):
                recording_controller.stop_recording()

            # 停止快捷键监听
            if self._hotkey_service:
                try:
                    # Backward compatibility: some implementations may expose stop() only
                    if hasattr(self._hotkey_service, "stop_listening"):
                        self._hotkey_service.stop_listening()
                    elif hasattr(self._hotkey_service, "stop"):
                        self._hotkey_service.stop()

                    if hasattr(self._hotkey_service, "unregister_all_hotkeys"):
                        self._hotkey_service.unregister_all_hotkeys()
                except Exception as e:
                    app_logger.log_error(e, "hotkey_service_cleanup")

            # 卸载模型
            if self._speech_service:
                self._speech_service.unload_model()

            # 清理音频服务 (修复PyAudio资源泄漏)
            if self._audio_service and hasattr(self._audio_service, "cleanup"):
                try:
                    self._audio_service.cleanup()
                    app_logger.log_audio_event("Audio service cleaned up", {})
                except Exception as e:
                    app_logger.log_error(e, "audio_service_cleanup")

            self._current_phase = InitializationPhase.NOT_STARTED
            self._startup_complete = False
            self._lazy_model_load_state = "idle"

            app_logger.log_audio_event("Application shutdown completed", {})

        except Exception as e:
            app_logger.log_error(e, "orchestrate_shutdown")

    def get_initialization_phase(self) -> str:
        """获取当前初始化阶段"""
        return self._current_phase.value

    def is_startup_complete(self) -> bool:
        """检查启动是否完成"""
        return self._startup_complete

    def register_startup_callback(self, phase: str, callback: Callable) -> None:
        """注册启动阶段回调"""
        if phase not in self._startup_callbacks:
            self._startup_callbacks[phase] = []
        self._startup_callbacks[phase].append(callback)
        app_logger.log_audio_event(
            "Startup callback registered",
            {"phase": phase, "callback_count": len(self._startup_callbacks[phase])},
        )

    def register_shutdown_callback(self, callback: Callable) -> None:
        """注册关闭回调"""
        self._shutdown_callbacks.append(callback)
        app_logger.log_audio_event(
            "Shutdown callback registered",
            {"callback_count": len(self._shutdown_callbacks)},
        )

    def _execute_phase(
        self, phase: InitializationPhase, phase_handler: Callable
    ) -> None:
        """执行初始化阶段"""
        self._current_phase = phase
        app_logger.log_audio_event(f"Starting initialization phase: {phase.value}", {})

        # 执行阶段处理器
        phase_handler()

        # 执行注册的回调
        callbacks = self._startup_callbacks.get(phase.value, [])
        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                app_logger.log_error(e, f"phase_callback_{phase.value}")

        app_logger.log_audio_event(f"Completed initialization phase: {phase.value}", {})

    def _init_core_services(self) -> None:
        """初始化核心服务阶段"""
        # 配置日志系统
        from ...utils import logger

        logger.set_config_service(self.config)

        self._start_lifecycle_service(self.config, "ConfigService")
        self._start_lifecycle_service(self.state, "StateManager")
        if self._history_service is not None:
            self._start_lifecycle_service(
                self._history_service, "HistoryStorageService"
            )

        # 核心服务已解析，这里验证运行时依赖
        if not all(
            [
                self._audio_service,
                self._speech_service,
                self._input_service,
            ]
        ):
            raise VoiceInputError("Core services not properly initialized")

    def _start_lifecycle_service(self, service: Any, service_name: str) -> None:
        if not hasattr(service, "start"):
            return
        if getattr(service, "is_running", False):
            return
        if not service.start():
            raise VoiceInputError(f"{service_name} failed to start")

    def _init_controllers(self) -> None:
        """初始化控制器阶段"""
        required_controllers = ["recording", "transcription", "ai", "input"]
        for controller_name in required_controllers:
            if controller_name not in self._controllers:
                raise VoiceInputError(f"Controller '{controller_name}' not initialized")

    def _init_hotkeys(self) -> None:
        """初始化快捷键阶段

        注意：HotkeyService 已经在初始化时注册了热键，
        这里启动热键监听。
        """
        if not self._hotkey_service:
            raise VoiceInputError("Hotkey service not available")

        # 获取热键配置用于日志记录
        from ..hotkey_config_helper import get_hotkeys_from_config

        hotkeys, backend = get_hotkeys_from_config(self.config)

        # HotkeyService 已经在 _on_initialize 中注册了热键
        # 现在启动监听
        if hasattr(self._hotkey_service, "start"):
            self._hotkey_service.start()

        app_logger.log_audio_event(
            "Hotkey service ready",
            {
                "hotkeys": hotkeys,
                "backend": backend,
                "is_listening": self._hotkey_service.is_listening,
            },
        )

    def _init_model_loading(self) -> None:
        """初始化模型加载阶段（懒加载模式）

        不在启动时加载模型，而是订阅 RECORDING_STARTED 事件，
        在用户首次按下热键开始录制时才触发模型加载。
        """
        if not self._should_enable_auto_load():
            return
        provider = self.config.get_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "local")
        if provider != "local":
            app_logger.log_audio_event(
                "Lazy model loading: cloud provider, skipping preload",
                {"provider": provider},
            )
            return

        if self._is_speech_model_loaded():
            self._lazy_model_load_state = "loaded"
            return

        model_name = self.config.get_setting(
            ConfigKeys.TRANSCRIPTION_LOCAL_MODEL, "paraformer"
        )
        from sonicinput.speech.sherpa_models import SherpaModelManager

        cache_checker = SherpaModelManager()
        if not cache_checker.is_model_cached(model_name):
            app_logger.log_audio_event(
                "Lazy model loading: model not cached, will load on first recording",
                {"model_name": model_name},
            )
            # 模型未缓存时仍订阅事件，首次录制时触发下载+加载
            self._register_lazy_model_load(model_name)
            return

        app_logger.log_audio_event(
            "Lazy model loading: model cached, will load on first recording",
            {"model_name": model_name},
        )
        self._register_lazy_model_load(model_name)

    def _register_lazy_model_load(self, model_name: str) -> None:
        """注册懒加载回调：首次 RECORDING_STARTED 时触发模型加载"""
        if self._lazy_model_load_state != "idle":
            return

        def on_first_recording(_data: Any = None) -> None:
            if self._lazy_model_load_state != "idle":
                return
            # 保险检查：模型可能已在其他地方加载
            if self._is_speech_model_loaded():
                self._lazy_model_load_state = "loaded"
                app_logger.log_audio_event(
                    "Lazy load: model already loaded, skipping", {}
                )
                return
            try:
                self._lazy_model_load_state = "loading"
                app_logger.log_audio_event(
                    "Lazy load: first recording detected, loading model",
                    {"model_name": model_name},
                )
                if not self._load_model_async(model_name, download_if_missing=True):
                    self._handle_lazy_model_load_failure(
                        model_name,
                        "Unable to start lazy model loading",
                    )
            except Exception as e:
                self._handle_lazy_model_load_failure(model_name, str(e))

        self.events.once(Events.RECORDING_STARTED, on_first_recording)

    def _is_speech_model_loaded(self) -> bool:
        return bool(
            self._speech_service is not None
            and hasattr(self._speech_service, "is_model_loaded")
            and self._speech_service.is_model_loaded
        )

    def _handle_lazy_model_load_failure(self, model_name: str, error_msg: str) -> None:
        self._lazy_model_load_state = "idle"
        app_logger.log_error(Exception(error_msg), "load_model_async")
        self.events.emit(
            Events.MODEL_LOADING_FAILED,
            {"model_name": model_name, "error": error_msg},
        )
        self.events.emit(Events.MODEL_LOADING_ERROR, error_msg)
        self._register_lazy_model_load(model_name)

    def _should_enable_auto_load(self) -> bool:
        """判断是否应该启用自动加载"""
        # 检查转录提供商
        provider = self.config.get_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "local")

        # 如果使用云端转录，不自动加载本地模型
        if provider != "local":
            return False

        # 否则根据配置决定
        return self.config.get_setting(ConfigKeys.TRANSCRIPTION_LOCAL_AUTO_LOAD, True)

    def _load_model_async(
        self, model_name: str, download_if_missing: bool = False
    ) -> bool:
        """异步加载语音模型"""
        if not self._speech_service:
            app_logger.log_audio_event(
                "Model loading skipped: speech service not available",
                {"model_name": model_name},
            )
            return False
        if (
            hasattr(self._speech_service, "is_running")
            and not self._speech_service.is_running
        ):
            app_logger.log_audio_event(
                "Model loading skipped: speech service not running",
                {"model_name": model_name},
            )
            return False
        if not hasattr(self._speech_service, "load_model_async"):
            app_logger.log_audio_event(
                "Model loading skipped: async load not supported",
                {"model_name": model_name},
            )
            return False
        self.events.emit(Events.MODEL_LOADING_STARTED)

        def on_success(result: Dict[str, Any]):
            """成功回调

            Args:
                result: 包含以下键的字典:
                    - success: bool
                    - model_name: str
                    - model_info: Dict[str, Any]
            """
            success = result.get("success", False)
            result_model_name = result.get("model_name", model_name)
            model_info = result.get("model_info", {})

            if not success:
                self._handle_lazy_model_load_failure(
                    result_model_name,
                    result.get("error", "Model load task returned success=False"),
                )
                return

            app_logger.log_audio_event(
                "Model loaded successfully", {"model": result_model_name}
            )

            # 如果结果中没有model_info，尝试获取
            if not model_info:
                if hasattr(self._speech_service, "get_model_info"):
                    model_info = self._speech_service.get_model_info()
                else:
                    model_info = {
                        "model_name": result_model_name,
                        "is_loaded": True,
                        "device": getattr(self._speech_service, "device", "Unknown"),
                    }

            self._lazy_model_load_state = "loaded"
            self.events.emit(Events.MODEL_LOADING_COMPLETED, model_info)
            self.events.emit(Events.MODEL_LOADED, model_info)

        def on_error(error_msg: str):
            self._handle_lazy_model_load_failure(model_name, error_msg)

        self._speech_service.load_model_async(
            model_name=model_name,
            callback=on_success,
            error_callback=on_error,
            download_if_missing=download_if_missing,
        )
        return True

    def _register_hot_reload_services(self) -> None:
        """注册支持热重载的服务到HotReloadManager"""
        services_to_register = [
            ("audio", self._audio_service),
            ("speech", self._speech_service),
            ("input", self._input_service),
            ("hotkey", self._hotkey_service),
        ]

        registered_count = 0
        for service_name, service in services_to_register:
            if (
                service
                and hasattr(service, "get_config_dependencies")
                and hasattr(service, "on_config_changed")
            ):
                try:
                    self.hot_reload_manager.register_service(service_name, service)
                    registered_count += 1
                    app_logger.log_audio_event(
                        f"Registered {service_name} for hot reload",
                        {"config_deps": service.get_config_dependencies()},
                    )
                except Exception as e:
                    app_logger.log_error(e, f"register_hot_reload_{service_name}")

        app_logger.log_audio_event(
            "Hot reload service registration completed",
            {"registered_services": registered_count},
        )

    def _on_config_changed(self, data: Dict[str, Any]) -> None:
        """配置变更事件处理器（内部方法）

        当 ConfigService 发出 config_changed_detailed 事件时自动调用

        Args:
            data: 事件数据，包含 changed_keys, old_config, new_config
        """
        try:
            changed_keys = data.get("changed_keys", [])
            new_config = data.get("new_config", {})

            app_logger.log_audio_event(
                "Config change event received, triggering hot-reload",
                {"changed_keys": changed_keys},
            )

            # 调用公共接口进行热重载
            self.notify_config_changed(changed_keys, new_config)

        except Exception as e:
            app_logger.log_error(e, "ApplicationOrchestrator._on_config_changed")

    def notify_config_changed(
        self, changed_keys: List[str], new_config: Dict[str, Any]
    ) -> bool:
        """通知配置变更到所有注册的服务

        Args:
            changed_keys: 变更的配置键列表
            new_config: 新的配置字典

        Returns:
            True if all reloads successful, False if any failed
        """
        app_logger.log_audio_event(
            "Notifying config changes to services", {"changed_keys": changed_keys}
        )

        success = self.hot_reload_manager.notify_config_changed(
            changed_keys, new_config
        )

        if success:
            app_logger.log_audio_event("Config hot-reload completed successfully", {})
        else:
            app_logger.log_error(
                Exception("Config hot-reload failed"), "notify_config_changed"
            )

        return success

    def _rollback_initialization(self) -> None:
        """回滚初始化（错误处理）"""
        try:
            app_logger.log_audio_event("Rolling back initialization", {})

            # 停止快捷键监听
            if self._hotkey_service:
                try:
                    if hasattr(self._hotkey_service, "stop_listening"):
                        self._hotkey_service.stop_listening()
                    elif hasattr(self._hotkey_service, "stop"):
                        self._hotkey_service.stop()

                    if hasattr(self._hotkey_service, "unregister_all_hotkeys"):
                        self._hotkey_service.unregister_all_hotkeys()
                except Exception as e:
                    app_logger.log_error(e, "hotkey_service_rollback_cleanup")

            # 重置状态
            self._current_phase = InitializationPhase.NOT_STARTED
            self._startup_complete = False

            app_logger.log_audio_event("Initialization rollback completed", {})

        except Exception as e:
            app_logger.log_error(e, "rollback_initialization")
