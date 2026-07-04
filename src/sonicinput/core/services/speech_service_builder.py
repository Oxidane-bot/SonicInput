"""语音服务构建器 — DI 容器与配置热重载共用的唯一工厂

此前 di_container.create_speech_service 与
RefactoredConfigService._create_speech_service 各维护一份几乎相同的
构建逻辑,且已经出现行为漂移(热重载路径会 auto-load 模型,启动路径不会)。
现在两边都调用 build_speech_service(),用 auto_load_model 参数表达差异。
"""

from typing import TYPE_CHECKING, Optional

from ...utils import app_logger
from ..interfaces import IConfigService, IEventService, ISpeechService
from .config import ConfigKeys

if TYPE_CHECKING:
    from ...speech import NullSpeechService


def _find_configured_cloud_provider(config: IConfigService) -> Optional[str]:
    """返回第一个已配置 API key 的云提供商,没有则返回 None"""
    provider_key_map = {
        "qwen": ConfigKeys.TRANSCRIPTION_QWEN_API_KEY,
        "groq": ConfigKeys.TRANSCRIPTION_GROQ_API_KEY,
        "siliconflow": ConfigKeys.TRANSCRIPTION_SILICONFLOW_API_KEY,
    }
    for cloud_provider, key in provider_key_map.items():
        api_key = config.get_setting(key, "")
        if api_key and api_key.strip():
            return cloud_provider
    return None


def build_speech_service(
    config: IConfigService,
    event_service: Optional[IEventService],
    *,
    auto_load_model: bool = False,
) -> ISpeechService:
    """根据当前配置构建语音服务

    行为:
    - provider=local 且本地运行时不可用 → 自动切换到已配置 key 的云提供商,
      否则返回 NullSpeechService 占位
    - provider=local → 用 RefactoredTranscriptionService 包装(线程隔离/流式)
    - 云提供商 → 直接返回(已实现完整 ISpeechService)
    - 任一环节失败 → NullSpeechService(带原因),绝不抛出

    Args:
        config: 配置服务
        event_service: 事件服务(RefactoredTranscriptionService 需要)
        auto_load_model: True 时本地服务构建后立即异步加载模型
            (热重载路径);False 时留给编排器首次录音时懒加载(启动路径)
    """
    from ...speech import NullSpeechService, SpeechServiceFactory

    provider = config.get_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "local")

    def _create_null_service(reason: str) -> "NullSpeechService":
        return NullSpeechService(reason=reason)

    # 智能检测:配置是 local 但环境不支持时,自动切换到云服务
    if provider == "local" and not SpeechServiceFactory._is_local_available():
        switched_to = _find_configured_cloud_provider(config)
        if switched_to:
            config.set_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, switched_to)
            app_logger.log_audio_event(
                "Auto-switched from local to cloud provider",
                {
                    "original_provider": "local",
                    "new_provider": switched_to,
                    "reason": "Local runtime unavailable",
                    "suggestion": "Install sherpa-onnx for local transcription",
                },
            )
            provider = switched_to
        else:
            app_logger.log_audio_event(
                "Local provider unavailable and no cloud provider configured",
                {
                    "original_provider": "local",
                    "reason": "Local runtime unavailable",
                    "action": "Will use stub service",
                    "suggestion": "Configure a cloud provider API key or install sherpa-onnx",
                },
            )
            return _create_null_service("Local provider unavailable")

    def speech_service_factory() -> ISpeechService:
        service = SpeechServiceFactory.create_from_config(config)
        if service is None:
            return _create_null_service("Speech service unavailable")
        return service

    if provider == "local":
        base_service = speech_service_factory()
        if isinstance(base_service, NullSpeechService):
            return base_service

        # 使用 RefactoredTranscriptionService 包装,提供线程隔离和流式转录
        from .transcription_service_refactored import RefactoredTranscriptionService

        transcription_service = RefactoredTranscriptionService(
            speech_service_factory=lambda: base_service,
            event_service=event_service,
            config_service=config,
        )

        if not transcription_service.start():
            app_logger.log_audio_event(
                "Local transcription service failed to start",
                {"action": "Using stub speech service"},
            )
            return _create_null_service("Local transcription service failed to start")

        if auto_load_model and config.get_setting(
            ConfigKeys.TRANSCRIPTION_LOCAL_AUTO_LOAD, True
        ):
            model_name = config.get_setting(
                ConfigKeys.TRANSCRIPTION_LOCAL_MODEL, "paraformer"
            )
            app_logger.log_audio_event(
                "Auto-loading model after hot reload",
                {"model": model_name, "trigger": "hot_reload"},
            )
            transcription_service.load_model_async(
                model_name=model_name,
                callback=lambda result: app_logger.log_audio_event(
                    "Model reloaded after hot-reload", result
                ),
                error_callback=lambda err: app_logger.log_error(
                    err, "model_reload_after_hot_reload"
                ),
            )

        app_logger.log_audio_event(
            "Created local speech service",
            {
                "provider": provider,
                "service_type": type(transcription_service).__name__,
            },
        )
        return transcription_service

    # 云提供商直接返回(Groq/SiliconFlow/Qwen 已实现完整的 ISpeechService)
    cloud_service = speech_service_factory()

    # 云服务也加载模型(虽然只是标记为已加载)
    if (
        cloud_service
        and not isinstance(cloud_service, NullSpeechService)
        and hasattr(cloud_service, "load_model")
    ):
        cloud_service.load_model()

    app_logger.log_audio_event(
        "Created cloud speech service",
        {"provider": provider, "service_type": type(cloud_service).__name__},
    )
    return cloud_service


__all__ = ["build_speech_service"]
