"""OpenAI Compatible API客户端

支持任何兼容 OpenAI API 格式的服务:
- LM Studio
- Ollama
- vLLM
- text-generation-webui
- 以及其他自托管服务
"""

from typing import Any, Dict, List

from ..utils import app_logger
from ..utils.exceptions import OpenAICompatibleAPIError
from .base_client import BaseAIClient


class OpenAICompatibleClient(BaseAIClient):
    """OpenAI Compatible API 客户端

    使用 BaseAIClient 提供的通用功能，添加以下特性：
    - 支持自定义 base_url（本地服务）
    - API Key 可选（某些本地服务不需要）
    - 增强的 JSON 错误处理
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "http://localhost:1234/v1",
        timeout: int = 30,
        max_retries: int = 3,
        filter_thinking: bool = True,
    ):
        """初始化 OpenAI Compatible 客户端

        Args:
            api_key: API 密钥（可选，本地服务可能不需要）
            base_url: API 基础 URL（默认本地 LM Studio）
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            filter_thinking: 是否过滤 AI 思考标签
        """
        # 保存 base_url（移除末尾斜杠）
        self._base_url = base_url.rstrip("/")

        # 调用父类初始化
        super().__init__(api_key, timeout, max_retries, filter_thinking)

    def get_base_url(self) -> str:
        """返回配置的 base_url"""
        return self._base_url

    def get_provider_name(self) -> str:
        """返回提供商名称"""
        return "OpenAI Compatible"

    def get_default_model(self) -> str:
        """返回默认模型"""
        return "local-model"

    def _create_api_error(self, message: str) -> Exception:
        """创建 OpenAI Compatible 特定的异常"""
        return OpenAICompatibleAPIError(message)

    def get_available_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表。"""
        try:
            response = self.session.get(
                f"{self.get_base_url()}/models", timeout=self.timeout
            )

            if response.status_code != 200:
                app_logger.log_api_call("OpenAI Compatible", 0, False, response.text)
                return []

            payload = response.json()
            if isinstance(payload, dict):
                models = payload.get("data", [])
            elif isinstance(payload, list):
                models = payload
            else:
                models = []

            normalized_models: List[Dict[str, Any]] = []
            for model in models:
                if isinstance(model, dict):
                    model_id = str(model.get("id", "")).strip()
                    owned_by = model.get("owned_by", "")
                    created = model.get("created", 0)
                else:
                    model_id = str(model).strip()
                    owned_by = ""
                    created = 0

                if not model_id:
                    continue

                normalized_models.append(
                    {
                        "id": model_id,
                        "name": model_id,
                        "description": "",
                        "owned_by": owned_by,
                        "created": created,
                    }
                )

            normalized_models.sort(key=lambda item: item["id"].lower())
            app_logger.log_api_call("OpenAI Compatible", 0, True)
            return normalized_models
        except Exception as e:
            app_logger.log_error(e, "openai_compatible_get_available_models")
            return []

    def fetch_available_models(self) -> List[str]:
        """返回模型 ID 列表。"""
        models = self.get_available_models()
        return [model["id"] for model in models if model.get("id")]

    def _extract_response_text(self, result: Dict[str, Any]) -> str:
        """从 API 响应中提取文本（增强 JSON 错误处理）

        某些本地服务可能返回无效的 JSON，需要特殊处理。

        Args:
            result: API 响应的 JSON 对象

        Returns:
            提取的文本

        Raises:
            OpenAICompatibleAPIError: 如果响应格式无效
        """
        choices = result.get("choices", [])
        if not choices:
            raise self._create_api_error(
                "No choices returned in OpenAI Compatible response"
            )

        return choices[0].get("message", {}).get("content", "").strip()
