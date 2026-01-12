"""模型管理器 - 负责Whisper模型的生命周期管理"""

import time
from enum import Enum
from typing import Any, Dict, Optional

from ...utils import app_logger


class ModelState(Enum):
    """模型状态"""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    RELOADING = "reloading"


class ModelManager:
    """模型生命周期管理器

    负责模型的加载、卸载、重载等操作，以及状态管理。
    与具体的转录逻辑解耦。
    """

    def __init__(self, speech_service_factory, event_service=None):
        """初始化模型管理器

        Args:
            speech_service_factory: 语音服务工厂函数
            event_service: 事件服务（可选）
        """
        self.speech_service_factory = speech_service_factory
        self.event_service = event_service

        # 模型状态管理
        self._whisper_engine = None
        self._model_state = ModelState.UNLOADED
        self._state_lock = None  # 将在start()中初始化

        # 模型信息
        self._current_model_name = None
        self._load_start_time = None
        self._last_load_error = None

        app_logger.log_audio_event("ModelManager initialized", {})

    def start(self) -> None:
        """启动模型管理器"""
        import threading

        self._state_lock = threading.Lock()

        # 初始化引擎实例
        self._whisper_engine = self.speech_service_factory()
        self._current_model_name = self._whisper_engine.model_name

        app_logger.log_audio_event(
            "ModelManager started", {"initial_model": self._current_model_name}
        )

    def stop(self) -> None:
        """停止模型管理器"""
        self.unload_model()

        if self._whisper_engine:
            self._whisper_engine = None

        self._model_state = ModelState.UNLOADED
        app_logger.log_audio_event("ModelManager stopped", {})

    def load_model(
        self,
        model_name: Optional[str] = None,
        timeout: int = 300,
        download_if_missing: bool = False,
    ) -> bool:
        """加载模型（异步兼容方法，推荐使用load_model_sync）

        Args:
            model_name: 模型名称（可选，默认使用当前模型）
            timeout: 超时时间（秒）

        Returns:
            True如果加载成功
        """
        return self.load_model_sync(model_name, timeout, download_if_missing)

    def load_model_sync(
        self,
        model_name: Optional[str] = None,
        timeout: int = 300,
        download_if_missing: bool = False,
    ) -> bool:
        """同步加载模型（阻塞直到加载完成）

        Args:
            model_name: 模型名称（可选，默认使用当前模型）
            timeout: 超时时间（秒）

        Returns:
            True如果加载成功
        """

        if not self._state_lock:
            self.start()

        with self._state_lock:
            if self._model_state == ModelState.LOADED:
                if not model_name or model_name == self._current_model_name:
                    return True  # 模型已加载

            if self._model_state == ModelState.LOADING:
                return False  # 正在加载中

            # 设置加载状态
            self._model_state = ModelState.LOADING
            self._load_start_time = time.time()
            self._last_load_error = None

        try:
            # 广播模型加载开始事件
            self._emit_model_event(
                "model_loading_started",
                {"model_name": model_name or self._current_model_name},
            )

            # 准备模型参数
            target_model_name = model_name or self._current_model_name

            # 检查是否需要重新创建引擎
            if (
                model_name and model_name != self._current_model_name
            ) or not self._whisper_engine:
                self._whisper_engine = self.speech_service_factory()
                self._current_model_name = target_model_name

            # 执行模型加载
            load_success = self._whisper_engine.load_model(
                model_name=model_name, download_if_missing=download_if_missing
            )

            # 检查加载结果
            if not load_success:
                with self._state_lock:
                    self._model_state = ModelState.ERROR
                raise Exception("Model load_model() returned False")

            # 更新状态
            with self._state_lock:
                self._model_state = ModelState.LOADED
                load_time = time.time() - self._load_start_time

            # 广播模型加载完成事件
            self._emit_model_event(
                "model_loaded",
                {
                    "model_name": self._current_model_name,
                    "device": self._whisper_engine.device,
                    "use_gpu": getattr(self._whisper_engine, "use_gpu", False),
                    "load_time": f"{load_time:.2f}s",
                },
            )

            app_logger.log_audio_event(
                "Model loaded successfully",
                {
                    "model_name": self._current_model_name,
                    "device": self._whisper_engine.device,
                    "load_time": load_time,
                },
            )

            return True

        except Exception as e:
            # 加载失败
            with self._state_lock:
                self._model_state = ModelState.ERROR
                self._last_load_error = str(e)

            app_logger.log_error(e, "load_model_sync")

            # 广播模型加载失败事件
            self._emit_model_event(
                "model_loading_failed",
                {"model_name": model_name or self._current_model_name, "error": str(e)},
            )

            return False

    def unload_model(self) -> None:
        """卸载模型"""
        if not self._whisper_engine or self._model_state == ModelState.UNLOADED:
            return

        try:
            # 广播模型卸载开始事件
            self._emit_model_event(
                "model_unloading_started", {"model_name": self._current_model_name}
            )

            # 执行卸载
            self._whisper_engine.unload_model()

            # 更新状态
            with self._state_lock:
                self._model_state = ModelState.UNLOADED

            # 广播模型卸载完成事件
            self._emit_model_event(
                "model_unloaded", {"model_name": self._current_model_name}
            )

            app_logger.log_audio_event(
                "Model unloaded", {"model_name": self._current_model_name}
            )

        except Exception as e:
            app_logger.log_error(e, "unload_model")
            with self._state_lock:
                self._model_state = ModelState.ERROR
                self._last_load_error = str(e)

    def reload_model(
        self, model_name: Optional[str] = None, use_gpu: Optional[bool] = None
    ) -> bool:
        """重新加载模型（用于切换GPU/CPU或更换模型）

        Args:
            model_name: 新模型名称（可选）
            use_gpu: 是否使用GPU（可选）

        Returns:
            True如果重载成功
        """
        start_time = time.time()

        with self._state_lock:
            if self._model_state == ModelState.RELOADING:
                return False  # 已在重载中

            self._model_state = ModelState.RELOADING

        try:
            app_logger.log_audio_event(
                "Reloading model with new settings",
                {
                    "model_name": model_name or self._current_model_name,
                    "use_gpu": use_gpu,
                },
            )

            # 广播重载开始事件
            self._emit_model_event(
                "model_reloading_started",
                {
                    "old_model": self._current_model_name,
                    "new_model": model_name or self._current_model_name,
                    "use_gpu": use_gpu,
                },
            )

            # 1. 卸载当前模型
            if self._model_state != ModelState.UNLOADED:
                self.unload_model()

            # 2. 创建新的引擎实例
            if model_name:
                # 需要重新创建引擎以应用新配置
                from ...speech import SherpaEngine

                target_model_name = model_name or self._current_model_name
                # sherpa-onnx 不使用 use_gpu 参数
                self._whisper_engine = SherpaEngine(target_model_name, language="zh")
                self._current_model_name = target_model_name

            # 3. 加载新模型
            success = self.load_model()

            reload_time = time.time() - start_time

            if success:
                # 广播重载成功事件
                self._emit_model_event(
                    "model_reloaded",
                    {
                        "model_name": self._current_model_name,
                        "device": self._whisper_engine.device,
                        "use_gpu": getattr(self._whisper_engine, "use_gpu", False),
                        "reload_time": f"{reload_time:.2f}s",
                    },
                )

                app_logger.log_audio_event(
                    "Model reloaded successfully",
                    {
                        "model_name": self._current_model_name,
                        "device": self._whisper_engine.device,
                        "reload_time": reload_time,
                    },
                )

                with self._state_lock:
                    self._model_state = ModelState.LOADED

            else:
                with self._state_lock:
                    self._model_state = ModelState.ERROR

            return success

        except Exception as e:
            error_msg = f"Failed to reload model: {e}"
            app_logger.log_error(e, "reload_model")

            with self._state_lock:
                self._model_state = ModelState.ERROR
                self._last_load_error = error_msg

            # 广播重载失败事件
            self._emit_model_event(
                "model_reloading_failed",
                {
                    "model_name": model_name or self._current_model_name,
                    "error": error_msg,
                },
            )

            return False

    def get_model_state(self) -> ModelState:
        """获取当前模型状态

        Returns:
            当前模型状态
        """
        return self._model_state

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载

        Returns:
            True如果模型已加载
        """
        return (
            self._model_state == ModelState.LOADED
            and self._whisper_engine
            and self._whisper_engine.is_model_loaded
        )

    def get_whisper_engine(self):
        """获取Whisper引擎实例

        Returns:
            Whisper引擎实例（如果已加载）
        """
        if self.is_model_loaded():
            return self._whisper_engine
        return None

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息

        Returns:
            模型信息字典
        """
        info = {
            "state": self._model_state.value,
            "model_name": self._current_model_name,
            "is_loaded": self.is_model_loaded(),
        }

        if self._whisper_engine:
            info.update(
                {
                    "device": getattr(self._whisper_engine, "device", "unknown"),
                    "use_gpu": getattr(self._whisper_engine, "use_gpu", False),
                }
            )

        if self._load_start_time and self._model_state == ModelState.LOADING:
            info["load_time"] = time.time() - self._load_start_time

        if self._last_load_error:
            info["last_error"] = self._last_load_error

        return info

    def _emit_model_event(self, event_name: str, data: Dict[str, Any]) -> None:
        """发送模型相关事件

        Args:
            event_name: 事件名称
            data: 事件数据
        """
        if self.event_service:
            try:
                self.event_service.emit(event_name, data)
            except Exception as e:
                app_logger.log_error(e, "emit_model_event")

    def get_available_models(self) -> list:
        """获取可用模型列表

        Returns:
            模型名称列表
        """
        if self._whisper_engine:
            try:
                return self._whisper_engine.get_available_models()
            except Exception as e:
                app_logger.log_error(e, "get_available_models")
                return ["tiny", "base", "small", "medium", "large-v3-turbo"]
        return []
