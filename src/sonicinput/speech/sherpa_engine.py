"""sherpa-onnx 语音识别引擎

基于 sherpa-onnx 的轻量级本地语音识别实现
"""

from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger

try:
    import sherpa_onnx
except ImportError:
    logger.error("sherpa-onnx not installed. Please run: uv sync --extra local")
    sherpa_onnx = None

from ..core.base.lifecycle_component import LifecycleComponent
from ..core.interfaces.speech import ISpeechService
from .sherpa_models import SherpaModelManager
from .sherpa_streaming import SherpaStreamingSession


class SherpaEngine(LifecycleComponent, ISpeechService):
    """sherpa-onnx 引擎实现

    特性：
    - 支持离线 Paraformer/Zipformer 模型
    - 原生流式转录支持
    - 无GPU依赖，CPU高效推理
    - 轻量级模型管理
    """

    provider_id = "sherpa_onnx"
    display_name = "Sherpa-ONNX Local"
    description = "Lightweight offline ASR with streaming support"

    def __init__(
        self,
        model_name: str = "paraformer",
        language: str = "zh",
        cache_dir: Optional[str] = None,
        download_if_missing: bool = False,
    ):
        """初始化 sherpa-onnx 引擎

        Args:
            model_name: 模型名称 (paraformer | zipformer-small)
            language: 语言 (zh | en)
            cache_dir: 模型缓存目录
        """
        super().__init__("SherpaEngine")

        if sherpa_onnx is None:
            raise RuntimeError(
                "sherpa-onnx is not installed. Please install with: uv sync --extra local"
            )

        self.model_name = model_name
        self.language = language
        self.model_manager = SherpaModelManager(cache_dir)
        self.recognizer: Optional[sherpa_onnx.OnlineRecognizer] = None
        self._is_loaded = False
        self._download_if_missing = download_if_missing

        logger.info(
            f"SherpaEngine initialized with model: {model_name}, language: {language}"
        )

    def _do_start(self) -> bool:
        """Load sherpa-onnx model (LifecycleComponent API)

        Returns:
            True if model loaded successfully
        """
        return self.load_model(download_if_missing=self._download_if_missing)

    def _do_stop(self) -> bool:
        """Cleanup model resources (LifecycleComponent API)

        Returns:
            True if cleanup successful
        """
        self.unload_model()
        return True

    def load_model(
        self, model_name: Optional[str] = None, download_if_missing: bool = False
    ) -> bool:
        """加载模型

        Args:
            model_name: 模型名称，None 表示使用默认模型

        Returns:
            是否加载成功
        """
        if model_name:
            self.model_name = model_name

        try:
            logger.info(f"Loading model: {self.model_name}")

            # 获取模型配置
            model_config = self.model_manager.get_model_config(
                self.model_name, download_if_missing=download_if_missing
            )

            # 使用工厂方法创建识别器（sherpa-onnx 1.12+ API）
            if model_config["model_type"] == "paraformer":
                # Paraformer 使用工厂方法
                self.recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
                    tokens=model_config["tokens"],
                    encoder=model_config["encoder"],
                    decoder=model_config["decoder"],
                    num_threads=model_config["num_threads"],
                    sample_rate=16000,
                    feature_dim=80,
                    decoding_method=model_config["decoding_method"],
                    enable_endpoint_detection=True,
                    rule1_min_trailing_silence=1.2,  # 1.2秒停顿触发endpoint
                    rule2_min_trailing_silence=0.8,  # 0.8秒停顿触发endpoint
                    rule3_min_utterance_length=10,  # 10帧,允许更短句子
                    provider=model_config["provider"],
                )
            elif model_config["model_type"] == "zipformer":
                # Zipformer 使用工厂方法
                self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                    tokens=model_config["tokens"],
                    encoder=model_config["encoder"],
                    decoder=model_config["decoder"],
                    joiner=model_config["joiner"],
                    num_threads=model_config["num_threads"],
                    sample_rate=16000,
                    feature_dim=80,
                    decoding_method=model_config["decoding_method"],
                    enable_endpoint_detection=True,
                    rule1_min_trailing_silence=1.2,  # 1.2秒停顿触发endpoint
                    rule2_min_trailing_silence=0.8,  # 0.8秒停顿触发endpoint
                    rule3_min_utterance_length=10,  # 10帧,允许更短句子
                    provider=model_config["provider"],
                )
            else:
                raise ValueError(f"Unknown model type: {model_config['model_type']}")

            self._is_loaded = True
            logger.info(f"Model {self.model_name} loaded successfully")

            return True

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self._is_loaded = False
            return False

    def unload_model(self) -> None:
        """卸载当前模型"""
        if self.recognizer:
            # sherpa-onnx 的 Python 绑定会自动释放资源
            self.recognizer = None
            self._is_loaded = False
            logger.info("Model unloaded")

    def transcribe(
        self, audio_data: np.ndarray, language: Optional[str] = None
    ) -> Dict[str, Any]:
        """转录音频数据（同步模式，用于分块转录）

        Args:
            audio_data: 音频数据，应该是 float32 类型，采样率 16kHz
            language: 语言代码（sherpa-onnx 模型通常是预训练语言，此参数被忽略）

        Returns:
            转录结果字典
        """
        if not self.is_model_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        try:
            # 确保音频格式正确
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # 创建临时流
            stream = self.recognizer.create_stream()

            # 推送音频
            stream.accept_waveform(16000, audio_data)

            # 标记输入结束
            stream.input_finished()

            # 解码
            while self.recognizer.is_ready(stream):
                self.recognizer.decode_stream(stream)

            # 获取结果
            result_text = self.recognizer.get_result(stream)

            return {
                "text": result_text,
                "language": self.language,
                "segments": [],  # sherpa-onnx 不提供分段信息
            }

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Failed to transcribe audio: {e}")

    def create_streaming_session(self) -> SherpaStreamingSession:
        """创建流式转录会话（用于实时模式）

        Returns:
            流式转录会话对象

        Raises:
            RuntimeError: 如果模型未加载
        """
        if not self.is_model_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        stream = self.recognizer.create_stream()
        return SherpaStreamingSession(self.recognizer, stream)

    def get_available_models(self) -> List[str]:
        """获取可用的模型列表

        Returns:
            模型名称列表
        """
        return list(self.model_manager.MODELS.keys())

    @property
    def is_model_loaded(self) -> bool:
        """模型是否已加载"""
        return self._is_loaded and self.recognizer is not None

    @property
    def device(self) -> str:
        """设备属性（兼容性）

        sherpa-onnx 是纯CPU推理，此属性始终返回 'CPU'。
        此属性用于与模型管理系统保持兼容。

        Returns:
            str: 始终返回 "CPU"
        """
        return "CPU"

    def get_model_info(self) -> Dict[str, Any]:
        """获取当前模型信息（合并静态元数据和运行时状态）

        Returns:
            模型信息字典，包含静态元数据和运行时状态
        """
        # 获取静态模型元数据
        if self.model_name:
            info = self.model_manager.get_model_info(self.model_name).copy()
        else:
            info = {}

        # 添加/覆盖运行时状态信息（UI所需）
        info.update(
            {
                "is_loaded": self.is_model_loaded,
                "model_name": self.model_name or "Unknown",
                "device": self.device,
            }
        )

        return info

    def __repr__(self) -> str:
        """字符串表示"""
        return f"SherpaEngine(model={self.model_name}, language={self.language}, loaded={self.is_model_loaded})"
