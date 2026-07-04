"""配置服务接口定义"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class IConfigService(ABC):
    """配置服务接口"""

    @abstractmethod
    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        pass

    @abstractmethod
    def set_setting(self, key: str, value: Any) -> None:
        """设置配置项"""
        pass

    @abstractmethod
    def get_all_settings(self) -> Dict[str, Any]:
        """获取全部配置的副本"""
        pass

    @abstractmethod
    def save_config(self) -> bool:
        """保存配置,返回是否成功"""
        pass


__all__ = ["IConfigService"]
