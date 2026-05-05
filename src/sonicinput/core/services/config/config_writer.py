"""配置写入服务 - 单一职责：配置写入和持久化"""

import json
import os
import threading
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ....utils import ConfigurationError, app_logger
from ....utils.secure_storage import get_secure_storage


class ConfigWriter:
    """配置写入器 - 只负责写入配置"""

    def __init__(self, config_path: Path):
        """初始化配置写入器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self._config: Dict[str, Any] = {}

        # 防抖保存机制
        self._dirty = False
        self._save_timer: Optional[threading.Timer] = None
        self._save_delay = 0.5  # 500ms 防抖延迟
        self._timer_lock = threading.Lock()

    def set_config(self, config: Dict[str, Any]) -> None:
        """设置完整配置字典

        Args:
            config: 配置字典
        """
        self._config = config

    def set_setting(self, key: str, value: Any) -> None:
        """设置配置项

        Args:
            key: 配置项键名，支持嵌套路径
            value: 要设置的值

        Raises:
            ConfigurationError: 配置项无效或类型不匹配时
        """
        try:
            keys = key.split(".")
            config = self._config

            # 导航到正确的嵌套位置，包含类型验证和自修复
            for i, k in enumerate(keys[:-1]):
                if k not in config:
                    config[k] = {}
                    app_logger.log_audio_event(
                        "Config auto-created missing key",
                        {"key": k, "path": ".".join(keys[: i + 1])},
                    )
                elif not isinstance(config[k], dict):
                    # 关键修复：检测到非字典类型时自动修复
                    old_type = type(config[k]).__name__
                    config[k] = {}
                    app_logger.log_audio_event(
                        "Config auto-repaired type conflict",
                        {
                            "key": k,
                            "path": ".".join(keys[: i + 1]),
                            "old_type": old_type,
                            "new_type": "dict",
                        },
                    )
                config = config[k]

            # 设置值
            config[keys[-1]] = value

            app_logger.log_audio_event(
                "Setting updated", {"key": key, "value_type": type(value).__name__}
            )

        except Exception as e:
            app_logger.log_error(e, f"config_writer_set_{key}")
            raise ConfigurationError(f"Failed to set setting '{key}': {e}")

    def save_config(self) -> bool:
        """保存配置到文件

        Returns:
            是否保存成功
        """
        try:
            # 取消待处理的定时器
            with self._timer_lock:
                if self._save_timer is not None:
                    self._save_timer.cancel()
                    self._save_timer = None

            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            config_to_save = get_secure_storage().secure_store_dict(self._config)

            # 保存配置
            temp_path: Optional[Path] = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.config_path.parent,
                    delete=False,
                    prefix=f"{self.config_path.name}.",
                    suffix=".tmp",
                ) as f:
                    json.dump(config_to_save, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                    temp_path = Path(f.name)

                os.replace(temp_path, self.config_path)
                with self._timer_lock:
                    self._dirty = False
            finally:
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass

            app_logger.log_audio_event(
                "Configuration saved",
                {"config_path": str(self.config_path), "keys_saved": len(self._config)},
            )

            return True

        except Exception as e:
            app_logger.log_error(e, "config_writer_save")
            return False

    def schedule_save(self) -> None:
        """调度延迟保存（防抖）"""
        with self._timer_lock:
            # 取消之前的定时器
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None

            # 标记为脏数据
            self._dirty = True

            # 创建新的定时器（非daemon，确保配置保存完成）
            self._save_timer = threading.Timer(self._save_delay, self._perform_save)
            self._save_timer.daemon = False
            self._save_timer.start()

    def _perform_save(self) -> None:
        """执行实际保存（由定时器调用）"""
        with self._timer_lock:
            should_save = self._dirty

        if should_save:
            try:
                self.save_config()
            except Exception as e:
                app_logger.log_error(e, "config_writer_scheduled_save")

    def flush(self) -> bool:
        """立即保存所有待处理的配置更改

        Returns:
            是否保存成功
        """
        with self._timer_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None

        if self._dirty:
            return self.save_config()
        return True

    def cleanup(self) -> None:
        """清理资源 - 强制保存待处理的配置更改并取消定时器"""
        # 先flush确保所有待处理的配置被保存
        try:
            self.flush()
            app_logger.log_audio_event("Config writer flushed before cleanup", {})
        except Exception as e:
            app_logger.log_error(e, "config_writer_cleanup_flush")

        # 然后清理定时器
        with self._timer_lock:
            if self._save_timer:
                self._save_timer.cancel()
                self._save_timer = None
