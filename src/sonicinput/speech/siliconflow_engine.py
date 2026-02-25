"""硅基流动音频转录引擎 - 简化版本

基于 SiliconFlow API 的云端语音识别服务。
支持 SenseVoiceSmall 和 TeleSpeechASR 模型，具有超低延迟和方言识别能力。
"""

from typing import Any, Dict, List, Optional

from ..utils import app_logger
from .cloud_base import CloudTranscriptionBase


class SiliconFlowEngine(CloudTranscriptionBase):
    """硅基流动音频转录引擎 - 简化版本

    特性:
    - 超低延迟：70ms 响应时间
    - 方言支持：40+ 中文方言
    - 情感识别：内置情感检测功能
    - 零GPU依赖：纯云端服务
    """

    # Provider metadata
    provider_id = "siliconflow"
    display_name = "SiliconFlow"
    description = "Ultra-low latency cloud transcription with Chinese dialect support"
    api_endpoint = "https://api.siliconflow.cn/v1/audio/transcriptions"
    default_base_url = "https://api.siliconflow.cn/v1"

    # 支持的模型列表
    AVAILABLE_MODELS = [
        "FunAudioLLM/SenseVoiceSmall",  # 50+语言，超低延迟
        "TeleAI/TeleSpeechASR",  # 40种中文方言+英语
    ]

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "FunAudioLLM/SenseVoiceSmall",
        base_url: Optional[str] = None,
        config_service=None,
    ):
        """初始化硅基流动引擎

        Args:
            api_key: 硅基流动API密钥 (default: empty, must be set via initialize)
            model_name: 模型名称，默认使用 SenseVoiceSmall
            base_url: 可选的自定义API端点
            config_service: 可选的配置服务，用于流式分块时长
        """
        super().__init__(api_key, config_service)
        self.model_name = model_name
        self.base_url = base_url if base_url else self.default_base_url
        self._available_models = self.AVAILABLE_MODELS.copy()

        # Keep model configurable even when provider adds new IDs before local defaults update
        if model_name and model_name not in self._available_models:
            app_logger.log_audio_event(
                "SiliconFlow model is not in built-in defaults",
                {
                    "requested_model": model_name,
                    "defaults": self._available_models,
                },
            )
            self._available_models.append(model_name)
        elif not model_name:
            self.model_name = self.AVAILABLE_MODELS[0]

    def prepare_request_data(self, **kwargs) -> Dict[str, Any]:
        """准备硅基流动特有的请求数据

        Args:
            **kwargs: 转录参数

        Returns:
            硅基流动API请求参数
        """
        request_data = {"model": self.model_name}

        # 添加语言参数（如果指定）
        language = kwargs.get("language")
        if language and language != "auto":
            request_data["language"] = language

        return request_data

    def parse_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """解析硅基流动API响应为标准格式

        Args:
            response_data: 原始API响应数据

        Returns:
            标准转录结果格式
        """
        text = response_data.get("text", "").strip()
        language = response_data.get("language", "auto")

        # 硅基流动响应格式比较简单，不包含详细的segments
        # 设置默认置信度
        confidence = 0.9  # 硅基流动质量较高，给予较高默认置信度

        return {
            "text": text,
            "language": language,
            "confidence": confidence,
            "segments": [],  # 硅基流动不提供详细segments
        }

    def get_auth_headers(self) -> Dict[str, str]:
        """获取硅基流动特有的认证头

        Returns:
            认证头字典
        """
        return {"Authorization": f"Bearer {self.api_key}"}

    def _models_endpoint(self) -> str:
        """构建模型列表接口地址。"""
        return f"{self.base_url.rstrip('/')}/models"

    def fetch_available_models(self, timeout: int = 10) -> List[str]:
        """从 SiliconFlow 平台拉取可用语音识别模型列表。

        Args:
            timeout: HTTP 请求超时时间（秒）

        Returns:
            更新后的模型 ID 列表；如果接口无语音模型返回，则回退到内存默认列表。

        Raises:
            RuntimeError: 拉取或解析失败
        """
        session = self._get_session()
        try:
            response = session.get(
                self._models_endpoint(),
                params={"type": "audio", "sub_type": "speech-to-text"},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch SiliconFlow models: {e}") from e

        data = payload.get("data", [])
        if not isinstance(data, list):
            raise RuntimeError("Unexpected SiliconFlow models response format")

        model_ids = []
        for item in data:
            if isinstance(item, dict):
                model_id = item.get("id")
                if isinstance(model_id, str) and model_id.strip():
                    model_ids.append(model_id.strip())

        models = sorted(set(model_ids))
        if models:
            self._available_models = models
            app_logger.log_audio_event(
                "SiliconFlow models refreshed",
                {"count": len(models), "models": models},
            )
            return models

        app_logger.log_audio_event(
            "SiliconFlow models refresh returned empty list, using fallback defaults",
            {"fallback": self._available_models},
        )
        return self._available_models.copy()

    def load_model(self, model_name: Optional[str] = None) -> bool:
        """加载模型（云端服务，标记为已加载即可）

        Args:
            model_name: 模型名称，None表示使用当前模型

        Returns:
            是否加载成功
        """
        if model_name:
            if model_name not in self._available_models:
                app_logger.log_audio_event(
                    "SiliconFlow model requested outside current model list",
                    {
                        "requested_model": model_name,
                        "available_models": self._available_models,
                    },
                )
                self._available_models.append(model_name)
            self.model_name = model_name

        # 云端服务无需预加载，API 会在首次转录时验证
        self._is_model_loaded = True
        app_logger.log_audio_event(
            "SiliconFlow model marked as loaded",
            {"model": self.model_name, "provider": "siliconflow"},
        )
        return True

    def get_available_models(self) -> List[str]:
        """获取可用的模型列表

        Returns:
            模型名称列表
        """
        return self._available_models.copy()

    def test_connection(self) -> Dict[str, Any]:
        """测试API连接

        Returns:
            连接测试结果
        """
        result = super().test_connection()
        result.update(
            {
                "details": {
                    "model": self.model_name,
                    "base_url": self.base_url,
                    "endpoint": self.api_endpoint,
                }
            }
        )
        return result

    def initialize(self, config: Dict[str, Any]) -> None:
        """使用配置初始化硅基流动引擎

        Args:
            config: 配置字典

        Raises:
            ValueError: 无效配置
            RuntimeError: 初始化失败
        """
        # 提取配置
        self.api_key = config.get("api_key", "")
        model_name = config.get("model_name", "FunAudioLLM/SenseVoiceSmall")
        self.base_url = config.get("base_url", self.default_base_url)

        # 验证API密钥
        if not self.api_key or self.api_key.strip() == "":
            raise ValueError("SiliconFlow API key is required")

        if not model_name:
            raise ValueError("SiliconFlow model is required")

        self.model_name = model_name
        if model_name not in self._available_models:
            self._available_models.append(model_name)

        # 标记为已加载
        self._is_model_loaded = True

        app_logger.log_model_loading_step(
            "SiliconFlow provider initialized",
            {"model": self.model_name, "base_url": self.base_url},
        )
