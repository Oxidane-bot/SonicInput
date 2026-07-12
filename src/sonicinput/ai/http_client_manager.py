"""HTTP客户端管理器

负责管理HTTP连接池、session配置和请求处理。
从BaseAIClient中提取出来以提高代码的内聚性。
"""

from typing import Dict

import requests

from ..utils import app_logger


class HTTPClientManager:
    """HTTP客户端管理器

    负责：
    - HTTP连接池配置和管理
    - Session配置和生命周期
    - 请求发送和基础错误处理
    """

    def __init__(self, timeout: int = 30):
        """初始化HTTP客户端管理器

        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self.session = requests.Session()
        self._setup_connection_pool()

    def _setup_connection_pool(self) -> None:
        """配置连接池"""
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            # 配置重试策略
            retry_strategy = Retry(
                total=0,  # 我们在应用层处理重试
                backoff_factor=0,
                status_forcelist=[429, 502, 503, 504],
            )

            # 创建适配器
            adapter = HTTPAdapter(
                pool_connections=10,  # 连接池数量
                pool_maxsize=20,  # 每个连接池的最大连接数
                max_retries=retry_strategy,
            )

            # 应用到session
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)

            app_logger.log_audio_event("Connection pool configured successfully", {})

        except Exception as e:
            app_logger.log_error(e, "setup_connection_pool")
            # 继续使用默认配置

    def get_session(self) -> requests.Session:
        """获取HTTP session

        Returns:
            配置好的requests.Session实例
        """
        return self.session

    def update_session_config(self, **kwargs) -> None:
        """更新session配置

        Args:
            **kwargs: session配置参数
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self.session, key):
                    setattr(self.session, key, value)

            app_logger.log_audio_event(
                "Session config updated", {"config_keys": list(kwargs.keys())}
            )
        except Exception as e:
            app_logger.log_error(e, "update_session_config")

    def set_default_headers(self, headers: Dict[str, str]) -> None:
        """设置默认请求头

        Args:
            headers: 默认请求头字典
        """
        self.session.headers.update(headers)
        app_logger.log_audio_event(
            "Default headers set", {"header_count": len(headers)}
        )

    def close(self) -> None:
        """关闭HTTP客户端"""
        try:
            self.session.close()
            app_logger.log_audio_event("HTTP client closed", {})
        except Exception as e:
            app_logger.log_error(e, "close_http_client")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """上下文管理器出口"""
        self.close()
