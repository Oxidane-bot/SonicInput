"""数据存储接口定义"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Optional


class IStorageService(ABC):
    """存储服务接口

    提供数据持久化存储功能。
    """

    @abstractmethod
    def save(self, key: str, data: Any) -> bool:
        """保存数据

        Args:
            key: 数据键名
            data: 要保存的数据

        Returns:
            是否保存成功
        """
        pass

    @abstractmethod
    def load(self, key: str, default: Any = None) -> Any:
        """加载数据

        Args:
            key: 数据键名
            default: 默认值

        Returns:
            加载的数据，不存在时返回默认值
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除数据

        Args:
            key: 数据键名

        Returns:
            是否删除成功
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查数据是否存在

        Args:
            key: 数据键名

        Returns:
            数据是否存在
        """
        pass

    @abstractmethod
    def get_all_keys(self) -> List[str]:
        """获取所有数据键名

        Returns:
            键名列表
        """
        pass

    @abstractmethod
    def clear_all(self) -> bool:
        """清除所有数据

        Returns:
            是否清除成功
        """
        pass

    @abstractmethod
    def get_storage_path(self) -> Path:
        """获取存储路径

        Returns:
            存储目录路径
        """
        pass


class ICacheService(ABC):
    """缓存服务接口

    提供临时数据缓存功能。
    """

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存项

        Args:
            key: 缓存键名
            value: 缓存值
            ttl: 生存时间（秒），None表示永不过期
        """
        pass

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存项

        Args:
            key: 缓存键名
            default: 默认值

        Returns:
            缓存值，不存在或过期时返回默认值
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存项

        Args:
            key: 缓存键名

        Returns:
            是否删除成功
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查缓存项是否存在且未过期

        Args:
            key: 缓存键名

        Returns:
            缓存项是否存在且有效
        """
        pass

    @abstractmethod
    def clear(self) -> int:
        """清除所有缓存

        Returns:
            清除的缓存项数量
        """
        pass

    @abstractmethod
    def cleanup_expired(self) -> int:
        """清理过期缓存

        Returns:
            清理的过期缓存项数量
        """
        pass

    @property
    @abstractmethod
    def size(self) -> int:
        """缓存项数量"""
        pass
