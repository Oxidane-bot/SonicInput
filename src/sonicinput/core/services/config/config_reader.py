"""配置读取服务 - 单一职责：配置读取和查询"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional, TypeVar, cast

from ....utils import app_logger
from .config_defaults import get_default_config

T = TypeVar("T")


class ConfigReader:
    """配置读取器 - 只负责读取配置"""

    def __init__(self, config_path: Path):
        """初始化配置读取器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self._default_config = get_default_config()

    def load_config(self) -> bool:
        """从文件加载配置

        Returns:
            是否加载成功
        """
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded_config = json.load(f)

                # 合并默认配置和加载的配置
                self._config = self._merge_configs(self._default_config, loaded_config)

                app_logger.log_audio_event(
                    "Configuration loaded",
                    {
                        "config_path": str(self.config_path),
                        "keys_loaded": len(loaded_config),
                    },
                )
            else:
                # 使用默认配置
                self._config = copy.deepcopy(self._default_config)

                app_logger.log_audio_event(
                    "Using default configuration",
                    {"config_path": str(self.config_path)},
                )

            return True

        except Exception as e:
            app_logger.log_error(e, "config_reader_load")
            self._config = copy.deepcopy(self._default_config)
            return False

    def get_setting(self, key: str, default: Optional[T] = None) -> T:
        """获取配置项

        Args:
            key: 配置项键名，支持嵌套路径 (例如: "transcription.local.model")
            default: 默认值

        Returns:
            配置项的值，如果不存在则返回默认值
        """
        try:
            keys = key.split(".")
            value: Any = self._config

            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return cast(T, default)

            return cast(T, value)

        except Exception as e:
            app_logger.log_error(e, f"config_reader_get_{key}")
            return cast(T, default)

    def get_all_settings(self) -> Dict[str, Any]:
        """获取所有配置的副本

        Returns:
            配置字典的深拷贝
        """
        return copy.deepcopy(self._config)

    def _get_default_value(self, key: str) -> Any:
        """获取配置项的默认值

        Args:
            key: 配置项键名

        Returns:
            默认值，不存在返回None
        """
        try:
            keys = key.split(".")
            value = self._default_config

            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return None

            return copy.deepcopy(value)

        except Exception:
            return None

    def _merge_configs(
        self, default: Dict[str, Any], loaded: Dict[str, Any]
    ) -> Dict[str, Any]:
        """合并默认配置和加载的配置

        Args:
            default: 默认配置
            loaded: 加载的配置

        Returns:
            合并后的配置
        """
        result = copy.deepcopy(default)

        def merge_recursive(base: Dict[str, Any], update: Dict[str, Any]) -> None:
            for key, value in update.items():
                if (
                    key in base
                    and isinstance(base[key], dict)
                    and isinstance(value, dict)
                ):
                    merge_recursive(base[key], value)
                else:
                    base[key] = value

        merge_recursive(result, loaded)
        return result
