"""Speech Service Factory

Unified speech service creation logic, supporting dynamic switching between providers.
"""

import ctypes
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.interfaces import IConfigService, ISpeechService
from ..core.services.config import ConfigKeys
from ..utils import app_logger
from .sherpa_runtime import (
    configure_sherpa_dll_search_path,
    inspect_onnxruntime_candidates,
)


class SpeechServiceFactory:
    """Speech service factory class

    Responsibilities:
    - Create different speech services based on configuration
    - Unified parameter passing
    - Lazy import for performance optimization
    - Provide clear error messages
    """

    @staticmethod
    def _is_local_available() -> bool:
        """Check if local transcription (sherpa-onnx) is available

        Returns:
            bool: True if sherpa-onnx is installed, False otherwise
        """
        try:
            configure_sherpa_dll_search_path()
            import sherpa_onnx  # noqa: F401

            return True
        except Exception as exc:
            SpeechServiceFactory._log_local_unavailable(exc)
            return False

    @staticmethod
    def _log_local_unavailable(error: Exception) -> None:
        details: Dict[str, Any] = {
            "exception_type": type(error).__name__,
            "error": str(error),
        }

        spec = importlib.util.find_spec("sherpa_onnx")
        if spec and spec.submodule_search_locations:
            base_dir = Path(list(spec.submodule_search_locations)[0])
            pyd_path = base_dir / "lib" / "_sherpa_onnx.pyd"
            details.update(
                {
                    "sherpa_onnx_path": str(base_dir),
                    "pyd_exists": pyd_path.exists(),
                }
            )
            if pyd_path.exists():
                try:
                    ctypes.CDLL(str(pyd_path))
                except OSError as cdll_error:
                    details["pyd_load_error"] = str(cdll_error)

        exe_dir = Path(sys.executable).resolve().parent
        details["exe_dir"] = str(exe_dir)

        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        onnxruntime_candidates = inspect_onnxruntime_candidates()
        details["onnxruntime_locations_checked"] = onnxruntime_candidates
        details["onnxruntime_found"] = any(
            candidate["exists"] for candidate in onnxruntime_candidates
        )

        vc_runtime_dlls = [
            "vcruntime140.dll",
            "vcruntime140_1.dll",
            "msvcp140.dll",
        ]
        details["vc_runtime_present"] = {
            dll: (system32 / dll).exists() for dll in vc_runtime_dlls
        }

        app_logger.log_audio_event("Local provider unavailable", details)

    @staticmethod
    def create_service(
        provider: str,
        api_key: str = "",
        model: str = "large-v3-turbo",
        use_gpu: Optional[bool] = None,
        base_url: Optional[str] = None,
        enable_itn: bool = True,
    ) -> ISpeechService:
        """Create speech service instance

        Args:
            provider: Provider name ("local", "groq", "siliconflow", "qwen")
            api_key: API key (for cloud providers)
            model: Model name
            use_gpu: Use GPU for local provider (None = auto-detect)
            base_url: Custom base URL for cloud providers (optional)
            enable_itn: Enable Inverse Text Normalization for Qwen (optional)

        Returns:
            ISpeechService: Speech service instance

        Raises:
            ValueError: Unsupported provider
            ImportError: Service module import failed
        """
        provider_lower = provider.lower()

        try:
            if provider_lower == "local":
                from .sherpa_engine import SherpaEngine

                # sherpa-onnx 不使用 use_gpu 参数，始终使用 CPU
                # model 参数应该是 sherpa 模型名称 (paraformer | zipformer-small)
                return SherpaEngine(model_name=model)

            elif provider_lower == "groq":
                from .groq_speech_service import GroqSpeechService

                if not api_key:
                    raise ValueError("Groq provider requires API key")
                return GroqSpeechService(
                    api_key=api_key, model=model, base_url=base_url
                )

            elif provider_lower == "siliconflow":
                from .siliconflow_engine import SiliconFlowEngine

                if not api_key:
                    raise ValueError("SiliconFlow provider requires API key")
                return SiliconFlowEngine(
                    api_key=api_key, model_name=model, base_url=base_url
                )

            elif provider_lower == "qwen":
                from .qwen_engine import QwenEngine

                if not api_key:
                    raise ValueError("Qwen provider requires API key")
                return QwenEngine(
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    enable_itn=enable_itn,
                )

            else:
                error_msg = f"Unsupported speech provider: {provider}"
                app_logger.log_audio_event(
                    "Speech service creation failed",
                    {"provider": provider, "error": error_msg},
                )
                raise ValueError(error_msg)

        except ImportError as e:
            error_msg = f"Failed to import {provider} speech service: {str(e)}"
            app_logger.log_error(e, "SpeechServiceFactory.create_service")
            raise ImportError(error_msg)

    @staticmethod
    def create_from_config(config: IConfigService) -> Optional[ISpeechService]:
        """Create speech service from configuration

        Args:
            config: Configuration service instance

        Returns:
            ISpeechService: Speech service instance, None if failed
        """
        try:
            # Read transcription provider (with fallback to legacy whisper config)
            provider = config.get_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "local")

            if provider == "local":
                if not SpeechServiceFactory._is_local_available():
                    app_logger.log_audio_event(
                        "Local provider selected but unavailable",
                        {"suggestion": "Install local runtime dependencies"},
                    )
                    return None
                # Read local (sherpa-onnx) configuration
                model = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_LOCAL_MODEL,
                    "paraformer",  # 默认使用 paraformer 模型
                )
                # sherpa-onnx 不需要 use_gpu 参数，始终使用 CPU
                return SpeechServiceFactory.create_service(
                    provider="local", model=model
                )

            elif provider == "groq":
                # Read Groq configuration
                api_key = config.get_setting(ConfigKeys.TRANSCRIPTION_GROQ_API_KEY, "")
                model = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_GROQ_MODEL, "whisper-large-v3-turbo"
                )
                base_url = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_GROQ_BASE_URL,
                    "https://api.groq.com/openai/v1",
                )

                if not api_key:
                    app_logger.log_audio_event(
                        "Groq provider selected but no API key configured", {}
                    )

                    # Only fallback to local if sherpa-onnx is available
                    if SpeechServiceFactory._is_local_available():
                        app_logger.log_audio_event("Falling back to local provider", {})
                        return SpeechServiceFactory.create_from_config_local_fallback(
                            config
                        )
                    else:
                        app_logger.log_audio_event(
                            "Cannot fallback: sherpa-onnx not installed",
                            {"suggestion": "Install with: uv sync --extra local"},
                        )
                        return None

                # Create Groq service with config_service injection
                from .groq_speech_service import GroqSpeechService

                # Only pass base_url if it's not the default (to use SDK's default)
                service: ISpeechService = GroqSpeechService(
                    api_key=api_key,
                    model=model,
                    base_url=None
                    if base_url == "https://api.groq.com/openai/v1"
                    else base_url,
                    config_service=config,
                )
                return service

            elif provider == "siliconflow":
                # Read SiliconFlow configuration
                api_key = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_SILICONFLOW_API_KEY, ""
                )
                model = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_SILICONFLOW_MODEL,
                    "FunAudioLLM/SenseVoiceSmall",
                )
                base_url = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_SILICONFLOW_BASE_URL,
                    "https://api.siliconflow.cn/v1",
                )

                if not api_key:
                    app_logger.log_audio_event(
                        "SiliconFlow provider selected but no API key configured",
                        {"suggestion": "Configure API key in settings"},
                    )
                    return None

                # Create SiliconFlow service with config_service injection
                from .siliconflow_engine import SiliconFlowEngine

                service = SiliconFlowEngine(
                    api_key=api_key,
                    model_name=model,
                    base_url=None
                    if base_url == "https://api.siliconflow.cn/v1"
                    else base_url,
                    config_service=config,
                )
                return service

            elif provider == "qwen":
                # Read Qwen configuration
                api_key = config.get_setting(ConfigKeys.TRANSCRIPTION_QWEN_API_KEY, "")
                model = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_QWEN_MODEL, "qwen3-asr-flash"
                )
                base_url = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_QWEN_BASE_URL,
                    "https://dashscope.aliyuncs.com",
                )
                enable_itn = config.get_setting(
                    ConfigKeys.TRANSCRIPTION_QWEN_ENABLE_ITN, True
                )

                if not api_key:
                    app_logger.log_audio_event(
                        "Qwen provider selected but no API key configured",
                        {"suggestion": "Configure DashScope API key in settings"},
                    )
                    return None

                # Create Qwen service with config_service injection
                from .qwen_engine import QwenEngine

                service = QwenEngine(
                    api_key=api_key,
                    model=model,
                    base_url=None
                    if base_url == "https://dashscope.aliyuncs.com"
                    else base_url,
                    enable_itn=enable_itn,
                    config_service=config,
                )
                return service

            else:
                app_logger.log_audio_event("Unknown provider", {"provider": provider})

                # Only fallback to local if sherpa-onnx is available
                if SpeechServiceFactory._is_local_available():
                    app_logger.log_audio_event("Falling back to local provider", {})
                    return SpeechServiceFactory.create_from_config_local_fallback(
                        config
                    )
                else:
                    app_logger.log_audio_event(
                        "Cannot fallback: sherpa-onnx not installed",
                        {"suggestion": "Install with: uv sync --extra local"},
                    )
                    return None

        except Exception as e:
            app_logger.log_error(e, "SpeechServiceFactory.create_from_config")

            # Only try to fallback to local if sherpa-onnx is available
            if SpeechServiceFactory._is_local_available():
                try:
                    app_logger.log_audio_event(
                        "Attempting fallback to local provider", {}
                    )
                    return SpeechServiceFactory.create_from_config_local_fallback(
                        config
                    )
                except Exception as fallback_error:
                    app_logger.log_error(
                        fallback_error, "SpeechServiceFactory.fallback"
                    )
                    return None
            else:
                app_logger.log_audio_event(
                    "Cannot fallback: sherpa-onnx not installed",
                    {
                        "original_error": str(e),
                        "suggestion": "Install with: uv sync --extra local",
                    },
                )
                return None

    @staticmethod
    def create_from_config_local_fallback(config: IConfigService) -> ISpeechService:
        """Create local speech service as fallback

        Args:
            config: Configuration service instance

        Returns:
            ISpeechService: Local speech service instance
        """
        model = config.get_setting(
            ConfigKeys.TRANSCRIPTION_LOCAL_MODEL,
            "paraformer",  # 默认使用 paraformer 模型
        )
        # sherpa-onnx 不需要 use_gpu 参数
        return SpeechServiceFactory.create_service(provider="local", model=model)
