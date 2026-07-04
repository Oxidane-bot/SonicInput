"""AI服务

负责AI文本优化处理，支持配置热重载。
"""

from typing import List, Optional

from ...ai.factory import AIClientFactory
from ...utils import app_logger
from ..base.lifecycle_component import LifecycleComponent
from ..interfaces.ai import IAIService
from ..interfaces.config import IConfigService
# IConfigReloadable removed - using service rebuild pattern instead


class AIService(LifecycleComponent):  # type: ignore[metaclass]
    """AI服务（支持配置热重载）

    职责：
    - 管理AI客户端实例
    - 提供文本优化功能
    - 支持配置热重载（通过服务重建实现）
    - 处理提供商切换
    """

    def __init__(self, config_service: IConfigService):
        """初始化AI服务

        Args:
            config_service: 配置服务实例
        """
        super().__init__("AIService")

        # 保存配置服务引用
        self._config_service = config_service

        # AI客户端和配置
        self._client: Optional[IAIService] = None
        self._current_provider: str = ""

        # AI配置参数
        self._enabled: bool = True
        self._filter_thinking: bool = True
        self._prompt: str = ""
        self._timeout: int = 30
        self._retries: int = 3

        # 性能追踪
        self._last_tps: float = 0.0

    # ==================== LifecycleComponent Implementation ====================

    def _do_start(self) -> bool:
        """启动AI服务并初始化客户端

        Returns:
            是否启动成功
        """
        try:
            # 获取配置
            config = self._config_service.get_all_settings()
            ai_config = config.get("ai", {})

            # 加载配置参数
            self._enabled = ai_config.get("enabled", True)
            self._filter_thinking = ai_config.get("filter_thinking", True)
            self._prompt = ai_config.get("prompt", "")
            self._timeout = ai_config.get("timeout", 30)
            self._retries = ai_config.get("retries", 3)

            # 创建AI客户端
            if self._enabled and self._config_service:
                self._current_provider = ai_config.get("provider", "groq")
                self._client = AIClientFactory.create_from_config(self._config_service)

                if self._client:
                    app_logger.log_audio_event(
                        "AI client initialized", {"provider": self._current_provider}
                    )
                else:
                    app_logger.log_audio_event(
                        "AI client creation failed",
                        {"provider": self._current_provider},
                    )

            return True

        except Exception as e:
            app_logger.log_error(e, "AIService._do_start")
            return False

    def _do_stop(self) -> bool:
        """停止AI服务并清理资源

        Returns:
            是否停止成功
        """
        try:
            # 清理AI客户端
            self._client = None
            app_logger.log_audio_event("AI service stopped and cleaned up", {})
            return True

        except Exception as e:
            app_logger.log_error(e, "AIService._do_stop")
            return False

    # ==================== AI Service Methods ====================

    def refine_text(self, text: str, prompt_template: str, model: str) -> str:
        """优化文本

        Args:
            text: 要优化的文本
            prompt_template: 提示模板
            model: 使用的AI模型

        Returns:
            优化后的文本
        """
        if not self._enabled or not self._client:
            return text

        try:
            refined_text = self._client.refine_text(text, prompt_template, model)

            # 保存TPS（如果客户端提供）
            if hasattr(self._client, "_last_tps"):
                self._last_tps = self._client._last_tps

            return refined_text

        except Exception as e:
            app_logger.log_error(e, "AIService.refine_text")
            return text

    def is_enabled(self) -> bool:
        """检查AI是否启用

        Returns:
            是否启用
        """
        return self._enabled

    def get_current_provider(self) -> str:
        """获取当前提供商

        Returns:
            提供商名称
        """
        return self._current_provider

    @property
    def last_tps(self) -> float:
        """获取最后一次处理的TPS

        Returns:
            TPS值
        """
        return self._last_tps

    # ==================== IConfigReloadable Implementation ====================

    def get_config_dependencies(self) -> List[str]:
        """声明此服务依赖的配置键

        Returns:
            配置键列表
        """
        return [
            "ai.provider",
            "ai.enabled",
            "ai.filter_thinking",
            "ai.prompt",
            "ai.timeout",
            "ai.retries",
            "ai.groq.api_key",
            "ai.groq.model_id",
            "ai.nvidia.api_key",
            "ai.nvidia.model_id",
            "ai.openrouter.api_key",
            "ai.openrouter.model_id",
            "ai.openai_compatible.api_key",
            "ai.openai_compatible.base_url",
            "ai.openai_compatible.model_id",
        ]
