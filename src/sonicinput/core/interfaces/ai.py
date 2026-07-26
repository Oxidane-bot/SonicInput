"""AI服务接口定义"""

import collections.abc
from abc import ABC, abstractmethod


class IAIService(ABC):
    """AI服务接口

    提供文本优化和AI处理功能。
    """

    @abstractmethod
    def refine_text(self, text: str, prompt_template: str, model: str) -> str:
        """优化文本

        Args:
            text: 要优化的文本
            prompt_template: 提示模板
            model: 使用的AI模型

        Returns:
            优化后的文本

        Raises:
            AIServiceError: AI服务调用失败时
        """
        pass

    def refine_text_streaming(
        self,
        text: str,
        prompt_template: str,
        model: str,
        on_token: "collections.abc.Callable[[str], None]",
    ) -> str:
        """流式优化文本（token 级实时输出）

        默认实现退化为普通 refine_text，子类可覆盖以提供真正的流式输出。

        Args:
            text: 要优化的文本
            prompt_template: 提示模板
            model: 使用的AI模型
            on_token: 每个 token 到达时的回调，参数为 token 字符串

        Returns:
            完整的优化后文本
        """
        # 默认实现：不支持流式，退化为普通调用
        result = self.refine_text(text, prompt_template, model)
        for token in result:
            on_token(token)
        return result

    # 移除的方法（不必需）：
    # - get_available_models: 在实际使用中不需要获取模型列表
    # - validate_api_key: API密钥验证可在内部处理
    # - get_model_info: 模型信息在实际使用中不需要
    # - test_connection: 连接测试可在内部处理
    # - api_key_configured: 可通过其他方式检查
    # - service_status: 状态信息可在异常中提供
