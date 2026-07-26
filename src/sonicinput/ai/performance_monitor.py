"""AI性能监控器

负责监控API请求的性能指标，包括TPS计算、响应时间统计等。
从BaseAIClient中提取出来以提高代码的内聚性。
"""

import time
from typing import Any, Dict

from ..utils import app_logger


class AIPerformanceMonitor:
    """AI性能监控器

    负责：
    - TPS（每秒令牌数）计算
    - 响应时间统计
    - 请求性能历史记录
    - 性能指标分析
    """

    def __init__(self):
        """初始化性能监控器"""
        self._last_tps = 0.0
        self._request_history = []
        self._max_history_size = 100

    def record_request(self, duration: float, tokens: int) -> None:
        """记录一次请求的性能数据

        Args:
            duration: 请求响应时间（秒）
            tokens: 处理的令牌数量
        """
        try:
            if duration > 0 and tokens > 0:
                tps = tokens / duration
                self._last_tps = tps

                # 记录到历史中
                self._request_history.append(
                    {
                        "duration": duration,
                        "tokens": tokens,
                        "tps": tps,
                        "timestamp": time.time(),
                    }
                )

                # 限制历史记录大小
                if len(self._request_history) > self._max_history_size:
                    self._request_history.pop(0)

                app_logger.log_audio_event(
                    "Request performance recorded",
                    {"duration": duration, "tokens": tokens, "tps": tps},
                )
        except Exception as e:
            app_logger.log_error(e, "record_request_performance")

    def extract_token_stats(
        self, result: Dict[str, Any], response_time: float
    ) -> Dict[str, Any]:
        """提取 token 使用统计

        Args:
            result: API 响应的 JSON 对象
            response_time: 响应时间（秒）

        Returns:
            包含 token 统计的字典
        """
        try:
            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            # 改进的TPS计算 - 包含prompt和completion处理时间
            if response_time > 0:
                # 计算综合TPS（包含prompt + completion）
                total_tokens_processed = prompt_tokens + completion_tokens
                if total_tokens_processed > 0:
                    self._last_tps = total_tokens_processed / response_time
                else:
                    self._last_tps = 0.0

                # 分别计算prompt和completion的TPS
                prompt_tps = prompt_tokens / response_time if prompt_tokens > 0 else 0.0
                completion_tps = (
                    completion_tokens / response_time if completion_tokens > 0 else 0.0
                )
            else:
                self._last_tps = 0.0
                prompt_tps = 0.0
                completion_tps = 0.0

            # 记录性能数据
            self.record_request(response_time, total_tokens)

            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "tps": self._last_tps,
                "prompt_tps": prompt_tps,
                "completion_tps": completion_tps,
                "response_time": response_time,
            }
        except Exception as e:
            app_logger.log_error(e, "extract_token_stats")
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "tps": 0.0,
                "prompt_tps": 0.0,
                "completion_tps": 0.0,
                "response_time": response_time,
            }

    def get_tps(self) -> float:
        """获取最新的TPS值

        Returns:
            最新的每秒令牌数
        """
        return self._last_tps

    def reset_stats(self) -> None:
        """重置性能统计"""
        self._last_tps = 0.0
        self._request_history.clear()
        app_logger.log_audio_event("Performance stats reset", {})
