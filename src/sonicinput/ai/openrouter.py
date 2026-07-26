"""OpenRouter API客户端"""

from typing import Any, Dict, List

from ..utils import OpenRouterAPIError
from .base_client import BaseAIClient


class OpenRouterClient(BaseAIClient):
    """OpenRouter API 集成客户端

    使用 BaseAIClient 提供的通用功能，添加以下 OpenRouter 特有功能：
    - 自定义请求头（HTTP-Referer, X-Title）
    - 获取可用模型列表
    - 获取使用统计
    - 估算 API 调用成本
    """

    def get_base_url(self) -> str:
        """返回 OpenRouter API 端点"""
        return "https://openrouter.ai/api/v1"

    def get_provider_name(self) -> str:
        """返回提供商名称"""
        return "OpenRouter"

    def get_default_model(self) -> str:
        """返回默认模型"""
        return "anthropic/claude-3-sonnet"

    def _create_api_error(self, message: str) -> Exception:
        """创建 OpenRouter 特定的异常"""
        return OpenRouterAPIError(message)

    def get_extra_headers(self) -> Dict[str, str]:
        """返回 OpenRouter 特定的请求头"""
        return {
            "HTTP-Referer": "https://github.com/user/sonic-input",
            "X-Title": "Sonic Input",
        }

    # ========== OpenRouter 独特功能 ==========

    def get_available_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表

        Returns:
            适合文本优化的模型列表，包含模型 ID、名称、描述、定价等信息
        """
        try:
            response = self.session.get(
                f"{self.get_base_url()}/models", timeout=self.timeout
            )

            if response.status_code == 200:
                models_data = response.json()
                models = models_data.get("data", [])

                # 过滤适合文本优化的模型
                suitable_models = []
                for model in models:
                    model_id = model.get("id", "")
                    # 选择常用的高质量模型
                    if any(
                        provider in model_id.lower()
                        for provider in [
                            "anthropic",
                            "openai",
                            "google",
                            "meta-llama",
                            "mistralai",
                        ]
                    ):
                        suitable_models.append(
                            {
                                "id": model_id,
                                "name": model.get("name", model_id),
                                "description": model.get("description", ""),
                                "pricing": model.get("pricing", {}),
                                "context_length": model.get("context_length", 0),
                            }
                        )

                from ..utils import app_logger

                app_logger.log_api_call("OpenRouter", 0, True)
                return suitable_models
            else:
                from ..utils import app_logger

                app_logger.log_api_call("OpenRouter", 0, False, response.text)
                return []

        except Exception as e:
            from ..utils import app_logger

            app_logger.log_error(e, "get_available_models")
            return []
