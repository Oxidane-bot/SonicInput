"""配置迁移服务 - 单一职责：配置版本迁移和升级"""

import os
import shutil
from pathlib import Path
from typing import Any, Dict

from ....utils import app_logger


class ConfigMigrator:
    """配置迁移器 - 只负责配置迁移"""

    def __init__(self, config_path: Path):
        """初始化配置迁移器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path

    def migrate_from_old_app_name(self) -> None:
        """从旧应用名称 'VoiceInputSoftware' 迁移配置到 'SonicInput'"""
        # 只在使用默认路径时才迁移
        if str(self.config_path).find("SonicInput") == -1:
            return

        try:
            old_config_dir = Path(os.environ.get("APPDATA", ".")) / "VoiceInputSoftware"
            old_config_path = old_config_dir / "config.json"

            # 如果新配置已存在，跳过迁移
            if self.config_path.exists():
                return

            # 如果旧配置不存在，跳过迁移
            if not old_config_path.exists():
                return

            app_logger.info("Migrating config from VoiceInputSoftware to SonicInput...")
            app_logger.info(f"  Old path: {old_config_path}")
            app_logger.info(f"  New path: {self.config_path}")

            # 复制配置文件
            shutil.copy2(old_config_path, self.config_path)
            app_logger.info("  Config file copied successfully")

            # 复制日志目录（如果存在）
            old_logs_dir = old_config_dir / "logs"
            new_logs_dir = self.config_path.parent / "logs"

            if old_logs_dir.exists() and old_logs_dir.is_dir():
                if new_logs_dir.exists():
                    app_logger.info(
                        "  New logs directory already exists, skipping logs migration"
                    )
                else:
                    shutil.copytree(old_logs_dir, new_logs_dir)
                    app_logger.info("  Logs directory copied successfully")

            app_logger.info(
                "Config migration from VoiceInputSoftware to SonicInput completed successfully!"
            )
            app_logger.info(
                f"Note: Old config directory still exists at {old_config_dir}"
            )
            app_logger.info(
                "      You can manually delete it if migration was successful."
            )

        except Exception as e:
            app_logger.log_error(e, "config_migration_from_old_app_name")
            app_logger.warning(
                "Failed to migrate config from VoiceInputSoftware. Using default config."
            )

    def migrate_config_structure(
        self, config: Dict[str, Any]
    ) -> tuple[Dict[str, Any], bool]:
        """迁移配置结构，清理旧字段，统一为标准结构

        Args:
            config: 要迁移的配置字典

        Returns:
            (迁移后的配置, 是否进行了迁移)
        """
        migrated = False

        try:
            # 1. Migrate legacy Whisper settings into transcription.local.
            # Supported legacy shapes:
            # - {"whisper": {"model": "...", "language": "...", "auto_load": true}}
            # - {"whisper.model": "...", "whisper.language": "...", "whisper.auto_load": true}
            legacy_whisper: Dict[str, Any] = {}

            if isinstance(config.get("whisper"), dict):
                legacy_whisper.update(config.get("whisper") or {})

            # Support very old flat-dot style keys (override dict values if both exist).
            if "whisper.model" in config:
                legacy_whisper["model"] = config["whisper.model"]
                del config["whisper.model"]
                migrated = True
            if "whisper.language" in config:
                legacy_whisper["language"] = config["whisper.language"]
                del config["whisper.language"]
                migrated = True
            if "whisper.auto_load" in config:
                legacy_whisper["auto_load"] = config["whisper.auto_load"]
                del config["whisper.auto_load"]
                migrated = True

            if legacy_whisper:
                # Ensure target structure exists (defensive against corrupted configs)
                if not isinstance(config.get("transcription"), dict):
                    config["transcription"] = {}
                    migrated = True
                if not isinstance(config["transcription"].get("local"), dict):
                    config["transcription"]["local"] = {}
                    migrated = True

                local_config = config["transcription"]["local"]

                legacy_model = legacy_whisper.get("model")
                if isinstance(legacy_model, str) and legacy_model.strip():
                    old_model = legacy_model.strip()
                    model_mapping = {
                        "whisper-large-v3": "paraformer",
                        "whisper-large-v3-turbo": "paraformer",
                        "large-v3": "paraformer",
                        "large-v3-turbo": "paraformer",
                        "large-v2": "paraformer",
                        "large": "paraformer",
                        "medium": "paraformer",
                        "small": "zipformer-small",
                        "base": "zipformer-small",
                        "tiny": "zipformer-small",
                    }

                    if old_model in model_mapping:
                        new_model = model_mapping[old_model]
                        app_logger.info(
                            f"Migrating: whisper.model '{old_model}' -> "
                            f"transcription.local.model '{new_model}'"
                        )
                    elif old_model in ["paraformer", "zipformer-small"]:
                        new_model = old_model
                        app_logger.info(
                            f"Migrating: whisper.model '{old_model}' -> "
                            f"transcription.local.model '{new_model}'"
                        )
                    else:
                        new_model = "paraformer"
                        app_logger.warning(
                            f"Migrating: Unknown whisper.model '{old_model}' "
                            f"-> transcription.local.model '{new_model}' (default)"
                        )

                    if local_config.get("model") != new_model:
                        local_config["model"] = new_model
                        migrated = True

                legacy_language = legacy_whisper.get("language")
                if isinstance(legacy_language, str) and legacy_language.strip():
                    new_language = legacy_language.strip()
                    if local_config.get("language") != new_language:
                        local_config["language"] = new_language
                        app_logger.info(
                            f"Migrating: whisper.language '{new_language}' -> "
                            f"transcription.local.language"
                        )
                        migrated = True

                legacy_auto_load = legacy_whisper.get("auto_load")
                if isinstance(legacy_auto_load, bool):
                    if local_config.get("auto_load") != legacy_auto_load:
                        local_config["auto_load"] = legacy_auto_load
                        app_logger.info(
                            f"Migrating: whisper.auto_load {legacy_auto_load} -> "
                            f"transcription.local.auto_load"
                        )
                        migrated = True

                # Drop the legacy whisper block after migration.
                if "whisper" in config:
                    del config["whisper"]
                    app_logger.info("Migrating: Removing legacy 'whisper' config block")
                    migrated = True

            if "transcription" in config:
                local_config = config.get("transcription", {}).get("local", {})
                if "model" in local_config:
                    old_model = local_config["model"]
                    # Faster Whisper 模型 -> sherpa-onnx 模型映射
                    model_mapping = {
                        "whisper-large-v3": "paraformer",
                        "whisper-large-v3-turbo": "paraformer",
                        "large-v3": "paraformer",
                        "large-v3-turbo": "paraformer",
                        "large-v2": "paraformer",
                        "large": "paraformer",
                        "medium": "paraformer",
                        "small": "zipformer-small",
                        "base": "zipformer-small",
                        "tiny": "zipformer-small",
                    }

                    if old_model in model_mapping:
                        new_model = model_mapping[old_model]
                        config["transcription"]["local"]["model"] = new_model
                        app_logger.info(
                            f"Migrating: transcription.local.model "
                            f"'{old_model}' -> '{new_model}'"
                        )
                        migrated = True
                    elif old_model not in ["paraformer", "zipformer-small"]:
                        # 未知模型名，默认使用 paraformer
                        config["transcription"]["local"]["model"] = "paraformer"
                        app_logger.warning(
                            f"Migrating: Unknown model '{old_model}' "
                            f"-> 'paraformer' (default)"
                        )
                        migrated = True

            # 2. 删除根级别的旧 openrouter 配置
            if "openrouter" in config:
                app_logger.info("Migrating: Removing root-level 'openrouter' config")
                del config["openrouter"]
                migrated = True

            # 2. 统一 AI provider 配置字段
            if "ai" in config:
                ai_config = config["ai"]

                for provider in ["openrouter", "groq"]:
                    if provider in ai_config:
                        provider_config = ai_config[provider]

                        # 迁移 model_id：优先级 model_id > simple_model_id > model
                        if "model_id" not in provider_config:
                            if "simple_model_id" in provider_config:
                                provider_config["model_id"] = provider_config[
                                    "simple_model_id"
                                ]
                                app_logger.info(
                                    f"Migrating: {provider}.simple_model_id -> model_id"
                                )
                                migrated = True
                            elif "model" in provider_config:
                                provider_config["model_id"] = provider_config["model"]
                                app_logger.info(
                                    f"Migrating: {provider}.model -> model_id"
                                )
                                migrated = True

                        # 删除旧字段
                        for old_field in ["simple_model_id", "model"]:
                            if old_field in provider_config:
                                del provider_config[old_field]
                                migrated = True

                        # 删除所有 provider 级别的 prompt 字段
                        for prompt_field in ["simple_prompt", "prompt"]:
                            if prompt_field in provider_config:
                                del provider_config[prompt_field]
                                migrated = True

                        # 删除旧的 enabled 字段（provider级别的enabled已废弃）
                        if "enabled" in provider_config:
                            del provider_config["enabled"]
                            migrated = True

                        # 删除冗余字段
                        for old_field in ["timeout", "max_retries", "custom_prompt"]:
                            if old_field in provider_config:
                                del provider_config[old_field]
                                migrated = True

            # 3. 删除废弃的历史记录保留配置（当前不再支持清理策略）
            if "history" in config:
                history_config = config.get("history")
                if isinstance(history_config, dict):
                    for old_field in ["max_records", "auto_cleanup_days"]:
                        if old_field in history_config:
                            del history_config[old_field]
                            app_logger.info(f"Migrating: Removing history.{old_field}")
                            migrated = True

            # 3.1 迁移 legacy ui.auto_start -> ui.launch_at_login
            ui_config = config.get("ui")
            if isinstance(ui_config, dict):
                if (
                    "launch_at_login" not in ui_config
                    and "auto_start" in ui_config
                    and isinstance(ui_config.get("auto_start"), bool)
                ):
                    ui_config["launch_at_login"] = ui_config["auto_start"]
                    app_logger.info("Migrating: ui.auto_start -> ui.launch_at_login")
                    migrated = True

                if "auto_start" in ui_config:
                    del ui_config["auto_start"]
                    migrated = True

            # 4. 迁移单个 hotkey 到 hotkeys 数组
            if "hotkey" in config and "hotkeys" not in config:
                old_hotkey = config["hotkey"]
                if isinstance(old_hotkey, str) and old_hotkey.strip():
                    config["hotkeys"] = [old_hotkey]
                    app_logger.info(
                        f"Migrating: hotkey '{old_hotkey}' -> hotkeys array"
                    )
                    migrated = True
                del config["hotkey"]
                migrated = True
            elif "hotkey" in config:
                # 如果两者都存在，删除旧的
                del config["hotkey"]
                app_logger.info("Migrating: Removing redundant 'hotkey' field")
                migrated = True

            # 5. 迁移旧 hotkeys 数组到新结构: {"keys": [...], "backend": "auto"}
            hotkeys_config = config.get("hotkeys")
            if isinstance(hotkeys_config, list):
                keys = [
                    hk.strip()
                    for hk in hotkeys_config
                    if isinstance(hk, str) and hk.strip()
                ]
                if not keys:
                    keys = ["ctrl+shift+v"]
                config["hotkeys"] = {"keys": keys, "backend": "auto"}
                app_logger.info("Migrating: hotkeys list -> hotkeys.{keys,backend}")
                migrated = True
            elif isinstance(hotkeys_config, str) and hotkeys_config.strip():
                config["hotkeys"] = {
                    "keys": [hotkeys_config.strip()],
                    "backend": "auto",
                }
                app_logger.info("Migrating: hotkeys str -> hotkeys.{keys,backend}")
                migrated = True
            elif isinstance(hotkeys_config, dict):
                # Ensure required fields exist for the structured format.
                if "keys" not in hotkeys_config:
                    hotkeys_config["keys"] = ["ctrl+shift+v"]
                    migrated = True
                if "backend" not in hotkeys_config:
                    hotkeys_config["backend"] = "auto"
                    migrated = True

            if migrated:
                app_logger.info("Configuration migration completed")

            return config, migrated

        except Exception as e:
            app_logger.log_error(e, "config_migrator_migrate")
            return config, False
