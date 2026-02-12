"""配置验证服务 - 单一职责：配置验证和修复"""

from datetime import datetime
from typing import Any, Dict

from ....utils import app_logger


class ConfigValidator:
    """配置验证器 - 只负责验证配置"""

    def __init__(self):
        """初始化配置验证器"""
        pass

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证配置完整性

        Args:
            config: 要验证的配置字典

        Returns:
            验证结果，包含错误信息和修复建议
        """
        issues = []
        warnings = []

        try:
            # 验证快捷键
            hotkeys_config = self._get_nested(config, "hotkeys", None)
            hotkeys = []

            if isinstance(hotkeys_config, dict):
                raw_keys = hotkeys_config.get("keys", [])
                if isinstance(raw_keys, list):
                    hotkeys = [
                        hk.strip()
                        for hk in raw_keys
                        if isinstance(hk, str) and hk.strip()
                    ]
                elif isinstance(raw_keys, str) and raw_keys.strip():
                    hotkeys = [raw_keys.strip()]
            elif isinstance(hotkeys_config, list):
                hotkeys = [
                    hk.strip()
                    for hk in hotkeys_config
                    if isinstance(hk, str) and hk.strip()
                ]
            elif isinstance(hotkeys_config, str) and hotkeys_config.strip():
                hotkeys = [hotkeys_config.strip()]
            else:
                # Very old format: single "hotkey"
                legacy_hotkey = self._get_nested(config, "hotkey", "")
                if isinstance(legacy_hotkey, str) and legacy_hotkey.strip():
                    hotkeys = [legacy_hotkey.strip()]

            if not hotkeys:
                issues.append("Hotkey is not set")

            backend = self._get_nested(config, "hotkeys.backend", "auto")
            if backend not in ["auto", "win32", "pynput"]:
                warnings.append(f"Unknown hotkey backend: {backend}")

            # 验证转录提供商配置
            provider = self._get_nested(config, "transcription.provider", "local")
            valid_providers = ["local", "groq", "siliconflow", "qwen"]
            if provider not in valid_providers:
                warnings.append(f"Unknown transcription provider: {provider}")

            # 本地 sherpa-onnx 配置验证
            if provider == "local":
                model = self._get_nested(
                    config, "transcription.local.model", "paraformer"
                )
                valid_local_models = ["paraformer", "zipformer-small"]
                if model not in valid_local_models:
                    warnings.append(f"Unknown sherpa-onnx model: {model}")

                streaming_mode = self._get_nested(
                    config, "transcription.local.streaming_mode", "chunked"
                )
                valid_streaming_modes = ["chunked", "realtime"]
                if streaming_mode not in valid_streaming_modes:
                    warnings.append(f"Unknown streaming mode: {streaming_mode}")

            # Groq 云服务配置验证
            elif provider == "groq":
                api_key = self._get_nested(config, "transcription.groq.api_key", "")
                if not api_key:
                    warnings.append("Groq provider is selected but API key is not set")

                model = self._get_nested(
                    config, "transcription.groq.model", "whisper-large-v3-turbo"
                )
                valid_groq_models = [
                    "whisper-large-v3",
                    "whisper-large-v3-turbo",
                    "distil-whisper-large-v3-en",
                ]
                if model not in valid_groq_models:
                    warnings.append(f"Unknown Groq model: {model}")

            # SiliconFlow 云服务配置验证
            elif provider == "siliconflow":
                api_key = self._get_nested(
                    config, "transcription.siliconflow.api_key", ""
                )
                if not api_key:
                    warnings.append(
                        "SiliconFlow provider is selected but API key is not set"
                    )

                model = self._get_nested(
                    config,
                    "transcription.siliconflow.model",
                    "FunAudioLLM/SenseVoiceSmall",
                )
                # SiliconFlow 只有一个模型，但允许未来扩展
                valid_siliconflow_models = ["FunAudioLLM/SenseVoiceSmall"]
                if model not in valid_siliconflow_models:
                    warnings.append(f"Unknown SiliconFlow model: {model}")

            # Qwen ASR 云服务配置验证
            elif provider == "qwen":
                api_key = self._get_nested(config, "transcription.qwen.api_key", "")
                if not api_key:
                    warnings.append("Qwen provider is selected but API key is not set")

                model = self._get_nested(
                    config, "transcription.qwen.model", "qwen3-asr-flash"
                )
                # Qwen ASR 模型验证（基于 Qwen 文档）
                valid_qwen_models = ["qwen3-asr-flash", "qwen2-audio-instruct"]
                if model not in valid_qwen_models:
                    warnings.append(f"Unknown Qwen ASR model: {model}")

            # 验证AI配置
            if self._get_nested(config, "ai.enabled", False):
                provider = self._get_nested(config, "ai.provider", "openrouter")
                api_key_path = f"ai.{provider}.api_key"
                api_key = self._get_nested(config, api_key_path, "")
                if not api_key:
                    warnings.append(
                        f"AI is enabled (provider: {provider}) but API key is not set"
                    )

            # 验证音频配置
            sample_rate = self._get_nested(config, "audio.sample_rate", 16000)
            if sample_rate not in [8000, 16000, 22050, 44100, 48000]:
                warnings.append(f"Unusual sample rate: {sample_rate}")

            # 验证UI配置
            theme_color = self._get_nested(config, "ui.theme_color", "cyan")
            valid_theme_colors = [
                "cyan",
                "blue",
                "teal",
                "purple",
                "red",
                "pink",
                "amber",
            ]
            if theme_color and theme_color not in valid_theme_colors:
                warnings.append(f"Unknown theme color: {theme_color}")

            ui_language = self._get_nested(config, "ui.language", "auto")
            valid_ui_languages = ["auto", "en-US", "zh-CN"]
            if ui_language and ui_language not in valid_ui_languages:
                warnings.append(f"Unknown UI language: {ui_language}")

        except Exception as e:
            issues.append(f"Validation error: {e}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "timestamp": datetime.now().isoformat(),
        }

    def validate_and_repair_structure(
        self, config: Dict[str, Any]
    ) -> tuple[Dict[str, Any], bool]:
        """验证和修复整个配置结构完整性

        Args:
            config: 要验证和修复的配置字典

        Returns:
            (修复后的配置, 是否进行了修复)
        """
        try:
            repaired = False

            # 确保ui节点存在且为字典
            if "ui" not in config or not isinstance(config["ui"], dict):
                config["ui"] = {}
                repaired = True

            # 确保ui.overlay_position存在且为字典
            if "overlay_position" not in config["ui"] or not isinstance(
                config["ui"]["overlay_position"], dict
            ):
                config["ui"]["overlay_position"] = {
                    "mode": "preset",
                    "preset": "center",
                    "custom": {"x": 0, "y": 0},
                    "auto_save": True,
                }
                repaired = True

            # 确保ui.overlay_position.custom存在且为字典
            overlay_pos = config["ui"]["overlay_position"]
            if "custom" not in overlay_pos or not isinstance(
                overlay_pos["custom"], dict
            ):
                overlay_pos["custom"] = {"x": 0, "y": 0}
                repaired = True

            # 检查其他关键结构
            required_structures = {
                "audio": {
                    "sample_rate": 16000,
                    "channels": 1,
                    "device_id": None,
                    "chunk_size": 1024,
                },
                "transcription": {
                    "provider": "local",
                    "local": {
                        "model": "paraformer",
                        "language": "zh",
                        "streaming_mode": "chunked",
                        "auto_load": True,
                    },
                },
                "ui": {
                    "show_overlay": True,
                    "launch_at_login": False,
                    "start_minimized": True,
                    "language": "auto",
                },
            }

            for section, defaults in required_structures.items():
                if section not in config or not isinstance(config[section], dict):
                    config[section] = defaults
                    repaired = True
                else:
                    # 确保所有必需的键都存在
                    for key, default_value in defaults.items():
                        if key not in config[section]:
                            config[section][key] = default_value
                            repaired = True

            if repaired:
                app_logger.log_audio_event("Config structure repaired", {})

            return config, repaired

        except Exception as e:
            app_logger.log_error(e, "config_validator_repair")
            return config, False

    def _get_nested(self, config: Dict[str, Any], key: str, default: Any = None) -> Any:
        """获取嵌套配置项

        Args:
            config: 配置字典
            key: 配置项键名，支持嵌套路径
            default: 默认值

        Returns:
            配置项的值
        """
        try:
            keys = key.split(".")
            value = config

            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default

            return value

        except Exception:
            return default
