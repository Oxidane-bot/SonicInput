"""内存缓存服务实现"""

import threading
import time
from typing import Any, Dict, Optional

from ..interfaces import ICacheService


class CacheEntry:
    """缓存条目，包含值和过期时间"""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: Optional[int] = None) -> None:
        self.value = value
        if ttl is None or ttl <= 0:
            self.expires_at: Optional[float] = None
        else:
            self.expires_at = time.time() + ttl


class InMemoryCacheService(ICacheService):
    """线程安全的内存缓存服务

    使用 dict 存储缓存项，每项包含过期时间。
    所有操作均线程安全（使用 RLock）。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            self._cache[key] = CacheEntry(value, ttl)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return default
            if entry.expires_at is not None and time.time() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return default
            self._hits += 1
            return entry.value

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.expires_at is not None and time.time() > entry.expires_at:
                del self._cache[key]
                return False
            return True

    def clear(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def cleanup_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired_keys = [
                key
                for key, entry in self._cache.items()
                if entry.expires_at is not None and now > entry.expires_at
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    def get_cache_info(self) -> Dict[str, Any]:
        with self._lock:
            self.cleanup_expired()
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
            }

    @property
    def size(self) -> int:
        with self._lock:
            self.cleanup_expired()
            return len(self._cache)
