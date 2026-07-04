"""主应用协调器

职责：
- 协调各个控制器
- 管理应用生命周期
- 提供简单的对外接口
- 不再直接处理业务逻辑
"""

from typing import Optional, cast

from ..utils import VoiceInputError, app_logger, logger
from .controllers import (
    AIProcessingController,
    InputController,
    RecordingController,
    TranscriptionController,
)
from .di_container import DIContainer
from .interfaces import (
    IAudioService,
    IConfigService,
    IEventService,
    IHotkeyService,
    IInputService,
    ISpeechService,
    IStateManager,
    ISyncTranscriptionService,
)
from .services.application_orchestrator import ApplicationOrchestrator
from .services.config import ConfigKeys
from .services.events import Events
from .services.hot_reload_manager import HotReloadManager
from .services.review_scheduler_service import (
    ReviewSchedulerRunResult,
    ReviewSchedulerService,
)
from .services.storage import HistoryStorageService, ReviewStorageService
from .services.ui_event_bridge import UIEventBridge


class VoiceInputApp:
    """应用协调器

    架构改进：
    - 使用控制器模式拆分职责
    - 通过事件总线解耦组件
    - 使用 StateManager 统一状态管理
    - 使用 ApplicationOrchestrator 编排启动流程
    - 使用 UIEventBridge 解耦UI层通信
    - UI 层通过事件通信
    """

    def __init__(self, container: Optional[DIContainer] = None):
        # 依赖注入容器
        self.container = container or DIContainer()

        # 核心服务
        self.config: IConfigService = self.container.get(IConfigService)
        self.events: IEventService = self.container.get(IEventService)
        self.state: IStateManager = self.container.get(IStateManager)
        self.hot_reload_manager: HotReloadManager = self.container.get(HotReloadManager)

        # 新增服务 - 应用编排和UI事件桥接
        self.orchestrator: ApplicationOrchestrator = self.container.get(
            ApplicationOrchestrator
        )
        self.ui_bridge: UIEventBridge = self.container.get(UIEventBridge)

        # 业务服务（延迟初始化）
        self._audio_service: Optional[IAudioService] = None
        self._speech_service: Optional[ISpeechService] = None
        self._input_service: Optional[IInputService] = None
        self._hotkey_service: Optional[IHotkeyService] = None
        self._history_service: Optional[HistoryStorageService] = None
        self._review_storage_service: Optional[ReviewStorageService] = None
        self._review_scheduler: Optional[ReviewSchedulerService] = None

        # 控制器（延迟初始化）
        self._recording_controller: Optional[RecordingController] = None
        self._transcription_controller: Optional[TranscriptionController] = None
        self._ai_controller: Optional[AIProcessingController] = None
        self._input_controller: Optional[InputController] = None

        # 应用状态
        self.is_initialized = False

        # UI 组件（向后兼容）
        self.recording_overlay = None

        app_logger.log_audio_event(
            "VoiceInputApp initialized with orchestrator and UI bridge", {}
        )

    @property
    def whisper_engine(self) -> Optional[ISpeechService]:
        """向后兼容属性 - MainWindow 期望此属性存在"""
        return self._speech_service

    def initialize(self) -> None:
        """初始化应用"""
        if self.is_initialized:
            return

        try:
            # 配置日志系统
            logger.set_config_service(self.config)

            app_logger.log_audio_event(
                "Initializing voice input app with orchestrator", {}
            )

            # 初始化核心服务
            self._audio_service = self.container.get(IAudioService)
            self._speech_service = self.container.get(ISpeechService)
            self._input_service = self.container.get(IInputService)
            self._history_service = self.container.get(HistoryStorageService)
            if self.container.is_registered(ReviewStorageService):
                self._review_storage_service = self.container.get(ReviewStorageService)
            if self.container.is_registered(ReviewSchedulerService):
                self._review_scheduler = self.container.get(ReviewSchedulerService)
                self._review_scheduler.bind_events(self.events)

            # 初始化快捷键服务（从 DI 容器获取，确保被注册到 config_reload_registry）
            # HotkeyService 在创建时已经注册了所有热键
            # 通过事件系统处理热键触发
            self._hotkey_service = self.container.get(IHotkeyService)

            # 订阅热键触发事件
            self.events.subscribe(Events.HOTKEY_TRIGGERED, self._on_hotkey_triggered)

            # 订阅 speech service 热重载事件
            self.events.subscribe(
                Events.SPEECH_SERVICE_RELOADED, self._on_speech_service_reloaded
            )

            # 获取后端信息用于日志
            from .hotkey_config_helper import get_hotkeys_from_config

            hotkeys, backend = get_hotkeys_from_config(self.config)

            app_logger.log_audio_event(
                "Hotkey service initialized from container",
                {"backend": backend, "registered_hotkeys": hotkeys},
            )

            # 初始化控制器
            self._init_controllers()

            # 设置编排器依赖
            self.orchestrator.set_services(
                audio_service=self._audio_service,
                speech_service=self._speech_service,
                input_service=self._input_service,
                hotkey_service=self._hotkey_service,
            )
            self.orchestrator.set_controllers(
                recording=self._recording_controller,
                transcription=self._transcription_controller,
                ai=self._ai_controller,
                input=self._input_controller,
            )

            # 使用编排器执行启动流程
            self.orchestrator.orchestrate_startup()

            self.is_initialized = True
            self.events.emit(Events.APP_STARTED)

            app_logger.log_audio_event("Voice input app initialized successfully", {})

        except Exception as e:
            app_logger.log_error(e, "initialize")
            self.events.emit(Events.APP_ERROR, str(e))
            raise VoiceInputError(f"Failed to initialize app: {e}")

    def initialize_with_validation(self) -> None:
        """向后兼容方法 - main.py 中环境验证已在外部完成

        注意: main.py 已经在调用此方法前完成了环境验证，
        因此这里只需调用 initialize()
        """
        self.initialize()

    def _init_controllers(self) -> None:
        """初始化所有控制器"""
        # 这些服务在 initialize() 中已注入，此处进入前必为非 None
        assert self._audio_service is not None
        assert self._speech_service is not None
        assert self._input_service is not None
        assert self._history_service is not None

        # 录音控制器
        self._recording_controller = RecordingController(
            audio_service=self._audio_service,
            config_service=self.config,
            event_service=self.events,
            state_manager=self.state,
            speech_service=self._speech_service,
            history_service=self._history_service,
        )

        # 转录控制器（共享 RecordingController 的 streaming_manager）
        # cast: DI 工厂交付的服务(RefactoredTranscriptionService/云服务/NullSpeechService)
        # 均实现 ISyncTranscriptionService 协议,但静态类型只声明为 ISpeechService
        self._transcription_controller = TranscriptionController(
            speech_service=cast(ISyncTranscriptionService, self._speech_service),
            config_service=self.config,
            event_service=self.events,
            state_manager=self.state,
            history_service=self._history_service,
            streaming_manager=self._recording_controller.streaming_manager,
        )

        # AI处理控制器
        self._ai_controller = AIProcessingController(
            config_service=self.config,
            event_service=self.events,
            state_manager=self.state,
            history_service=self._history_service,
            review_storage_service=self._review_storage_service,
        )

        # 输入控制器
        self._input_controller = InputController(
            input_service=self._input_service,
            config_service=self.config,
            event_service=self.events,
            state_manager=self.state,
        )

        # 启动所有控制器（触发 _do_start() 注册事件监听器）
        self._recording_controller.start()
        self._transcription_controller.start()
        self._ai_controller.start()
        self._input_controller.start()

        self._sync_ui_runtime_services()

        app_logger.log_audio_event("All controllers initialized", {})

    def _sync_ui_runtime_services(self) -> None:
        """将最新运行时服务引用同步到 UI facade。"""
        try:
            from .services.ui_services import UIModelService, UISettingsService

            if self.container.is_registered(UISettingsService):
                settings_service = self.container.get(UISettingsService)
                settings_service.sync_runtime_dependencies(
                    transcription_service=self._speech_service,
                    ai_processing_controller=self._ai_controller,
                )

            if self.container.is_registered(UIModelService):
                model_service = self.container.get(UIModelService)
                assert self._speech_service is not None
                model_service.set_speech_service(self._speech_service)
        except Exception as e:
            app_logger.log_error(e, "sync_ui_runtime_services")

    def _on_hotkey_triggered(self, event_data: dict) -> None:
        """快捷键触发处理（事件回调）

        Args:
            event_data: 事件数据，包含 {"action": "toggle_recording"}
        """
        action = event_data.get("action", "toggle_recording")
        if action == "toggle_recording":
            self.toggle_recording()

    def _on_speech_service_reloaded(self, event_data: dict) -> None:
        """处理 speech service 热重载事件

        Args:
            event_data: 事件数据，包含 old_provider, new_provider, changed_key
        """
        app_logger.log_audio_event(
            "VoiceInputApp received speech service reload event", event_data
        )

        # 更新引用和重建控制器
        self._update_speech_service_references()

    def _update_speech_service_references(self) -> None:
        """更新 speech service 引用并重建控制器"""
        try:
            # 1. 从 DI 容器获取新的 speech service
            self._speech_service = self.container.get(ISpeechService)

            # 2. 更新 orchestrator 的引用
            if self.orchestrator:
                self.orchestrator._speech_service = self._speech_service

            # 3. 重建控制器
            self._recreate_controllers()

            app_logger.log_audio_event("Speech service references updated", {})

        except Exception as e:
            app_logger.log_error(e, "update_speech_service_references")
            raise

    def _recreate_controllers(self) -> None:
        """重建控制器（使用新的 speech service）"""
        try:
            # 这些服务在 initialize() 中已注入，重建时必为非 None
            assert self._audio_service is not None
            assert self._speech_service is not None
            assert self._history_service is not None

            # 停止旧控制器
            if self._recording_controller:
                self._recording_controller.stop()
            if self._transcription_controller:
                self._transcription_controller.stop()

            # 重建录音控制器
            self._recording_controller = RecordingController(
                audio_service=self._audio_service,
                config_service=self.config,
                event_service=self.events,
                state_manager=self.state,
                speech_service=self._speech_service,
                history_service=self._history_service,
            )

            # 重建转录控制器（共享 RecordingController 的 streaming_manager）
            self._transcription_controller = TranscriptionController(
                speech_service=cast(ISyncTranscriptionService, self._speech_service),
                config_service=self.config,
                event_service=self.events,
                state_manager=self.state,
                history_service=self._history_service,
                streaming_manager=self._recording_controller.streaming_manager,
            )

            # 启动新控制器
            self._recording_controller.start()
            self._transcription_controller.start()

            # 更新 orchestrator 中的控制器引用
            if self.orchestrator:
                self.orchestrator.set_controllers(
                    recording=self._recording_controller,
                    transcription=self._transcription_controller,
                    ai=self._ai_controller,
                    input=self._input_controller,
                )

            self._sync_ui_runtime_services()

            app_logger.log_audio_event("Controllers recreated successfully", {})

        except Exception as e:
            app_logger.log_error(e, "recreate_controllers")
            raise

    def toggle_recording(self) -> None:
        """切换录音状态"""
        if self._recording_controller:
            self._recording_controller.toggle_recording()

    def run_idle_review_once(self) -> ReviewSchedulerRunResult:
        """Run one local review pass if enabled.

        This method is safe for the manual UI action. It bypasses the idle gate
        but still respects busy-state and session-budget protections.
        """
        if not self._review_scheduler:
            return ReviewSchedulerRunResult(False, "review_scheduler_unavailable")
        if not self.config.get_setting(ConfigKeys.REVIEW_ENABLED, False):
            return ReviewSchedulerRunResult(False, "review_disabled")
        review_service = None
        container_ref = getattr(self, "_container", None)
        if container_ref is not None:
            try:
                from .quality import LLMReviewService

                review_service = container_ref.resolve(LLMReviewService)
            except Exception:
                review_service = None
        return self._review_scheduler.run_once_now(review_service=review_service)

    def set_recording_overlay(self, recording_overlay) -> None:
        """设置录音悬浮窗 (向后兼容方法)

        注意: 现在使用 UIEventBridge 处理UI事件通信
        """
        self.recording_overlay = recording_overlay

        # 使用UI事件桥接器设置事件监听
        self.ui_bridge.setup_overlay_events(recording_overlay)

    def reload_hotkeys(self) -> bool:
        """重新加载快捷键配置（支持多快捷键）"""
        try:
            if self._hotkey_service:
                # 注销所有旧快捷键
                self._hotkey_service.unregister_all_hotkeys()

                # 从配置读取新快捷键列表（支持新旧格式）
                from ..utils import HotkeyRegistrationError
                from .hotkey_config_helper import get_hotkeys_from_config
                from .hotkey_manager_win32 import HotkeyConflictError

                hotkeys, backend = get_hotkeys_from_config(self.config)

                # 注册所有新快捷键，处理冲突
                registered_count = 0
                failed_hotkeys = []

                for hotkey in hotkeys:
                    if hotkey and hotkey.strip():
                        try:
                            self._hotkey_service.register_hotkey(
                                hotkey.strip(), "toggle_recording"
                            )
                            registered_count += 1
                        except HotkeyConflictError as e:
                            # 记录冲突但继续处理其他快捷键
                            failed_hotkeys.append(hotkey.strip())
                            app_logger.log_audio_event(
                                "Hotkey conflict during reload",
                                {
                                    "hotkey": hotkey.strip(),
                                    "suggestions": e.suggestions,
                                },
                            )
                            # 发送事件通知UI
                            self.events.emit(
                                Events.HOTKEY_CONFLICT,
                                {
                                    "hotkey": e.hotkey,
                                    "suggestions": e.suggestions,
                                    "error_code": e.error_code,
                                },
                            )
                        except HotkeyRegistrationError as e:
                            failed_hotkeys.append(hotkey.strip())
                            app_logger.log_error(e, f"hotkey_registration_{hotkey}")
                            self.events.emit(
                                Events.HOTKEY_REGISTRATION_ERROR,
                                {
                                    "hotkey": hotkey.strip(),
                                    "error": str(e),
                                },
                            )
                        except Exception as e:
                            failed_hotkeys.append(hotkey.strip())
                            app_logger.log_error(e, f"hotkey_unexpected_error_{hotkey}")

                app_logger.log_audio_event(
                    "Hotkeys reloaded",
                    {
                        "hotkeys": hotkeys,
                        "registered": registered_count,
                        "failed": len(failed_hotkeys),
                        "failed_hotkeys": failed_hotkeys,
                        "backend": backend,
                    },
                )
                return registered_count > 0
            return False

        except Exception as e:
            app_logger.log_error(e, "reload_hotkeys")
            return False

    def get_status(self) -> dict:
        """获取应用状态"""
        return {
            "is_initialized": self.is_initialized,
            "is_recording": self.state.is_recording(),
            "is_processing": self.state.is_processing(),
            "model_loaded": (
                self._speech_service.model_manager.is_model_loaded()
                if self._speech_service
                and hasattr(self._speech_service, "model_manager")
                else False
            ),
            "hotkey_active": self._hotkey_service.is_listening
            if self._hotkey_service
            else False,
        }

    def _cleanup_resources(self) -> None:
        """清理应用资源（应用关闭阶段调用）"""
        try:
            app_logger.log_audio_event("Cleaning up application resources", {})

            # 移除UI事件桥接
            self.ui_bridge.remove_overlay_events()

            if self._review_scheduler:
                self._review_scheduler.unbind_events(self.events)

            # 停止历史记录服务（关闭线程本地数据库连接）
            if self._history_service and hasattr(self._history_service, "stop"):
                self._history_service.stop()

            # 清理容器
            self.container.cleanup()

            self.is_initialized = False

            app_logger.log_audio_event("Application resources cleaned up", {})

        except Exception as e:
            app_logger.log_error(e, "_cleanup_resources")

    def shutdown(self) -> None:
        """关闭应用"""
        try:
            app_logger.log_audio_event("Shutting down voice input app", {})

            # 使用编排器执行关闭流程
            if hasattr(self.orchestrator, "orchestrate_shutdown"):
                self.orchestrator.orchestrate_shutdown()

            # 最后执行应用资源清理
            self._cleanup_resources()

            app_logger.log_shutdown()

        except Exception as e:
            app_logger.log_error(e, "shutdown")

    def get_initialization_phase(self) -> str:
        """获取当前初始化阶段（委托给编排器）"""
        return self.orchestrator.get_initialization_phase()

    def is_startup_complete(self) -> bool:
        """检查启动是否完成（委托给编排器）"""
        return self.orchestrator.is_startup_complete()
