"""AI客户端抽象基类

提供 OpenAI-compatible API 的通用实现，消除重复代码。
所有 AI 提供商客户端应继承此基类。
"""

import re
import time
from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple

import requests

from ..core.interfaces import IAIService
from ..utils import AIOutputTruncatedError, app_logger
from .http_client_manager import HTTPClientManager
from .performance_monitor import AIPerformanceMonitor


class BaseAIClient(IAIService):
    """AI 客户端抽象基类

    提供 OpenAI-compatible API 的通用功能：
    - 统一的初始化和配置管理
    - 通用的 HTTP 请求处理
    - 标准化的重试逻辑
    - 统一的 token 统计和 TPS 计算
    - 标准化的错误处理

    子类只需实现 4 个抽象方法即可完成集成：
    - get_base_url() - API 端点
    - get_provider_name() - 提供商名称
    - get_default_model() - 默认模型
    - _create_api_error() - 提供商特定异常
    """

    # ========== 抽象方法（子类必须实现）==========

    @abstractmethod
    def get_base_url(self) -> str:
        """返回 API 基础 URL

        示例:
        - OpenRouter: "https://openrouter.ai/api/v1"
        - Groq: "https://api.groq.com/openai/v1"
        - NVIDIA: "https://integrate.api.nvidia.com/v1"
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """返回提供商名称（用于日志）

        示例: "OpenRouter", "Groq", "NVIDIA", "OpenAI Compatible"
        """
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """返回默认模型

        示例:
        - OpenRouter: "anthropic/claude-3-sonnet"
        - Groq: "llama3-8b-8192"
        - NVIDIA: "meta/llama-3.1-8b-instruct"
        """
        pass

    @abstractmethod
    def _create_api_error(self, message: str) -> Exception:
        """创建提供商特定的异常

        Args:
            message: 错误消息

        Returns:
            提供商特定的异常实例（如 GroqAPIError, NVIDIAAPIError）
        """
        pass

    # ========== 可选覆盖的方法（提供默认实现）==========

    def get_extra_headers(self) -> Dict[str, str]:
        """返回额外的 HTTP 请求头

        子类可以覆盖此方法添加特殊请求头。
        例如 OpenRouter 需要 HTTP-Referer 和 X-Title。

        Returns:
            额外的请求头字典
        """
        return {}

    def _handle_http_error(
        self, status_code: int, response_text: str, attempt: int, response_time: float
    ) -> Optional[str]:
        """处理特定 HTTP 错误

        子类可以覆盖此方法处理提供商特定的 HTTP 错误码。

        Args:
            status_code: HTTP 状态码
            response_text: 响应文本
            attempt: 当前重试次数
            response_time: 响应时间

        Returns:
            错误消息字符串（如果需要抛出异常）
            None（如果错误已处理，允许重试）
        """
        # 默认处理通用错误
        if status_code == 400:  # Bad request
            return f"Bad request: {response_text}"
        elif status_code == 401:  # Unauthorized
            return f"Invalid API key for {self.get_provider_name()}"
        elif status_code == 402:  # Payment required
            return "Insufficient credits"
        else:
            return f"HTTP {status_code}: {response_text}"

    def _extract_response_text(self, result: Dict[str, Any]) -> str:
        """从 API 响应中提取文本

        子类可以覆盖此方法处理特殊的响应格式。
        例如 OpenAICompatibleClient 需要额外的 JSON 错误处理。

        Args:
            result: API 响应的 JSON 对象

        Returns:
            提取的文本

        Raises:
            Exception: 如果响应格式无效
        """
        choices = result.get("choices", [])
        if not choices:
            raise self._create_api_error("No choices returned in response")

        return choices[0].get("message", {}).get("content", "").strip()

    def _extract_finish_reason(self, result: Dict[str, Any]) -> Optional[str]:
        choices = result.get("choices", [])
        if not choices:
            raise self._create_api_error("No choices returned in response")
        reason = choices[0].get("finish_reason")
        return str(reason) if reason is not None else None

    def _raise_if_output_truncated(
        self,
        finish_reason: Optional[str],
        *,
        max_tokens: int,
        response_length: int,
    ) -> None:
        if finish_reason != "length":
            return
        raise AIOutputTruncatedError(
            "AI output reached max_tokens before completion",
            context={
                "provider": self.get_provider_name(),
                "finish_reason": finish_reason,
                "max_tokens": max_tokens,
                "response_length": response_length,
            },
        )

    def _filter_thinking_tags(self, text: str) -> str:
        """过滤 AI 思考标签 (<think>...</think>)

        移除文本中所有的 <think>...</think> 标签及其内容。
        这些标签通常包含 AI 模型的内部思考过程，不应该显示给用户。

        Args:
            text: 包含思考标签的原始文本

        Returns:
            过滤后的文本

        Examples:
            >>> self._filter_thinking_tags("Hello <think>thinking...</think> world")
            "Hello world"
            >>> self._filter_thinking_tags("<think>思考中</think>结果文本")
            "结果文本"
        """
        if not text:
            return text

        # 使用正则表达式移除 <think>...</think> 标签
        # re.DOTALL 使 . 匹配包括换行符在内的所有字符
        # 非贪婪匹配 .*? 确保正确处理多个标签
        filtered_text = re.sub(
            r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE
        )

        # 清理多余的空白字符
        filtered_text = filtered_text.strip()

        # 如果过滤后文本为空，记录警告
        if not filtered_text and text:
            app_logger.log_audio_event(
                "AI response was only thinking tags",
                {"original_length": len(text), "provider": self.get_provider_name()},
            )

        return filtered_text

    # ========== 通用实现（所有子类共享）==========

    def __init__(
        self,
        api_key: str = "",
        timeout: int = 30,
        max_retries: int = 3,
        filter_thinking: bool = True,
    ):
        """初始化 AI 客户端

        Args:
            api_key: API 密钥
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            filter_thinking: 是否过滤 AI 思考标签 (<think>...</think>)
        """
        self._raw_api_key = api_key

        # 使用新的HTTP客户端管理器
        self._http_client = HTTPClientManager(timeout)
        self.session = self._http_client.get_session()

        # 使用新的性能监控器
        self._performance_monitor = AIPerformanceMonitor()

        # 请求配置
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = 1.0  # 初始重试延迟（指数退避）
        self.filter_thinking = filter_thinking

        # 设置请求头
        self._update_headers()

        app_logger.log_audio_event(
            f"{self.get_provider_name()} client initialized",
            {
                "has_api_key": bool(api_key),
                "api_key_length": len(api_key) if api_key else 0,
                "base_url": self.get_base_url(),
            },
        )

    def health_check(self) -> Dict[str, Any]:
        """服务健康检查"""
        try:
            start_time = time.time()
            # 尝试访问提供商的健康检查端点（如果有的话）
            health_url = f"{self.get_base_url()}/health"

            response = self.session.get(
                health_url,
                timeout=5,  # 短超时用于健康检查
                headers=self.session.headers,
            )
            response_time = time.time() - start_time

            return {
                "healthy": response.status_code == 200,
                "response_time": response_time,
                "status_code": response.status_code,
                "provider": self.get_provider_name(),
                "base_url": self.get_base_url(),
            }

        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "response_time": 0,
                "provider": self.get_provider_name(),
                "base_url": self.get_base_url(),
            }

    def _get_secure_api_key(self) -> str:
        """获取安全的API密钥（用于日志和调试）"""
        if not self._raw_api_key:
            return ""

        # 返回密钥的掩码版本用于日志
        if len(self._raw_api_key) <= 8:
            return "*" * len(self._raw_api_key)
        else:
            return (
                self._raw_api_key[:4]
                + "*" * (len(self._raw_api_key) - 8)
                + self._raw_api_key[-4:]
            )

    @property
    def api_key(self) -> str:
        """获取API密钥（兼容性属性）"""
        return self._raw_api_key

    @property
    def _last_tps(self) -> float:
        """获取最新的TPS值（用于向后兼容）

        Returns:
            最新的tokens per second值，如果没有则返回0.0
        """
        return self._performance_monitor.get_tps()

    def _update_headers(self) -> None:
        """更新 HTTP 请求头"""
        headers = {
            "Content-Type": "application/json",
        }

        # API Key（可选）
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # 子类提供的额外请求头
        headers.update(self.get_extra_headers())

        self.session.headers.update(headers)

    def set_api_key(self, api_key: str) -> None:
        """设置 API 密钥

        Args:
            api_key: 新的 API 密钥
        """
        self._raw_api_key = api_key
        self._update_headers()
        app_logger.log_audio_event(
            f"API key updated for {self.get_provider_name()}",
            {"has_key": bool(api_key)},
        )

    def _prepare_messages(self, text: str, prompt_template: str) -> Tuple[str, str]:
        """准备聊天消息

        支持两种格式：
        1. 旧格式: prompt_template 包含 {text}，所有内容放在 user message
        2. 新格式: prompt_template 作为 system message，text 作为 user message

        Args:
            text: 用户文本
            prompt_template: 提示模板

        Returns:
            (system_message, user_message) 元组
        """
        if "{text}" in prompt_template:
            # 旧格式：向后兼容
            system_message = "You are a professional text refinement assistant."
            user_message = prompt_template.format(text=text)
        else:
            # 新格式
            system_message = prompt_template
            user_message = text

        return system_message, user_message

    def _build_request_data(
        self, text: str, prompt_template: str, model: str, max_tokens: int
    ) -> Dict[str, Any]:
        """构建 API 请求数据

        Args:
            text: 用户文本
            prompt_template: 提示模板
            model: 模型 ID
            max_tokens: 最大 token 数

        Returns:
            请求数据字典
        """
        system_message, user_message = self._prepare_messages(text, prompt_template)

        return {
            "model": model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "top_p": 0.9,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "stream": False,
        }

    def _extract_token_stats(
        self, result: Dict[str, Any], response_time: float
    ) -> Dict[str, Any]:
        """提取 token 使用统计

        Args:
            result: API 响应的 JSON 对象
            response_time: 响应时间（秒）

        Returns:
            包含 token 统计的字典
        """
        # 使用性能监控器处理token统计
        return self._performance_monitor.extract_token_stats(result, response_time)

    def _handle_rate_limit(self, attempt: int, response_time: float) -> bool:
        """处理速率限制 - 智能重试机制

        Args:
            attempt: 当前重试次数
            response_time: 响应时间

        Returns:
            True 如果应该重试，False 如果应该放弃
        """
        provider = self.get_provider_name()
        app_logger.log_api_call(
            provider, response_time, False, f"Rate limit (attempt {attempt + 1})"
        )

        if attempt < self.max_retries - 1:
            wait_time = min(self.retry_delay * (2**attempt), 60.0)

            # 如果等待时间过长，提前放弃
            if wait_time > 30.0:
                app_logger.warning(
                    f"Excessive wait time for {provider}, giving up",
                    context={"wait_time": wait_time, "attempt": attempt + 1},
                )
                raise self._create_api_error(
                    f"Excessive wait time for rate limit with {provider}"
                )

            app_logger.log_audio_event(
                f"{provider} rate limit, retrying {attempt + 2}/{self.max_retries}",
                {"wait_time": wait_time, "status_code": 429, "max_wait_allowed": 60.0},
            )
            time.sleep(wait_time)
            return True
        else:
            raise self._create_api_error(
                f"Rate limit after all retries with {provider}"
            )

    def _handle_timeout(self, attempt: int) -> bool:
        """处理超时错误 - 增强超时处理

        Args:
            attempt: 当前重试次数

        Returns:
            True 如果应该重试，False 如果应该放弃
        """
        provider = self.get_provider_name()
        error_msg = f"Request timeout (attempt {attempt + 1})"
        app_logger.log_api_call(provider, self.timeout, False, error_msg)

        if attempt < self.max_retries - 1:
            wait_time = min(self.retry_delay * (1.5**attempt), 10.0)

            app_logger.log_audio_event(
                f"{provider} timeout, retrying {attempt + 2}/{self.max_retries}",
                {
                    "wait_time": wait_time,
                    "error": "Request timeout",
                    "timeout_setting": self.timeout,
                },
            )
            time.sleep(wait_time)
            return True
        else:
            raise self._create_api_error(
                f"Request timeout after all retries with {provider}"
            )

    def _handle_network_error(self, error: Exception, attempt: int) -> bool:
        """处理网络错误

        Args:
            error: 网络异常
            attempt: 当前重试次数

        Returns:
            True 如果应该重试，False 如果应该放弃
        """
        provider = self.get_provider_name()
        error_msg = f"{type(error).__name__}: {str(error)}"
        app_logger.log_api_call(
            provider, 0, False, f"Network error (attempt {attempt + 1}): {error_msg}"
        )

        if attempt < self.max_retries - 1:
            wait_time = min(self.retry_delay * (2**attempt), 60.0)
            app_logger.log_audio_event(
                f"{provider} network error, retrying {attempt + 2}/{self.max_retries}",
                {"wait_time": wait_time, "error": error_msg},
            )
            time.sleep(wait_time)
            return True
        else:
            raise self._create_api_error(
                f"Network error after all retries with {provider}: {error_msg}"
            )

    def refine_text(
        self,
        text: str,
        prompt_template: str,
        model: Optional[str] = None,
        max_tokens: int = 1000,
    ) -> str:
        """使用 AI 优化文本

        Args:
            text: 原始文本
            prompt_template: 提示模板
            model: 模型 ID（None 则使用默认模型）
            max_tokens: 最大生成 token 数

        Returns:
            优化后的文本

        Raises:
            提供商特定的 API 错误
        """
        # 验证 API key（修复：正确捕获 None 和空字符串）
        if not self.api_key or not self.api_key.strip():
            raise self._create_api_error(
                f"API key not set for {self.get_provider_name()}"
            )

        if not text.strip():
            return text

        # 使用默认模型
        if model is None:
            model = self.get_default_model()

        provider = self.get_provider_name()

        # 重试循环
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()

                # 构建请求
                request_data = self._build_request_data(
                    text, prompt_template, model, max_tokens
                )

                # 发送请求
                response = self.session.post(
                    f"{self.get_base_url()}/chat/completions",
                    json=request_data,
                    timeout=self.timeout,
                )

                response_time = time.time() - start_time

                # 处理成功响应
                if response.status_code == 200:
                    result = response.json()

                    # 提取文本
                    refined_text = self._extract_response_text(result)
                    finish_reason = self._extract_finish_reason(result)

                    # 过滤思考标签（如果启用）
                    if self.filter_thinking:
                        original_length = len(refined_text)
                        refined_text = self._filter_thinking_tags(refined_text)

                        # 记录过滤信息（如果有内容被过滤）
                        if len(refined_text) < original_length:
                            app_logger.log_audio_event(
                                "Thinking tags filtered",
                                {
                                    "original_length": original_length,
                                    "filtered_length": len(refined_text),
                                    "removed_chars": original_length
                                    - len(refined_text),
                                },
                            )

                    self._raise_if_output_truncated(
                        finish_reason,
                        max_tokens=max_tokens,
                        response_length=len(refined_text),
                    )

                    # 提取 token 统计
                    token_stats = self._extract_token_stats(result, response_time)

                    # 记录成功
                    app_logger.log_api_call(
                        provider,
                        response_time,
                        True,
                        prompt_tokens=token_stats["prompt_tokens"],
                        completion_tokens=token_stats["completion_tokens"],
                        total_tokens=token_stats["total_tokens"],
                    )

                    app_logger.log_audio_event(
                        f"Text refined by {provider}",
                        {
                            "model": model,
                            "original_length": len(text),
                            "refined_length": len(refined_text),
                            "response_time": response_time,
                            "attempt": attempt + 1,
                            "filter_thinking_enabled": self.filter_thinking,
                            "finish_reason": finish_reason,
                            "max_tokens": max_tokens,
                            **token_stats,
                        },
                    )

                    return refined_text

                # 处理速率限制
                elif response.status_code == 429:
                    if self._handle_rate_limit(attempt, response_time):
                        continue

                # 处理其他 HTTP 错误
                else:
                    error_msg = self._handle_http_error(
                        response.status_code, response.text, attempt, response_time
                    )

                    if error_msg:
                        app_logger.log_api_call(
                            provider,
                            response_time,
                            False,
                            f"API error (attempt {attempt + 1}): {error_msg}",
                        )

                        if attempt < self.max_retries - 1:
                            wait_time = self.retry_delay * (2**attempt)
                            app_logger.log_audio_event(
                                f"{provider} API error, retrying {attempt + 2}/{self.max_retries}",
                                {
                                    "wait_time": wait_time,
                                    "status_code": response.status_code,
                                    "error": error_msg[:200],
                                },
                            )
                            time.sleep(wait_time)
                            continue
                        else:
                            raise self._create_api_error(
                                f"HTTP error after all retries with {provider}: {error_msg}"
                            )

            except requests.exceptions.Timeout:
                if self._handle_timeout(attempt):
                    continue

            except requests.exceptions.RequestException as e:
                if self._handle_network_error(e, attempt):
                    continue

        # 所有重试失败
        app_logger.log_error(
            self._create_api_error(f"All retry attempts failed with {provider}"),
            "refine_text",
        )
        return text

    def refine_text_streaming(
        self,
        text: str,
        prompt_template: str,
        model: Optional[str] = None,
        on_token: Any = None,
        max_tokens: int = 1000,
    ) -> str:
        """使用 AI 流式优化文本（token 级实时输出）

        Args:
            text: 原始文本
            prompt_template: 提示模板
            model: 模型 ID（None 则使用默认模型）
            on_token: 每个 token 到达时的回调，签名为 (token: str) -> None
            max_tokens: 最大生成 token 数

        Returns:
            完整的优化后文本

        Raises:
            提供商特定的 API 错误
        """
        if on_token is None:
            return self.refine_text(text, prompt_template, model, max_tokens)

        if not self.api_key or not self.api_key.strip():
            raise self._create_api_error(
                f"API key not set for {self.get_provider_name()}"
            )

        if not text.strip():
            return text

        if model is None:
            model = self.get_default_model()

        provider = self.get_provider_name()

        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                request_data = self._build_request_data(
                    text, prompt_template, model, max_tokens
                )
                request_data["stream"] = True

                response = self.session.post(
                    f"{self.get_base_url()}/chat/completions",
                    json=request_data,
                    timeout=self.timeout,
                    stream=True,
                )

                response_time = time.time() - start_time

                if response.status_code != 200:
                    if response.status_code == 429:
                        if self._handle_rate_limit(attempt, response_time):
                            continue
                    error_msg = self._handle_http_error(
                        response.status_code, response.text, attempt, response_time
                    )
                    if error_msg and attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (2**attempt)
                        time.sleep(wait_time)
                        continue
                    raise self._create_api_error(
                        f"HTTP {response.status_code}: {error_msg}"
                    )

                # 解析 SSE 流
                full_text_parts: list[str] = []
                token_count = 0
                finish_reason: Optional[str] = None

                for line in response.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if not line_str.startswith("data: "):
                        continue
                    data_str = line_str[6:]  # strip "data: "
                    if data_str == "[DONE]":
                        break
                    try:
                        import json as _json

                        chunk = _json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        reason = choices[0].get("finish_reason")
                        if reason is not None:
                            finish_reason = str(reason)
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text_parts.append(content)
                            token_count += 1
                            try:
                                on_token(content)
                            except Exception:
                                pass  # 回调异常不中断流程
                    except Exception:
                        continue

                refined_text = "".join(full_text_parts)

                # 过滤思考标签（如果启用）
                if self.filter_thinking and refined_text:
                    refined_text = self._filter_thinking_tags(refined_text)

                self._raise_if_output_truncated(
                    finish_reason,
                    max_tokens=max_tokens,
                    response_length=len(refined_text),
                )

                total_time = time.time() - start_time
                tps = token_count / total_time if total_time > 0 else 0.0

                app_logger.log_api_call(
                    provider,
                    total_time,
                    True,
                    prompt_tokens=0,
                    completion_tokens=token_count,
                    total_tokens=token_count,
                )
                app_logger.log_audio_event(
                    f"Text refined by {provider} (streaming)",
                    {
                        "model": model,
                        "original_length": len(text),
                        "refined_length": len(refined_text),
                        "token_count": token_count,
                        "finish_reason": finish_reason,
                        "max_tokens": max_tokens,
                        "tps": round(tps, 2),
                        "total_time": round(total_time, 3),
                    },
                )

                return refined_text

            except requests.exceptions.Timeout:
                if self._handle_timeout(attempt):
                    continue
            except requests.exceptions.RequestException:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2**attempt))
                    continue
                raise

        return text

    def test_connection(self, model: Optional[str] = None) -> tuple[bool, str]:
        """测试 API 连接（使用 refine_text 复用完整的错误处理逻辑）

        Args:
            model: 模型 ID（None 则使用默认模型）

        Returns:
            (success, error_message): 成功返回 (True, "")，失败返回 (False, 详细错误信息)
        """
        provider = self.get_provider_name()

        # API key 验证
        if not self.api_key or not self.api_key.strip():
            error_msg = f"API key not set for {provider}"
            app_logger.log_error(self._create_api_error(error_msg), "test_connection")
            return False, error_msg

        try:
            # 使用 refine_text 进行测试，复用其完整的重试和错误处理逻辑
            # 使用最简单的提示，减少 token 消耗
            test_text = "test"
            prompt = "Return the word 'ok' only."

            # 确定使用的模型
            test_model = model if model else self.get_default_model()

            app_logger.log_audio_event(
                f"Testing {provider} connection",
                {"method": "refine_text", "model": test_model, "max_tokens": 5},
            )

            result = self.refine_text(
                text=test_text,
                prompt_template=prompt,
                model=model,  # 传递用户指定的模型或None（让refine_text处理fallback）
                max_tokens=5,  # 最小 token 数
            )

            # refine_text 成功返回意味着连接正常
            # 它有完整的重试逻辑，如果失败会 fallback 到原文
            if result and result != test_text:
                # API 返回了不同的文本，说明成功
                return True, ""
            elif result == test_text:
                # fallback 到原文，说明 API 调用失败但被优雅降级了
                # 这种情况视为连接失败
                error_msg = f"{provider} API call failed (all retries exhausted)"
                return False, error_msg
            else:
                # 空结果
                error_msg = f"{provider} returned empty result"
                return False, error_msg

        except Exception as e:
            # 捕获任何异常（虽然 refine_text 已经处理了大部分）
            error_msg = f"{provider} connection test failed: {str(e)}"
            app_logger.log_api_call(provider, 0, False, error_msg)
            return False, error_msg
