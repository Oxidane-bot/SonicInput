"""统一日志系统 - 单一接口，智能路由，性能监控集成

这是Sonic Input的统一日志系统，提供：
- 单一清晰的API接口
- 智能输出路由（控制台 + 文件）
- 内置性能监控和追踪
- 即时无缓冲输出

使用示例:
    from sonicinput.utils import logger

    logger.info("Application started")
    logger.performance("transcription", 2.5, audio_duration=5.0)

    with logger.trace("voice_processing") as trace:
        # ... processing code ...
        trace.checkpoint("transcription_done")
"""

import json
import os
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Union

# ConfigKeys import moved to method level to avoid circular import
# from ..core.services.config import ConfigKeys


def _safe_print(message: str, output_stream=sys.stdout) -> None:
    """安全打印，处理Unicode编码错误"""
    try:
        print(message, file=output_stream, flush=True)
    except UnicodeEncodeError:
        safe_msg = message.encode("ascii", "ignore").decode("ascii")
        print(f"[ENCODING_WARNING] {safe_msg}", file=output_stream, flush=True)
    except (OSError, ValueError):
        # Ignore invalid console handles (e.g., no attached console in onefile GUI)
        return


class LogLevel(Enum):
    """日志级别"""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogCategory(Enum):
    """日志类别（用于过滤和路由）"""

    AUDIO = "audio"
    API = "api"
    UI = "ui"
    MODEL = "model"
    HOTKEY = "hotkey"
    GPU = "gpu"
    STARTUP = "startup"
    ERROR = "error"
    PERFORMANCE = "performance"


@dataclass
class TraceContext:
    """性能追踪上下文"""

    trace_id: str
    operation: str
    component: str = ""
    start_time: float = field(default_factory=time.time)
    parameters: Dict[str, Any] = field(default_factory=dict)
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)

    def checkpoint(self, name: str, data: Dict[str, Any] = None) -> None:
        """添加检查点"""
        self.checkpoints.append(
            {
                "name": name,
                "timestamp": time.time(),
                "elapsed": time.time() - self.start_time,
                "data": data or {},
            }
        )

    def duration(self) -> float:
        """获取总耗时"""
        return time.time() - self.start_time


