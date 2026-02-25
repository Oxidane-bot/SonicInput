"""NVIDIA API客户端"""

from typing import Any, Dict, List

from ..utils import app_logger
from ..utils.exceptions import NVIDIAAPIError
from .base_client import BaseAIClient


class NvidiaClient(BaseAIClient):
    """NVIDIA API 集成客户端 (NIM - NVIDIA Inference Microservices)

    使用 BaseAIClient 提供的通用功能，仅需实现提供商特定配置。
    """

    def get_base_url(self) -> str:
        """返回 NVIDIA API 端点"""
        return "https://integrate.api.nvidia.com/v1"

    def get_provider_name(self) -> str:
        """返回提供商名称"""
        return "NVIDIA"

    def get_default_model(self) -> str:
        """返回默认模型"""
        return "meta/llama-3.1-8b-instruct"

    def _create_api_error(self, message: str) -> Exception:
        """创建 NVIDIA 特定的异常"""
        return NVIDIAAPIError(message)

    def get_available_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表。

        NVIDIA 的 /v1/models 端点返回 OpenAI-compatible 模型对象列表。
        """
        try:
            response = self.session.get(
                f"{self.get_base_url()}/models", timeout=self.timeout
            )

            if response.status_code != 200:
                app_logger.log_api_call("NVIDIA", 0, False, response.text)
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
            app_logger.log_api_call("NVIDIA", 0, True)
            return normalized_models
        except Exception as e:
            app_logger.log_error(e, "nvidia_get_available_models")
            return []

    def fetch_available_models(self) -> List[str]:
        """返回模型 ID 列表。"""
        models = self.get_available_models()
        return [model["id"] for model in models if model.get("id")]
