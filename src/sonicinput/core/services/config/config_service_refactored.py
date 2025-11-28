"""重构后的配置服务 - 门面模式协调各专职服务

使用门面模式（Facade Pattern）协调多个专职服务，保持向后兼容的API。
"""

import copy
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar, Union

from ....utils import ConfigurationError, app_logger
from ...base.lifecycle_component import LifecycleComponent
from ...interfaces import EventPriority, IEventService
from ...interfaces.config import IConfigService
from .config_backup import ConfigBackupService
from .config_keys import ConfigKeys
from .config_migrator import ConfigMigrator
from .config_reader import ConfigReader
from .config_validator import ConfigValidator
from .config_writer import ConfigWriter

T = TypeVar("T")

# Reload triggers for speech service hot reload
SPEECH_SERVICE_RELOAD_TRIGGERS = [
    ConfigKeys.TRANSCRIPTION_PROVIDER,  # local ↔ cloud, cloud ↔ cloud
    ConfigKeys.TRANSCRIPTION_LOCAL_MODEL,  # paraformer ↔ zipformer
]


class RefactoredConfigService(LifecycleComponent, IConfigService):
    """重构后的配置服务 - 门面模式

    协调多个专职服务提供统一的配置管理接口，保持与原ConfigService完全兼容。
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        event_service: Optional[IEventService] = None,
        container = None,
    ):
        """初始化配置服务

        Args:
            config_path: 配置文件路径，None 表示使用默认路径
            event_service: 事件服务实例，用于发送配置变更事件
            container: DI容器实例，用于热重载服务（可选）
        """
        super().__init__("ConfigService")
        self._event_service = event_service
        self._container = container

        # 设置配置文件路径
        if config_path:
            self.config_path = Path(config_path)
        else:
            config_dir = Path(os.environ.get("APPDATA", ".")) / "SonicInput"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = config_dir / "config.json"

        # 初始化各专职服务
        self._reader = ConfigReader(self.config_path)
        self._writer = ConfigWriter(self.config_path)
        self._validator = ConfigValidator()
        self._migrator = ConfigMigrator(self.config_path)
        self._backup = ConfigBackupService(self.config_path)

        # 初始化上次保存的配置快照（用于计算变更）
        self._last_saved_config: Dict[str, Any] = {}

        if app_logger:
            app_logger.log_audio_event(
                "ConfigService initialized",
                {
                    "config_path": str(self.config_path),
                    "config_exists": self.config_path.exists(),
                    "event_service_enabled": self._event_service is not None,
                },
            )

    def _do_start(self) -> bool:
        """Start configuration service

        Returns:
            True if start successful
        """
        try:
            # 检查并迁移旧配置文件
            self._migrator.migrate_from_old_app_name()

            # 加载配置
            if not self.load_config():
                app_logger.log_audio_event(
                    "ConfigService failed to load config",
                    {"config_path": str(self.config_path)},
                )
                return False

            # 初始化上次保存的配置快照（用于计算变更）
            self._last_saved_config = copy.deepcopy(self._reader._config)

            # 验证和修复配置结构完整性
            if not self._validate_and_repair_config_structure():
                app_logger.log_audio_event(
                    "ConfigService failed to validate/repair config structure", {}
                )
                return False

            app_logger.log_audio_event(
                "ConfigService started successfully", {"structure_validated": True}
            )
            return True

        except Exception as e:
            app_logger.log_error(e, "ConfigService_start")
            return False

    def _do_stop(self) -> bool:
        """Stop configuration service and cleanup resources

        Returns:
            True if stop successful
        """
        try:
            # Flush any pending writes
            self._writer.cleanup()

            app_logger.log_audio_event("ConfigService stopped", {})
            return True

        except Exception as e:
            app_logger.log_error(e, "ConfigService_stop")
            return False

    def get_setting(self, key: str, default: Optional[T] = None) -> T:
        """获取配置项

        Args:
            key: 配置项键名，支持嵌套路径 (例如: "whisper.model")
            default: 默认值

        Returns:
            配置项的值，如果不存在则返回默认值
        """
        return self._reader.get_setting(key, default)

    def set_setting(self, key: str, value: Any, immediate: bool = False) -> None:
        """设置配置项

        Args:
            key: 配置项键名，支持嵌套路径
            value: 要设置的值
            immediate: 是否立即保存（默认False，使用防抖机制）

        Raises:
            ConfigurationError: 配置项无效或类型不匹配时
            RuntimeError: 热重载失败时（例如录音进行中）
        """
        old_value = self.get_setting(key)

        # 更新配置
        self._writer.set_setting(key, value)

        # 同步到读取器（使用深拷贝避免引用同步问题）
        self._reader._config = copy.deepcopy(self._writer._config)

        # 发送配置变更事件
        if self._event_service:
            self._event_service.emit(
                "config_changed",
                {
                    "key": key,
                    "old_value": old_value,
                    "new_value": value,
                    "timestamp": datetime.now().isoformat(),
                },
                EventPriority.NORMAL,
            )

        # 保存配置
        if immediate:
            if not self._writer.save_config():
                raise ConfigurationError(
                    f"Failed to save configuration after setting '{key}'"
                )
            self._send_config_saved_event()

            # 检查是否需要热重载 speech service（保存后执行）
            if key in SPEECH_SERVICE_RELOAD_TRIGGERS:
                self._reload_speech_service(key, value)
        else:
            self._writer.schedule_save()

    def set_settings_batch(
        self, changes: dict[str, Any], immediate: bool = False
    ) -> None:
        """批量设置配置项（避免重复热重载）

        Args:
            changes: 配置变更字典 {key: value}
            immediate: 是否立即保存并触发热重载

        Raises:
            ConfigurationError: 配置项无效时
            RuntimeError: 热重载失败时
        """
        if not changes:
            return

        # 1. 批量更新所有配置项
        for key, value in changes.items():
            old_value = self.get_setting(key)

            # 更新配置
            self._writer.set_setting(key, value)

            # 发送配置变更事件
            if self._event_service:
                self._event_service.emit(
                    "config_changed",
                    {
                        "key": key,
                        "old_value": old_value,
                        "new_value": value,
                        "timestamp": datetime.now().isoformat(),
                    },
                    EventPriority.NORMAL,
                )

        # 2. 同步到读取器（一次性）
        self._reader._config = copy.deepcopy(self._writer._config)

        # 3. 保存配置并处理热重载
        if immediate:
            if not self._writer.save_config():
                raise ConfigurationError("Failed to save configuration in batch mode")
            self._send_config_saved_event()

            # 4. 检查是否需要热重载（去重后仅触发一次）
            reload_triggers = [
                key for key in changes.keys() if key in SPEECH_SERVICE_RELOAD_TRIGGERS
            ]
            if reload_triggers:
                # 仅使用第一个触发器的值进行重载（所有触发器针对同一服务）
                first_trigger = reload_triggers[0]
                self._reload_speech_service(first_trigger, changes[first_trigger])
        else:
            self._writer.schedule_save()

    def save_config(self) -> bool:
        """保存配置到文件

        Returns:
            是否保存成功
        """
        success = self._writer.save_config()

        if success:
            self._send_config_saved_event()

        return success

    def load_config(self) -> bool:
        """从文件加载配置

        Returns:
            是否加载成功
        """
        success = self._reader.load_config()

        if success:
            # 执行配置迁移
            config, migrated = self._migrator.migrate_config_structure(
                self._reader._config
            )
            self._reader._config = config
            self._writer.set_config(config)

            if migrated:
                self._writer.save_config()

            # 发送配置加载事件
            if self._event_service:
                self._event_service.emit(
                    "config_loaded",
                    {
                        "config_path": str(self.config_path),
                        "timestamp": datetime.now().isoformat(),
                    },
                    EventPriority.NORMAL,
                )

        return success

    def reset_to_default(self, key: Optional[str] = None) -> None:
        """重置配置到默认值

        Args:
            key: 要重置的配置项键名，None 表示重置所有配置
        """
        if key is None:
            # 重置所有配置
            from .config_defaults import get_default_config

            config = get_default_config()
            self._reader._config = config
            self._writer.set_config(config)
            self.save_config()

            if self._event_service:
                self._event_service.emit(
                    "config_reset",
                    {"type": "full", "timestamp": datetime.now().isoformat()},
                    EventPriority.HIGH,
                )

            app_logger.log_audio_event("Configuration reset to defaults", {})
        else:
            # 重置特定配置项
            old_value = self.get_setting(key)
            default_value = self._reader._get_default_value(key)
            if default_value is not None:
                self.set_setting(key, default_value)

                if self._event_service:
                    self._event_service.emit(
                        "config_reset",
                        {
                            "type": "single",
                            "key": key,
                            "old_value": old_value,
                            "new_value": default_value,
                            "timestamp": datetime.now().isoformat(),
                        },
                        EventPriority.NORMAL,
                    )

    def validate_config(self) -> Dict[str, Any]:
        """验证配置完整性

        Returns:
            验证结果，包含错误信息和修复建议
        """
        return self._validator.validate_config(self._reader._config)

    def get_all_settings(self) -> Dict[str, Any]:
        """获取所有配置的副本

        Returns:
            配置字典的深拷贝
        """
        return self._reader.get_all_settings()

    def get_config_path(self) -> Path:
        """获取配置文件路径

        Returns:
            配置文件的路径
        """
        return self.config_path

    def export_config(self, target_path: Union[str, Path]) -> bool:
        """导出配置到指定路径

        Args:
            target_path: 目标文件路径

        Returns:
            是否导出成功
        """
        return self._backup.export_config(self._reader._config, target_path)

    def import_config(self, source_path: Union[str, Path]) -> bool:
        """从指定路径导入配置

        Args:
            source_path: 源文件路径

        Returns:
            是否导入成功
        """
        imported_config = self._backup.import_config(source_path)

        if imported_config is not None:
            # 合并配置
            old_config = self._reader._config.copy()
            merged_config = self._reader._merge_configs(
                self._reader._config, imported_config
            )

            self._reader._config = merged_config
            self._writer.set_config(merged_config)

            if self.save_config():
                if self._event_service:
                    self._event_service.emit(
                        "config_imported",
                        {
                            "source_path": str(source_path),
                            "timestamp": datetime.now().isoformat(),
                        },
                        EventPriority.HIGH,
                    )
                return True
            else:
                # 恢复原配置
                self._reader._config = old_config
                self._writer.set_config(old_config)
                return False

        return False

    def backup_config(self) -> Optional[str]:
        """创建配置备份

        Returns:
            备份文件路径，失败时返回None
        """
        return self._backup.backup_config(self._reader._config)

    def list_backups(self) -> List[Dict[str, Any]]:
        """列出配置备份

        Returns:
            备份文件信息列表
        """
        return self._backup.list_backups()

    def flush(self) -> bool:
        """立即保存所有待处理的配置更改

        Returns:
            是否保存成功
        """
        success = self._writer.flush()

        if success:
            self._send_config_saved_event()

        return success

    def _validate_and_repair_config_structure(self) -> bool:
        """验证和修复整个配置结构完整性

        Returns:
            是否修复成功
        """
        config, repaired = self._validator.validate_and_repair_structure(
            self._reader._config
        )

        if repaired:
            self._reader._config = config
            self._writer.set_config(config)
            self._writer.save_config()

        return True

    def _calculate_config_diff(
        self, old_config: Dict[str, Any], new_config: Dict[str, Any]
    ) -> set:
        """计算两个配置之间的差异键

        Args:
            old_config: 旧配置
            new_config: 新配置

        Returns:
            变更的键集合（点分隔路径）
        """

        def flatten(config: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
            """将嵌套配置展平为点分隔的键值对"""
            result = {}
            for key, value in config.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    result.update(flatten(value, full_key))
                else:
                    result[full_key] = value
            return result

        old_flat = flatten(old_config)
        new_flat = flatten(new_config)

        changed_keys = set()

        # 检查新增和变更的键
        for key, value in new_flat.items():
            if key not in old_flat or old_flat[key] != value:
                changed_keys.add(key)

        # 检查删除的键
        for key in old_flat:
            if key not in new_flat:
                changed_keys.add(key)

        return changed_keys

    def validate_before_save(self, key: str, value: Any) -> tuple[bool, str]:
        """在保存前验证配置值是否有效

        Args:
            key: 配置项键名（点分隔路径）
            value: 要验证的值

        Returns:
            (is_valid, error_message) 元组。如果有效返回 (True, "")，无效返回 (False, "错误信息")
        """
        # 音频设备验证
        if key == "audio.device_id" or key == ConfigKeys.AUDIO_DEVICE_ID:
            return self._validate_audio_device(value)

        # 快捷键后端验证
        if key == "hotkeys.backend" or key == ConfigKeys.HOTKEYS_BACKEND:
            if value not in ["pynput", "win32"]:
                return (
                    False,
                    f"Invalid hotkey backend: '{value}'. Must be 'pynput' or 'win32'",
                )
            return True, ""

        # 快捷键格式验证
        if key == "hotkey" or key.startswith("hotkeys"):
            # 处理单个快捷键或快捷键列表
            if isinstance(value, list):
                for hotkey in value:
                    is_valid, error = self._validate_hotkey(hotkey)
                    if not is_valid:
                        return False, error
                return True, ""
            else:
                return self._validate_hotkey(value)

        # 转录提供商验证
        if key == "transcription.provider" or key == ConfigKeys.TRANSCRIPTION_PROVIDER:
            return self._validate_transcription_provider(value)

        # 默认：所有其他配置项都视为有效
        return True, ""

    def _validate_audio_device(self, device_id: Optional[int]) -> tuple[bool, str]:
        """验证音频设备 ID 是否有效

        Args:
            device_id: 设备 ID，None 表示默认设备

        Returns:
            (is_valid, error_message)
        """
        try:
            # None 表示默认设备，始终有效
            if device_id is None:
                return True, ""

            # 必须是整数
            if not isinstance(device_id, int):
                return (
                    False,
                    f"Audio device ID must be an integer, got {type(device_id).__name__}",
                )

            # 不能为负数
            if device_id < 0:
                return False, f"Audio device ID cannot be negative (got {device_id})"

            # 使用 PyAudio 检查设备是否存在
            import pyaudio

            audio = None
            try:
                audio = pyaudio.PyAudio()
                device_count = audio.get_device_count()

                # 检查设备索引是否在有效范围内
                if device_id >= device_count:
                    return (
                        False,
                        f"Audio device ID {device_id} does not exist (only {device_count} devices available)",
                    )

                # 检查设备是否有输入通道
                device_info = audio.get_device_info_by_index(device_id)
                if device_info["maxInputChannels"] <= 0:
                    return (
                        False,
                        f"Audio device {device_id} ({device_info.get('name', 'Unknown')}) has no input channels",
                    )

                return True, ""

            finally:
                if audio:
                    audio.terminate()

        except Exception as e:
            app_logger.log_error(e, "validate_audio_device")
            return False, f"Failed to validate audio device: {str(e)}"

    def _validate_hotkey(self, hotkey_str: str) -> tuple[bool, str]:
        """验证快捷键格式是否可解析

        Args:
            hotkey_str: 快捷键字符串（如 "ctrl+shift+v"）

        Returns:
            (is_valid, error_message)
        """
        try:
            if not isinstance(hotkey_str, str):
                return (
                    False,
                    f"Hotkey must be a string, got {type(hotkey_str).__name__}",
                )

            if not hotkey_str or not hotkey_str.strip():
                return False, "Hotkey cannot be empty"

            # 规范化快捷键（移除空格，转小写）
            normalized = hotkey_str.lower().replace(" ", "")

            # 分割修饰键和主键
            parts = normalized.split("+")
            if len(parts) < 1:
                return (
                    False,
                    f"Invalid hotkey format: '{hotkey_str}'. Expected format: 'ctrl+shift+key' or similar",
                )

            # 检查是否有主键（最后一个部分）
            if len(parts[-1]) == 0:
                return (
                    False,
                    f"Invalid hotkey format: '{hotkey_str}'. Missing main key after '+'",
                )

            # 验证修饰键（可选）
            valid_modifiers = {"ctrl", "control", "shift", "alt", "win", "cmd", "meta"}
            for i, part in enumerate(parts[:-1]):  # 除了最后一个主键外的所有部分
                if part not in valid_modifiers:
                    return (
                        False,
                        f"Invalid modifier key '{part}' in hotkey '{hotkey_str}'. Valid modifiers: {', '.join(sorted(valid_modifiers))}",
                    )

            # 基本格式验证通过
            return True, ""

        except Exception as e:
            app_logger.log_error(e, "validate_hotkey")
            return False, f"Failed to validate hotkey: {str(e)}"

    def _validate_transcription_provider(self, provider: str) -> tuple[bool, str]:
        """验证转录提供商配置

        Args:
            provider: 提供商名称（local/groq/siliconflow/qwen）

        Returns:
            (is_valid, error_message)
        """
        try:
            if not isinstance(provider, str):
                return (
                    False,
                    f"Provider must be a string, got {type(provider).__name__}",
                )

            # 检查提供商是否在支持列表中
            valid_providers = ["local", "groq", "siliconflow", "qwen"]
            if provider not in valid_providers:
                return (
                    False,
                    f"Invalid transcription provider '{provider}'. Valid providers: {', '.join(valid_providers)}",
                )

            # 对于云服务提供商，检查 API 密钥是否已配置
            if provider == "groq":
                api_key = self.get_setting("transcription.groq.api_key", "")
                if not api_key or not api_key.strip():
                    return (
                        False,
                        "Groq provider requires an API key. Please enter your Groq API key in the Transcription tab.",
                    )

            elif provider == "siliconflow":
                api_key = self.get_setting("transcription.siliconflow.api_key", "")
                if not api_key or not api_key.strip():
                    return (
                        False,
                        "SiliconFlow provider requires an API key. Please enter your SiliconFlow API key in the Transcription tab.",
                    )

            elif provider == "qwen":
                api_key = self.get_setting("transcription.qwen.api_key", "")
                if not api_key or not api_key.strip():
                    return (
                        False,
                        "Qwen provider requires an API key. Please enter your Qwen API key in the Transcription tab.",
                    )

            return True, ""

        except Exception as e:
            app_logger.log_error(e, "validate_transcription_provider")
            return False, f"Failed to validate transcription provider: {str(e)}"

    def _reload_speech_service(self, changed_key: str, new_value: Any) -> None:
        """热重载 speech service当提供商或模型变更时

        Args:
            changed_key: 触发重载的配置键
            new_value: 新的配置值

        Raises:
            RuntimeError: 录音进行中时不允许重载
        """
        # 检查是否有 DI 容器（可能在早期初始化时未提供）
        if not self._container:
            app_logger.log_audio_event(
                "Speech service reload skipped - DI container not available",
                {"changed_key": changed_key, "new_value": new_value},
            )
            return

        try:
            # 1. 检查录音状态
            from ...interfaces import IStateManager

            state_manager = self._container.resolve(IStateManager)
            if state_manager.is_recording():
                raise RuntimeError(
                    "Cannot change transcription provider while recording. "
                    "Please stop recording first."
                )

            # 2. 获取旧服务实例
            from ...interfaces import ISpeechService

            old_service = self._container.resolve(ISpeechService)
            old_provider = type(old_service).__name__

            app_logger.log_audio_event(
                "Starting speech service reload",
                {
                    "changed_key": changed_key,
                    "new_value": new_value,
                    "old_provider": old_provider,
                },
            )

            # 3. 清理旧服务资源
            self._cleanup_speech_service(old_service)

            # 4. 创建新服务
            new_service = self._create_speech_service()
            new_provider = type(new_service).__name__

            # 5. 更新 DI 容器的单例
            self._container.update_singleton(ISpeechService, new_service)

            # 6. 发送重载完成事件
            if self._event_service:
                self._event_service.emit(
                    "speech_service.reloaded",
                    {
                        "changed_key": changed_key,
                        "old_provider": old_provider,
                        "new_provider": new_provider,
                    },
                    EventPriority.HIGH,
                )

            app_logger.log_audio_event(
                "Speech service reloaded successfully",
                {"from": old_provider, "to": new_provider, "trigger": changed_key},
            )

        except RuntimeError:
            # 重新抛出录音状态错误（用户需要看到）
            raise
        except Exception as e:
            app_logger.log_error(e, "speech_service_reload")
            raise ConfigurationError(
                f"Failed to reload speech service: {str(e)}"
            ) from e

    def _cleanup_speech_service(self, service: Any) -> None:
        """清理旧 speech service 的资源

        Args:
            service: 要清理的旧服务实例
        """
        try:
            # 1. 停止 LifecycleComponent (本地提供商)
            if hasattr(service, "stop") and callable(service.stop):
                service.stop()
                app_logger.log_audio_event("Stopped old speech service", {})

            # 2. 停止流式协调器（如果活跃）
            if hasattr(service, "streaming_coordinator"):
                coordinator = service.streaming_coordinator
                if coordinator and hasattr(coordinator, "is_streaming"):
                    if coordinator.is_streaming():
                        coordinator.stop_streaming()
                        app_logger.log_audio_event("Stopped streaming coordinator", {})

            # 3. 卸载模型（本地提供商）
            if hasattr(service, "unload_model"):
                service.unload_model()
                app_logger.log_audio_event("Unloaded speech model", {})

            # 4. 关闭线程池（云提供商）
            if hasattr(service, "_chunk_accumulator"):
                accumulator = service._chunk_accumulator
                if accumulator and hasattr(accumulator, "shutdown"):
                    accumulator.shutdown()
                    app_logger.log_audio_event("Shutdown chunk accumulator", {})

        except Exception as e:
            app_logger.log_error(e, "speech_service_cleanup")
            # 尽力清理，不抛出异常

    def _create_speech_service(self) -> Any:
        """根据当前配置创建新的 speech service

        Returns:
            新的 speech service 实例

        Raises:
            Exception: 服务创建失败时
        """

        provider = self.get_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "local")

        # 使用 SpeechServiceFactory 从配置创建服务
        from ....speech import SpeechServiceFactory

        if provider == "local":
            # 本地提供商：需要包装在 RefactoredTranscriptionService 中
            base_service = SpeechServiceFactory.create_from_config(self)

            # 包装到 RefactoredTranscriptionService（提供流式支持）
            from ..transcription_service_refactored import (
                RefactoredTranscriptionService,
            )

            wrapped_service = RefactoredTranscriptionService(
                speech_service_factory=lambda: base_service,
                event_service=self._event_service,
                config_service=self,
            )

            # 启动服务
            wrapped_service.start()

            # 热重载后自动加载模型（如果 auto_load 启用）
            if self.get_setting(ConfigKeys.TRANSCRIPTION_LOCAL_AUTO_LOAD, True):
                model_name = self.get_setting(
                    ConfigKeys.TRANSCRIPTION_LOCAL_MODEL, "paraformer"
                )
                app_logger.log_audio_event(
                    "Auto-loading model after hot reload",
                    {"model": model_name, "trigger": "hot_reload"},
                )
                # 异步加载模型，避免阻塞UI
                wrapped_service.load_model_async(
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
                {"provider": provider, "service_type": type(wrapped_service).__name__},
            )

            return wrapped_service
        else:
            # 云提供商：直接返回
            cloud_service = SpeechServiceFactory.create_from_config(self)

            # 云服务加载模型（标记为已加载）
            if hasattr(cloud_service, "load_model"):
                cloud_service.load_model()

            app_logger.log_audio_event(
                "Created cloud speech service",
                {"provider": provider, "service_type": type(cloud_service).__name__},
            )

            return cloud_service

    def _send_config_saved_event(self) -> None:
        """发送配置保存事件"""
        if self._event_service:
            current_config = self._reader._config.copy()

            self._event_service.emit(
                "config_saved",
                {
                    "config_path": str(self.config_path),
                    "timestamp": datetime.now().isoformat(),
                },
                EventPriority.NORMAL,
            )

            # 计算配置变更
            changed_keys = self._calculate_config_diff(
                self._last_saved_config, current_config
            )

            # 发送配置变更事件（用于热重载）
            self._event_service.emit(
                "config.changed",
                {
                    "changed_keys": changed_keys,
                    "old_config": self._last_saved_config.copy(),
                    "new_config": current_config,
                    "config": current_config,  # 保持向后兼容
                    "timestamp": datetime.now().timestamp(),  # 使用 float 时间戳
                },
                EventPriority.HIGH,
            )

            # 更新上次保存的配置
            self._last_saved_config = copy.deepcopy(current_config)
