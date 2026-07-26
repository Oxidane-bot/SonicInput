"""Simplified Dependency Injection Container

Minimal DI container following YAGNI principle.
Only provides essential features actually needed by the application.
"""

from datetime import datetime
from enum import Enum
import threading
from typing import Any, Callable, Dict, Type, TypeVar

# Interface imports for create_container()
from .interfaces import (
    IAIService,
    IHotkeyService,
    IInputService,
)
from .interfaces.audio import IAudioService
from .services.events import Events
from .services.ui_services import (
    UIMainService,
    UILocalizationService,
    UIModelService,
    UISettingsService,
)

T = TypeVar("T")


class Lifetime(Enum):
    """Service lifetime"""

    SINGLETON = "singleton"  # One instance for the entire application
    TRANSIENT = "transient"  # New instance each time


class DIContainer:
    """Simplified dependency injection container

    Provides only 3 core responsibilities:
    1. Service registration
    2. Singleton management
    3. Dependency resolution

    Usage:
        container = DIContainer()

        # Register singleton
        container.register_singleton(IMyService, MyServiceImpl)

        # Register transient
        container.register_transient(IMyService, MyServiceImpl)

        # Register with factory
        container.register_singleton(
            IConfigService,
            factory=lambda: ConfigService(config_path)
        )

        # Resolve service
        service = container.resolve(IMyService)
    """

    def __init__(self):
        """Initialize DI container"""
        # Core storage
        self._registrations: Dict[Type, tuple[Callable, Lifetime]] = {}
        self._singletons: Dict[Type, Any] = {}
        # Per-thread resolution chain for circular dependency detection
        self._resolving = threading.local()

    def register_singleton(
        self,
        interface: type,
        implementation: type | None = None,
        factory: Callable[[], object] | None = None,
    ) -> "DIContainer":
        """Register a singleton service

        Args:
            interface: Service interface type
            implementation: Service implementation type (if not using factory)
            factory: Factory function to create service (if not using implementation)

        Returns:
            Self for method chaining

        Example:
            container.register_singleton(IConfigService, ConfigService)
            container.register_singleton(ILogger, factory=lambda: Logger("app"))
        """
        # Self-registration: interface doubles as implementation when neither given
        impl = implementation if implementation is not None else interface
        creator: Callable[[], object] = (
            factory if factory is not None else (lambda: self._create(impl))
        )
        self._registrations[interface] = (creator, Lifetime.SINGLETON)
        return self

    def register_transient(
        self,
        interface: type,
        implementation: type | None = None,
        factory: Callable[[], object] | None = None,
    ) -> "DIContainer":
        """Register a transient service (new instance each time)

        Args:
            interface: Service interface type
            implementation: Service implementation type (if not using factory)
            factory: Factory function to create service (if not using implementation)

        Returns:
            Self for method chaining

        Example:
            container.register_transient(IRequestHandler, RequestHandler)
        """
        impl = implementation if implementation is not None else interface
        creator: Callable[[], object] = (
            factory if factory is not None else (lambda: self._create(impl))
        )
        self._registrations[interface] = (creator, Lifetime.TRANSIENT)
        return self

    def resolve(self, interface: Type[T]) -> T:
        """Resolve a service instance

        Args:
            interface: Service interface type to resolve

        Returns:
            Service instance

        Raises:
            ValueError: If service not registered
            RuntimeError: If a circular dependency is detected during creation

        Example:
            config = container.resolve(IConfigService)
        """
        if interface not in self._registrations:
            raise ValueError(f"Service {interface.__name__} not registered")

        creator, lifetime = self._registrations[interface]

        # Singleton: reuse existing instance (no creation -> no cycle possible)
        if lifetime == Lifetime.SINGLETON and interface in self._singletons:
            return self._singletons[interface]

        instance = self._invoke_creator(interface, creator)

        if lifetime == Lifetime.SINGLETON:
            self._singletons[interface] = instance
        return instance

    def _invoke_creator(self, interface: Type[T], creator: Callable[[], Any]) -> T:
        """Run a creator with circular dependency detection

        Factories typically call ``container.resolve(...)`` for their own
        dependencies. We track the per-thread chain of in-progress
        resolutions; re-entering a type that is still being created means
        the dependency graph has a cycle, which would otherwise die with an
        opaque RecursionError.

        Raises:
            RuntimeError: With the full A -> B -> A chain when a cycle is hit
        """
        chain: list[Type] = getattr(self._resolving, "chain", None) or []
        self._resolving.chain = chain

        if interface in chain:
            cycle = " -> ".join(t.__name__ for t in [*chain, interface])
            raise RuntimeError(
                f"Circular dependency detected: {cycle}. "
                f"Break the cycle by injecting one side lazily "
                f"(e.g. resolve it inside a method instead of the factory)."
            )

        chain.append(interface)
        try:
            return creator()
        finally:
            chain.pop()

    def update_singleton(self, interface: Type[T], new_instance: T) -> None:
        """Update a singleton instance at runtime

        This method allows replacing an existing singleton instance with a new one,
        useful for hot reload scenarios.

        Args:
            interface: The interface/type to update
            new_instance: The new singleton instance

        Raises:
            ValueError: If interface not currently registered as singleton

        Example:
            new_service = create_new_speech_service()
            container.update_singleton(ISpeechService, new_service)
        """
        if interface not in self._singletons:
            raise ValueError(
                f"No singleton registered for {interface.__name__}. "
                f"Only existing singletons can be updated."
            )

        old_instance = self._singletons[interface]
        self._singletons[interface] = new_instance

        # Log the update (import locally to avoid circular dependency)
        try:
            from ..utils import app_logger

            app_logger.log_audio_event(
                "DI container singleton updated",
                {
                    "interface": str(interface),
                    "old_type": type(old_instance).__name__,
                    "new_type": type(new_instance).__name__,
                },
            )
        except Exception:
            # Don't fail if logging fails
            pass

    def _create(self, service_type: Type[T]) -> T:
        """Create service instance with dependency resolution

        Args:
            service_type: Type to instantiate

        Returns:
            Service instance

        Note:
            This is a simple implementation that does NOT handle
            constructor parameter injection. Circular dependencies between
            factories are detected in resolve() (see _invoke_creator).
        """
        try:
            # Simple instantiation without dependency injection
            # If the service needs dependencies, use factory function instead
            return service_type()
        except Exception as e:
            raise RuntimeError(
                f"Failed to create {service_type.__name__}: {e}. "
                f"If this service has dependencies, register it with a factory function."
            )

    def is_registered(self, interface: Type) -> bool:
        """Check if service is registered

        Args:
            interface: Service interface type

        Returns:
            True if registered, False otherwise
        """
        return interface in self._registrations

    def clear(self) -> None:
        """Clear all registrations and singletons

        Useful for testing or resetting the container.
        """
        from ..utils import app_logger

        # Best-effort cleanup for resolved singleton instances
        for interface, instance in reversed(list(self._singletons.items())):
            try:
                if hasattr(instance, "stop"):
                    instance.stop()
                elif hasattr(instance, "cleanup"):
                    instance.cleanup()
            except Exception as e:
                app_logger.log_error(e, f"di_container_clear_{interface.__name__}")

        self._registrations.clear()
        self._singletons.clear()

    # Backward compatibility aliases
    def get(self, interface: Type[T]) -> T:
        """Alias for resolve() - backward compatibility

        Args:
            interface: Service interface type to resolve

        Returns:
            Service instance
        """
        return self.resolve(interface)

    def cleanup(self) -> None:
        """Alias for clear() - backward compatibility

        Clears all registrations and singletons.
        """
        self.clear()