class UnifiedLogger:
    """统一日志系统 - 单例模式"""

    _MAX_LOG_SIZE_MB = 100

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._config_service = None  # 延迟设置
        self._min_level = LogLevel.DEBUG if self._is_dev_mode() else LogLevel.INFO
        self._console_output_enabled = False  # 默认禁用控制台输出（从配置加载）
        self._enabled_categories = set(LogCategory)  # 默认所有类别
        self._lock = threading.RLock()

        # 设置日志文件
        log_dir = Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = log_dir / "app.log"
        self._max_log_size_mb = 10
        self._max_backup_files = 2
        self._keep_logs_days = 7

        # 追踪栈（每线程）
        self._trace_stack: Dict[int, List[TraceContext]] = {}
        self._trace_counter = 0

        # Defer log retention cleanup until after config is loaded to avoid
        # early import cycles during module initialization.

    @staticmethod
    def _is_dev_mode() -> bool:
        """检查是否为开发模式"""
        return (
            "--dev" in sys.argv or os.getenv("VOICE_INPUT_DEV") or "--gui" in sys.argv
        )

    def set_config_service(self, config_service) -> None:
        """设置配置服务并从配置中加载日志设置

        Args:
            config_service: 配置服务实例
        """
        self._config_service = config_service
        self._load_settings_from_config()

    def _load_settings_from_config(self) -> None:
        """从配置中加载日志设置"""
        if not self._config_service:
            return

        try:
            # 读取日志级别
            level_str = self._config_service.get_setting("logging.level", "WARNING")
            self._min_level = self._string_to_log_level(level_str)

            # 读取控制台输出设置
            self._console_output_enabled = self._config_service.get_setting(
                "logging.console_output", False
            )

            max_log_size_mb = self._config_service.get_setting(
                "logging.max_log_size_mb", self._max_log_size_mb
            )
            max_backup_files = self._config_service.get_setting(
                "logging.max_backup_files", self._max_backup_files
            )
            keep_logs_days = self._config_service.get_setting(
                "logging.keep_logs_days", self._keep_logs_days
            )

            self._max_log_size_mb = self._validate_positive_number(
                max_log_size_mb,
                default=self._max_log_size_mb,
                name="logging.max_log_size_mb",
                min_value=1.0,
                max_value=self._MAX_LOG_SIZE_MB,
            )
            self._max_backup_files = self._validate_positive_int(
                max_backup_files,
                default=self._max_backup_files,
                name="logging.max_backup_files",
                min_value=1,
            )
            self._keep_logs_days = self._validate_positive_int(
                keep_logs_days,
                default=self._keep_logs_days,
                name="logging.keep_logs_days",
                min_value=1,
            )

            # 读取启用的类别
            enabled_categories_str = self._config_service.get_setting(
                "logging.enabled_categories", []
            )
            if enabled_categories_str:
                resolved_categories = set()
                invalid_categories = []
                for cat in enabled_categories_str:
                    try:
                        if isinstance(cat, LogCategory):
                            resolved_categories.add(cat)
                        else:
                            resolved_categories.add(LogCategory(str(cat)))
                    except Exception:
                        invalid_categories.append(cat)

                if resolved_categories:
                    self._enabled_categories = resolved_categories
                else:
                    self._enabled_categories = set(LogCategory)

                if invalid_categories:
                    self._warn_config(
                        f"Ignoring unknown log categories: {invalid_categories}"
                    )
            else:
                self._enabled_categories = set(LogCategory)

        except Exception as e:
            self._warn_config(f"Failed to load logger settings from config: {e}")

        self._cleanup_old_logs()

    def _string_to_log_level(self, level_str: str) -> LogLevel:
        """将字符串转换为 LogLevel 枚举"""
        level_map = {
            "DEBUG": LogLevel.DEBUG,
            "INFO": LogLevel.INFO,
            "WARNING": LogLevel.WARNING,
            "ERROR": LogLevel.ERROR,
            "CRITICAL": LogLevel.CRITICAL,
        }
        return level_map.get(level_str.upper(), LogLevel.WARNING)

    def _rotate_logs(self) -> None:
        """检查并按大小滚动日志"""
        try:
            if not self._log_file.exists():
                return

            max_bytes = int(self._max_log_size_mb * 1024 * 1024)
            if self._log_file.stat().st_size <= max_bytes:
                return

            if self._max_backup_files < 1:
                self._log_file.unlink(missing_ok=True)
                return

            for idx in range(self._max_backup_files, 0, -1):
                src = self._log_file.with_name(f"app.log.{idx}")
                dst = self._log_file.with_name(f"app.log.{idx + 1}")
                if src.exists():
                    if idx == self._max_backup_files:
                        src.unlink(missing_ok=True)
                    else:
                        src.replace(dst)

            backup = self._log_file.with_name("app.log.1")
            self._log_file.replace(backup)
        except Exception as e:
            self._warn_config(f"Log rotation failed: {e}")
            return

    def _cleanup_old_logs(self) -> None:
        """按天清理过期日志文件"""
        if self._keep_logs_days < 1:
            return

        try:
            cutoff_time = time.time() - (self._keep_logs_days * 24 * 3600)
            for file_path in self._log_file.parent.glob("app.log*"):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                    except OSError:
                        continue
        except Exception as e:
            self._warn_config(f"Log retention cleanup failed: {e}")

    def _warn_config(self, message: str) -> None:
        _safe_print(f"[LOG WARNING] {message}", output_stream=sys.stderr)

    def _validate_positive_int(
        self,
        value: Any,
        default: int,
        name: str,
        min_value: int = 1,
        max_value: Union[int, None] = None,
    ) -> int:
        try:
            if isinstance(value, bool):
                raise ValueError("bool is not valid")
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    raise ValueError("empty string")
                value = int(float(value))
            elif isinstance(value, (int, float)):
                value = int(value)
            else:
                raise ValueError("unsupported type")
            if value < min_value:
                raise ValueError("too small")
            if max_value is not None and value > max_value:
                raise ValueError("too large")
            return value
        except Exception:
            self._warn_config(f"Invalid {name} value '{value}', using {default}")
            return default

    def _validate_positive_number(
        self,
        value: Any,
        default: float,
        name: str,
        min_value: float = 1.0,
        max_value: Union[float, None] = None,
    ) -> float:
        try:
            if isinstance(value, bool):
                raise ValueError("bool is not valid")
            if isinstance(value, str):
                value = float(value.strip())
            elif isinstance(value, (int, float)):
                value = float(value)
            else:
                raise ValueError("unsupported type")
            if value < min_value:
                raise ValueError("too small")
            if max_value is not None and value > max_value:
                raise ValueError("too large")
            return value
        except Exception:
            self._warn_config(f"Invalid {name} value '{value}', using {default}")
            return float(default)

    def set_log_level(self, level: "Union[str, LogLevel]") -> None:
        """动态修改日志级别

        Args:
            level: 日志级别，可以是字符串或 LogLevel 枚举
        """
        with self._lock:
            if isinstance(level, str):
                self._min_level = self._string_to_log_level(level)
            else:
                self._min_level = level

            # 如果有配置服务，同步更新配置
            if self._config_service:
                try:
                    self._config_service.set_setting(
                        "logging.level", self._min_level.name
                    )
                except Exception as e:
                    print(
                        f"[LOG WARNING] Failed to save log level to config: {e}",
                        file=sys.stderr,
                    )

    def set_console_output(self, enabled: bool) -> None:
        """动态修改控制台输出设置

        Args:
            enabled: 是否启用控制台输出
        """
        with self._lock:
            self._console_output_enabled = enabled

            # 如果有配置服务，同步更新配置
            if self._config_service:
                try:
                    self._config_service.set_setting("logging.console_output", enabled)
                except Exception as e:
                    print(
                        f"[LOG WARNING] Failed to save console output setting: {e}",
                        file=sys.stderr,
                    )

    def is_debug_enabled(self) -> bool:
        """检查DEBUG级别日志是否启用

        Returns:
            如果当前日志级别为DEBUG则返回True
        """
        return self._min_level == LogLevel.DEBUG

    def set_enabled_categories(self, categories: "List[LogCategory]") -> None:
        """设置启用的日志类别

        Args:
            categories: 要启用的日志类别列表
        """
        with self._lock:
            self._enabled_categories = set(categories)

            # 如果有配置服务，同步更新配置
            if self._config_service:
                try:
                    category_names = [cat.value for cat in categories]
                    self._config_service.set_setting(
                        "logging.enabled_categories", category_names
                    )
                except Exception as e:
                    print(
                        f"[LOG WARNING] Failed to save enabled categories: {e}",
                        file=sys.stderr,
                    )

    def get_log_level(self) -> LogLevel:
        """获取当前日志级别"""
        return self._min_level

    def get_console_output(self) -> bool:
        """获取控制台输出设置"""
        return self._console_output_enabled

    def get_enabled_categories(self) -> "List[LogCategory]":
        """获取启用的日志类别"""
        return list(self._enabled_categories)

    def _should_log(self, level: LogLevel) -> bool:
        """检查是否应该记录该级别日志"""
        return level.value >= self._min_level.value

    def _format_console_message(
        self,
        level: LogLevel,
        category: LogCategory,
        message: str,
        context: Dict[str, Any] = None,
    ) -> str:
        """格式化控制台消息（包含context）"""
        timestamp = time.strftime("%H:%M:%S")

        # 颜色代码
        colors = {
            LogLevel.DEBUG: "\033[36m",  # Cyan
            LogLevel.INFO: "\033[32m",  # Green
            LogLevel.WARNING: "\033[33m",  # Yellow
            LogLevel.ERROR: "\033[31m",  # Red
            LogLevel.CRITICAL: "\033[35m",  # Magenta
        }
        reset = "\033[0m"
        color = colors.get(level, "")

        # 基本消息
        parts = [
            f"[{timestamp}] {color}{level.name}{reset} | {category.value} | {message}"
        ]

        # 添加context（如果有且重要）
        if context and category in [
            LogCategory.PERFORMANCE,
            LogCategory.AUDIO,
            LogCategory.MODEL,
            LogCategory.ERROR,
        ]:
            # 格式化context为可读形式
            context_str = self._format_context_readable(context)
            if context_str:
                parts.append(f"\n  {context_str}")

        return "".join(parts)

    def _format_context_readable(self, context: Dict[str, Any]) -> str:
        """格式化context为可读字符串"""
        parts = []
        for key, value in context.items():
            if isinstance(value, dict):
                # 嵌套字典特殊处理
                if key == "breakdown":
                    parts.append(f"{key}: {value}")
                else:
                    parts.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            elif isinstance(value, (list, tuple)):
                parts.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                parts.append(f"{key}: {value}")
        return " | ".join(parts)

    @staticmethod
    def _safe_json_serialize(obj):
        """安全的 JSON 序列化，处理枚举和其他特殊类型"""
        # 处理枚举类型（如 PySide6 的 ActivationReason）
        if hasattr(obj, "value") and hasattr(obj, "name"):
            return f"{type(obj).__name__}.{obj.name}"
        # 处理类型对象
        if hasattr(obj, "__name__"):
            return obj.__name__
        # 其他情况转为字符串
        return str(obj)

    def _format_file_message(
        self,
        level: LogLevel,
        category: LogCategory,
        message: str,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> str:
        """格式化文件日志消息（详细JSON格式）"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        parts = [timestamp, level.name.ljust(8), category.value.ljust(12)]
        if component:
            parts.append(f"[{component}]")
        parts.append(message)

        if context:
            # 使用自定义序列化器处理特殊类型
            context_json = json.dumps(
                context,
                ensure_ascii=False,
                separators=(",", ":"),
                default=self._safe_json_serialize,
            )
            parts.append(f"| {context_json}")

        return " | ".join(parts)

    def _write_log(
        self,
        level: LogLevel,
        category: LogCategory,
        message: str,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        """写入日志（控制台 + 文件）"""
        # PERFORMANCE 类别绕过级别检查，总是记录
        if category != LogCategory.PERFORMANCE:
            if not self._should_log(level):
                return

        # 检查类别是否启用
        if category not in self._enabled_categories:
            return

        with self._lock:
            # 控制台输出（选择性）
            if self._console_output_enabled and self._should_output_to_console(
                level, category
            ):
                console_msg = self._format_console_message(
                    level, category, message, context
                )
                output_stream = (
                    sys.stderr if level.value >= LogLevel.ERROR.value else sys.stdout
                )
                _safe_print(console_msg, output_stream)

            # 文件输出（全部）
            try:
                file_msg = self._format_file_message(
                    level, category, message, context, component
                )
                self._rotate_logs()
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(file_msg + "\n")
                    if level.value >= LogLevel.WARNING.value:
                        f.flush()
            except Exception as e:
                print(f"[LOG ERROR] Failed to write to log file: {e}", file=sys.stderr)

    def _should_output_to_console(self, level: LogLevel, category: LogCategory) -> bool:
        """判断是否输出到控制台"""
        # WARNING以上总是输出
        if level.value >= LogLevel.WARNING.value:
            return True

        # 特殊类别总是输出（性能、模型、音频）
        if category in [LogCategory.PERFORMANCE, LogCategory.MODEL, LogCategory.AUDIO]:
            return True

        # INFO级别在GUI模式下输出
        if level == LogLevel.INFO and self._is_dev_mode():
            return True

        return False

    # ============ 公开API ============

    def debug(
        self,
        message: str,
        category: LogCategory = LogCategory.STARTUP,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        """记录DEBUG日志"""
        self._write_log(LogLevel.DEBUG, category, message, context, component)

    def info(
        self,
        message: str,
        category: LogCategory = LogCategory.STARTUP,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        """记录INFO日志"""
        self._write_log(LogLevel.INFO, category, message, context, component)

    def warning(
        self,
        message: str,
        category: LogCategory = LogCategory.ERROR,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        """记录WARNING日志"""
        self._write_log(LogLevel.WARNING, category, message, context, component)

    def error(
        self,
        message: str,
        exception: Exception = None,
        category: LogCategory = LogCategory.ERROR,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        """记录ERROR日志"""
        ctx = context or {}
        if exception:
            ctx["exception"] = str(exception)
            ctx["exception_type"] = type(exception).__name__
        self._write_log(LogLevel.ERROR, category, message, ctx, component)

    def critical(
        self,
        message: str,
        exception: Exception = None,
        category: LogCategory = LogCategory.ERROR,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        """记录CRITICAL日志"""
        ctx = context or {}
        if exception:
            ctx["exception"] = str(exception)
            ctx["exception_type"] = type(exception).__name__
        self._write_log(LogLevel.CRITICAL, category, message, ctx, component)

    # ============ 便捷方法 ============

    def audio(self, event: str, details: Dict[str, Any] = None) -> None:
        """记录音频事件"""
        self.info(f"Audio: {event}", LogCategory.AUDIO, details, "audio")

    def performance(
        self,
        operation: str,
        duration: float,
        audio_duration: float = None,
        details: Dict[str, Any] = None,
    ) -> None:
        """记录性能指标（自动格式化）"""
        ctx = details or {}
        ctx["duration"] = f"{duration:.3f}s"

        if audio_duration:
            ctx["audio_duration"] = f"{audio_duration:.2f}s"

        # 简化消息，移除RTF状态指示器
        message = f"Performance: {operation} - {duration:.3f}s"

        self.info(message, LogCategory.PERFORMANCE, ctx, "performance")

    @contextmanager
    def trace(
        self, operation: str, component: str = "", parameters: Dict[str, Any] = None
    ):
        """性能追踪上下文管理器"""
        thread_id = threading.get_ident()

        # 创建trace context
        with self._lock:
            self._trace_counter += 1
            trace_id = f"trace_{self._trace_counter:04d}"

        trace_ctx = TraceContext(
            trace_id=trace_id,
            operation=operation,
            component=component,
            parameters=parameters or {},
        )

        # 入栈
        with self._lock:
            if thread_id not in self._trace_stack:
                self._trace_stack[thread_id] = []
            self._trace_stack[thread_id].append(trace_ctx)

        # 记录开始
        self.info(
            f"Starting {operation}",
            LogCategory.PERFORMANCE,
            {"trace_id": trace_id, "parameters": parameters},
            component,
        )

        try:
            yield trace_ctx
        except Exception as e:
            trace_ctx.checkpoint("error", {"error": str(e), "type": type(e).__name__})
            self.error(
                f"Operation {operation} failed",
                e,
                LogCategory.ERROR,
                {"trace_id": trace_id},
                component,
            )
            raise
        finally:
            # 出栈
            with self._lock:
                if thread_id in self._trace_stack and self._trace_stack[thread_id]:
                    self._trace_stack[thread_id].pop()

            # 记录完成
            duration = trace_ctx.duration()
            self.info(
                f"Completed {operation} in {duration:.3f}s",
                LogCategory.PERFORMANCE,
                {
                    "trace_id": trace_id,
                    "duration": f"{duration:.3f}s",
                    "checkpoints": len(trace_ctx.checkpoints),
                },
                component,
            )


# ============ 全局单例和兼容接口 ============

# 创建全局logger实例
logger = UnifiedLogger()

# 向后兼容的别名
unified_logger = logger


# 兼容旧接口的包装类
class LegacyLoggerAdapter:
    """兼容旧app_logger接口的适配器"""

    def __init__(self, logger_instance: UnifiedLogger):
        self._logger = logger_instance

    # 基础日志方法（委托给UnifiedLogger）
    def debug(
        self,
        message: str,
        category: LogCategory = LogCategory.STARTUP,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        self._logger.debug(message, category, context, component)

    def info(
        self,
        message: str,
        category: LogCategory = LogCategory.STARTUP,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        self._logger.info(message, category, context, component)

    def warning(
        self,
        message: str,
        category: LogCategory = LogCategory.ERROR,
        context: Dict[str, Any] = None,
        component: str = None,
    ) -> None:
        self._logger.warning(message, category, context, component)

    def error(
        self,
        message: str,
        exception: Exception = None,
        category: LogCategory = LogCategory.ERROR,
        context: Dict[str, Any] = None,
        component: str = None,
        exc_info=None,
    ) -> None:
        """记录错误日志

        Args:
            exc_info: 兼容参数，被忽略（因为我们已经有 exception 参数）
        """
        self._logger.error(message, exception, category, context, component)

    def log_audio_event(self, event: str, details: Dict[str, Any] = None) -> None:
        self._logger.audio(event, details)

    def audio(self, event: str, details: Dict[str, Any] = None) -> None:
        """记录音频事件"""
        self._logger.audio(event, details)

    def log_transcription(
        self, audio_length: float, text: str, confidence: float = None
    ) -> None:
        details = {
            "audio_length": f"{audio_length:.2f}s",
            "text_preview": text[:50] + "..." if len(text) > 50 else text,
        }
        if confidence is not None:
            details["confidence"] = confidence
        self._logger.audio("Transcription completed", details)

    def log_api_call(
        self,
        service: str,
        response_time: float,
        success: bool,
        error: str = None,
        prompt_tokens: int = None,
        completion_tokens: int = None,
        total_tokens: int = None,
    ) -> None:
        # 基础消息
        message = f"API Call: {service} - {'Success' if success else 'Failed'} in {response_time:.2f}s"

        # 计算TPS（Tokens Per Second）
        if completion_tokens and response_time > 0:
            tps = completion_tokens / response_time
            message += f" | TPS: {tps:.2f}"

        context = {
            "service": service,
            "response_time": f"{response_time:.2f}s",
            "success": success,
        }

        # 添加token统计
        if prompt_tokens is not None:
            context["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            context["completion_tokens"] = completion_tokens
            if response_time > 0:
                context["tokens_per_second"] = round(
                    completion_tokens / response_time, 2
                )
        if total_tokens is not None:
            context["total_tokens"] = total_tokens

        if error:
            context["error"] = error

        # 明确区分 info 和 error 的调用（参数数量不同）
        if success:
            self._logger.info(message, LogCategory.API, context, "api")
        else:
            self._logger.error(message, None, LogCategory.API, context, "api")

    def log_error(self, error: Exception, context: str) -> None:
        # 获取完整的异常堆栈
        tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = "".join(tb_lines)

        # 记录错误和完整堆栈
        self._logger.error(
            f"Error in {context}",
            error,
            LogCategory.ERROR,
            context={"traceback": tb_str, "error_details": str(error)},
            component=context,
        )

    def log_startup(self) -> None:
        self._logger.info(
            "Sonic Input starting up", LogCategory.STARTUP, component="startup"
        )

    def log_shutdown(self) -> None:
        self._logger.info(
            "Sonic Input shutting down",
            LogCategory.STARTUP,
            component="shutdown",
        )

    def log_hotkey_event(self, hotkey: str, action: str) -> None:
        self._logger.info(
            f"Hotkey Event: {hotkey} - {action}", LogCategory.HOTKEY, component="hotkey"
        )

    def log_gpu_info(
        self, gpu_available: bool, memory_usage: Dict[str, float] = None
    ) -> None:
        context = {"gpu_available": gpu_available}
        if memory_usage:
            context["memory_usage"] = memory_usage
        self._logger.info(
            f"GPU Available: {gpu_available}", LogCategory.GPU, context, "gpu"
        )

    def log_model_loading_step(self, step: str, details: Dict[str, Any] = None) -> None:
        self._logger.info(f"Model: {step}", LogCategory.MODEL, details, "model")

    def log_gui_operation(
        self, operation: str, details: str = "", level: str = "INFO"
    ) -> None:
        message = f"GUI Operation: {operation}"
        if details:
            message += f" - {details}"

        log_func = getattr(self._logger, level.lower(), self._logger.info)
        log_func(message, LogCategory.UI, component="gui")

    def is_debug_enabled(self) -> bool:
        """检查DEBUG级别日志是否启用（委托给UnifiedLogger）"""
        return self._logger.is_debug_enabled()


# 创建兼容适配器
app_logger_compat = LegacyLoggerAdapter(logger)


__all__ = [
    "logger",
    "unified_logger",
    "app_logger_compat",
    "LogLevel",
    "LogCategory",
    "TraceContext",
]
