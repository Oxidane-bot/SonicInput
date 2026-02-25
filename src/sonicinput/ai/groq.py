"""Groq API客户端"""

from typing import Any, Dict, List

from ..utils import app_logger
from ..utils.exceptions import GroqAPIError
from .base_client import BaseAIClient


class GroqClient(BaseAIClient):
    """Groq API 集成客户端

    使用 BaseAIClient 提供的通用功能，仅需实现提供商特定配置。
    """

    def get_base_url(self) -> str:
        """返回 Groq API 端点"""
        return "https://api.groq.com/openai/v1"

    def get_provider_name(self) -> str:
        """返回提供商名称"""
        return "Groq"

    def get_default_model(self) -> str:
        """返回默认模型

        Note: llama3-8b-8192 已被淘汰（2024年已下线）
        推荐使用 llama-3.3-70b-versatile 或其他当前可用模型
        参考: https://console.groq.com/docs/deprecations
        """
        return "llama-3.3-70b-versatile"

    def _create_api_error(self, message: str) -> Exception:
        """创建 Groq 特定的异常"""
        return GroqAPIError(message)

    def get_available_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表。"""
        try:
            response = self.session.get(
                f"{self.get_base_url()}/models", timeout=self.timeout
            )

            if response.status_code != 200:
                app_logger.log_api_call("Groq", 0, False, response.text)
                return []

            payload = response.json()
            models = payload.get("data", [])

            normalized_models: List[Dict[str, Any]] = []
            for model in models:
                model_id = str(model.get("id", "")).strip()
                if not model_id:
                    continue

                normalized_models.append(
                    {
                        "id": model_id,
                        "name": model_id,
                        "description": "",
                        "owned_by": model.get("owned_by", ""),
                        "created": model.get("created", 0),
                    }
                )

            normalized_models.sort(key=lambda item: item["id"].lower())
            app_logger.log_api_call("Groq", 0, True)
            return normalized_models
        except Exception as e:
            app_logger.log_error(e, "groq_get_available_models")
            return []

    def fetch_available_models(self) -> List[str]:
        """返回模型 ID 列表。"""
        models = self.get_available_models()
        return [model["id"] for model in models if model.get("id")]