# Migrated from di_container_enhanced.py (Phase 3.5.2a)
def create_container() -> "DIContainer":
    """创建依赖注入容器实例并注册所有服务"""
    container = DIContainer()

    # 显式导入接口（避免import *）
    from ..ai import AIClientFactory
    from ..audio import AudioRecorder
    from ..input import SmartTextInput
    from .interfaces import (
        ICacheService,
        IConfigService,
        IEventService,
        ISpeechService,
        IStateManager,
    )
    from .services.application_orchestrator import ApplicationOrchestrator

    # 服务实现
    from .services.config import RefactoredConfigService
    from .services.dynamic_event_system import DynamicEventSystem
    from .services.hot_reload_manager import HotReloadManager
    from .services.hotkey_service import HotkeyService
    from .services.launch_at_login_service import LaunchAtLoginService
    from .services.state_manager import StateManager
    from .services.ui_event_bridge import UIEventBridge

    # 事件服务 - 单例（最先创建，因为其他服务依赖它）
    container.register_singleton(IEventService, DynamicEventSystem)

    # 缓存服务 - 单例（无依赖，供其他服务使用）
    from .services.cache_service import InMemoryCacheService

    container.register_singleton(ICacheService, InMemoryCacheService)

    # 配置服务 - 单例（需要 EventService 和 Container）
    def create_config_service(container):
        event_service = container.resolve(IEventService)
        return RefactoredConfigService(
            config_path=None, event_service=event_service, container=container
        )

    container.register_singleton(
        IConfigService, factory=lambda: create_config_service(container)
    )

    # Launch-at-login integration service - singleton
    container.register_singleton(LaunchAtLoginService, LaunchAtLoginService)

    # 状态管理器 - 单例（需要 EventService）
    container.register_singleton(IStateManager, StateManager)

    # Hot Reload Manager - 单例 (Phase 3.5.2b: Registered for VoiceInputApp)
    container.register_singleton(HotReloadManager, HotReloadManager)

    # 历史记录服务 - 单例
    from .services.storage import HistoryStorageService, ReviewStorageService

    def create_history_service(container):
        config = container.resolve(IConfigService)
        cache = container.resolve(ICacheService)
        return HistoryStorageService(config, cache_service=cache)

    container.register_singleton(
        HistoryStorageService, factory=lambda: create_history_service(container)
    )

    def create_review_storage_service(container):
        history = container.resolve(HistoryStorageService)
        return ReviewStorageService(history.get_storage_path() / "history.db")

    container.register_singleton(
        ReviewStorageService,
        factory=lambda: create_review_storage_service(container),
    )

    from .quality import LLMReviewService
    from .services.review_scheduler_service import ReviewSchedulerService

    def create_review_scheduler_service(container):
        config = container.resolve(IConfigService)
        history = container.resolve(HistoryStorageService)
        review_storage = container.resolve(ReviewStorageService)
        return ReviewSchedulerService(
            load_recent_records=lambda limit: history.search_records(limit=limit),
            load_review_records=lambda limit, cursor: history.search_records_keyset(
                limit=limit,
                cursor_timestamp=(
                    datetime.fromisoformat(cursor["cursor_timestamp"])
                    if cursor and cursor.get("cursor_timestamp")
                    else None
                ),
                cursor_id=cursor.get("cursor_id") if cursor else None,
            ),
            review_storage=review_storage,
            config=ReviewSchedulerService.config_from_service(config),
        )

    container.register_singleton(
        ReviewSchedulerService,
        factory=lambda: create_review_scheduler_service(container),
    )

    def create_llm_review_service(container):
        config = container.resolve(IConfigService)
        return LLMReviewService(config_service=config)

    container.register_transient(
        LLMReviewService,
        factory=lambda: create_llm_review_service(container),
    )

    # 音频服务 - 瞬态
    def create_audio_service(container):
        config = container.resolve(IConfigService)
        from .services.config import ConfigKeys

        sample_rate = config.get_setting(ConfigKeys.AUDIO_SAMPLE_RATE, 16000)
        channels = config.get_setting(ConfigKeys.AUDIO_CHANNELS, 1)
        chunk_size = config.get_setting(ConfigKeys.AUDIO_CHUNK_SIZE, 1024)

        return AudioRecorder(
            sample_rate=sample_rate,
            channels=channels,
            chunk_size=chunk_size,
            config_service=config,
        )

    container.register_transient(
        IAudioService, factory=lambda: create_audio_service(container)
    )

    # 语音服务 - 单例（构建逻辑与配置热重载共用,见 speech_service_builder）
    def create_speech_service(container):
        from .services.speech_service_builder import build_speech_service

        config = container.resolve(IConfigService)
        event_service = container.resolve(IEventService)
        # 启动路径不 auto-load 模型:留给编排器在首次录音时懒加载
        return build_speech_service(config, event_service, auto_load_model=False)

    container.register_singleton(
        ISpeechService, factory=lambda: create_speech_service(container)
    )

    # AI服务 - 瞬态
    def create_ai_service(container):
        config = container.resolve(IConfigService)
        from .services.config import ConfigKeys

        # 使用工厂从配置创建客户端
        client = AIClientFactory.create_from_config(config)

        # 如果工厂返回 None，创建默认的 OpenRouter 客户端
        if client is None:
            from ..ai import OpenRouterClient

            api_key = config.get_setting(ConfigKeys.AI_OPENROUTER_API_KEY, "")
            return OpenRouterClient(api_key)

        return client

    container.register_transient(
        IAIService, factory=lambda: create_ai_service(container)
    )

    # 输入服务 - 瞬态
    def create_input_service(container):
        config_service = container.resolve(IConfigService)
        return SmartTextInput(config_service)

    container.register_transient(
        IInputService, factory=lambda: create_input_service(container)
    )

    # 快捷键服务 - 单例（需要热重载支持）
    def create_hotkey_service(container):
        # 读取配置以确定使用哪个后端
        config = container.resolve(IConfigService)

        # 创建一个回调函数（调用录音控制器）
        # 注意：此时录音控制器可能还未创建，所以使用延迟绑定
        def hotkey_callback(action: str):
            # 通过事件系统触发，而不是直接调用录音控制器
            # 这样可以解耦 HotkeyService 和 VoiceInputApp
            event_service = container.resolve(IEventService)
            event_service.emit(Events.HOTKEY_TRIGGERED, {"action": action})

        # 使用 HotkeyService 包装器（支持配置热重载）
        hotkey_service = HotkeyService(config, hotkey_callback)

        # Note: Do NOT call initialize() here - VoiceInputApp will do it

        return hotkey_service

    container.register_singleton(
        IHotkeyService, factory=lambda: create_hotkey_service(container)
    )

    # 应用编排器 - 单例（依赖多个核心服务）
    def create_application_orchestrator(container):
        config = container.resolve(IConfigService)
        events = container.resolve(IEventService)
        state = container.resolve(IStateManager)

        return ApplicationOrchestrator(
            config_service=config,
            event_service=events,
            state_manager=state,
        )

    container.register_singleton(
        ApplicationOrchestrator,
        factory=lambda: create_application_orchestrator(container),
    )

    # UI事件桥接器 - 单例（依赖事件服务）
    def create_ui_event_bridge(container):
        events = container.resolve(IEventService)
        return UIEventBridge(event_service=events)

    container.register_singleton(
        UIEventBridge, factory=lambda: create_ui_event_bridge(container)
    )

    # UI localization service - singleton
    def create_ui_localization_service(container):
        config = container.resolve(IConfigService)
        events = container.resolve(IEventService)

        return UILocalizationService(config_service=config, event_service=events)

    container.register_singleton(
        UILocalizationService, factory=lambda: create_ui_localization_service(container)
    )

    # ========================================================================
    # UI 服务 - 为UI层提供专门的服务接口（不依赖VoiceInputApp）
    # ========================================================================

    # UI主窗口服务 - 单例
    def create_ui_main_service(container):
        config = container.resolve(IConfigService)
        events = container.resolve(IEventService)
        state = container.resolve(IStateManager)

        from .services.ui_services import UIMainService

        return UIMainService(
            config_service=config, event_service=events, state_manager=state
        )

    container.register_singleton(
        UIMainService, factory=lambda: create_ui_main_service(container)
    )

    # UI设置服务 - 单例
    def create_ui_settings_service(container):
        config = container.resolve(IConfigService)
        events = container.resolve(IEventService)
        history = container.resolve(HistoryStorageService)
        review_storage = container.resolve(ReviewStorageService)
        localization_service = container.resolve(UILocalizationService)
        launch_at_login_service = container.resolve(LaunchAtLoginService)

        # 尝试获取转录服务和AI控制器(可能还未注册)
        transcription_service = None
        ai_processing_controller = None
        try:
            transcription_service = container.resolve(ISpeechService)
        except Exception as e:
            from ..utils import app_logger

            app_logger.log_audio_event(
                "ISpeechService not yet registered",
                {
                    "context": "Optional dependency for UISettingsService",
                    "error": str(e),
                },
            )

        # AI controller在这个阶段可能还未注册,留空

        from .services.ui_services import UISettingsService

        return UISettingsService(
            config_service=config,
            event_service=events,
            history_service=history,
            transcription_service=transcription_service,
            ai_processing_controller=ai_processing_controller,
            localization_service=localization_service,
            launch_at_login_service=launch_at_login_service,
            review_storage_service=review_storage,
            container=container,  # Pass container for dynamic service resolution after hot reload
        )

    container.register_singleton(
        UISettingsService, factory=lambda: create_ui_settings_service(container)
    )

    # UI模型管理服务 - 单例
    def create_ui_model_service(container):
        speech = container.resolve(ISpeechService)

        from .services.ui_services import UIModelService

        return UIModelService(speech_service=speech)

    container.register_singleton(
        UIModelService, factory=lambda: create_ui_model_service(container)
    )

    # ========================================================================
    # NOTE: cleanup priorities removed in NEW DIContainer API
    # The NEW API manages cleanup automatically based on dependency order
    # ========================================================================

    # ========================================================================
    # Phase 4 Bug Fix: Start LifecycleComponent services after registration
    # ========================================================================
    from ..utils import app_logger

    # Services that need to be started (in dependency order)
    lifecycle_services: list[tuple[type, str]] = [
        (IConfigService, "ConfigService"),
        (IStateManager, "StateManager"),
        (IHotkeyService, "HotkeyService"),
        (HistoryStorageService, "HistoryStorageService"),
    ]

    for service_interface, service_name in lifecycle_services:
        try:
            app_logger.log_audio_event(
                f"Attempting to start {service_name}",
                {"component": "di_container", "service": service_name},
            )
            service: Any = container.resolve(service_interface)
            has_start_method = hasattr(service, "start")
            app_logger.log_audio_event(
                f"{service_name} resolved",
                {"component": "di_container", "has_start": has_start_method},
            )
            if has_start_method:
                start_result = service.start()
                if not start_result:
                    app_logger.log_error(
                        Exception(f"{service_name} failed to start"),
                        f"di_container_start_{service_name}",
                    )
                else:
                    app_logger.log_audio_event(
                        f"{service_name} started successfully",
                        {"component": "di_container"},
                    )
            else:
                app_logger.log_audio_event(
                    f"{service_name} has no start() method",
                    {"component": "di_container"},
                )
        except Exception as e:
            app_logger.log_error(e, f"di_container_start_{service_name}")

    return container
