"""UI服务适配器

作为UI层和业务逻辑层之间的适配器，实现UI服务接口。
UI组件通过此适配器访问业务逻辑，不直接依赖具体的业务实现。
"""

from typing import Any, Dict, Optional

from ...utils import app_logger
from ..interfaces import IConfigService, IEventService
from ..services.storage.history_storage_service import HistoryStorageService


class UIMainServiceAdapter:
    """UI主窗口服务适配器

    适配VoiceInputApp的功能，使其符合IUIMainService接口。
    """

    def __init__(self, voice_input_app):
        """初始化UI主服务适配器

        Args:
            voice_input_app: VoiceInputApp实例
        """
        self.voice_input_app = voice_input_app
        app_logger.log_audio_event("UIMainServiceAdapter initialized", {})

    def is_recording(self) -> bool:
        """检查是否正在录音"""
        return getattr(self.voice_input_app, "is_recording", False)

    def start_recording(self) -> None:
        """开始录音"""
        if hasattr(self.voice_input_app, "start_recording"):
            self.voice_input_app.start_recording()

    def stop_recording(self) -> None:
        """停止录音"""
        if hasattr(self.voice_input_app, "stop_recording"):
            self.voice_input_app.stop_recording()

    def get_current_status(self) -> str:
        """获取当前状态文本"""
        if self.is_recording():
            return "Recording..."
        return "Ready"

    def get_event_service(self) -> IEventService:
        """获取事件服务"""
        if hasattr(self.voice_input_app, "events"):
            return self.voice_input_app.events
        raise AttributeError("VoiceInputApp does not have events service")

    def show_settings(self) -> None:
        """显示设置窗口"""
        # 这个方法在MainWindow中实现，这里不需要实现
        pass

    def reload_hotkeys(self) -> None:
        """重新加载快捷键配置"""
        if hasattr(self.voice_input_app, "reload_hotkeys"):
            self.voice_input_app.reload_hotkeys()

    def get_whisper_engine(self) -> Optional[Any]:
        """获取Whisper引擎"""
        if hasattr(self.voice_input_app, "whisper_engine"):
            return self.voice_input_app.whisper_engine
        return None

    def cleanup(self) -> None:
        """清理资源"""
        if hasattr(self.voice_input_app, "cleanup"):
            self.voice_input_app.cleanup()


class UISettingsServiceAdapter:
    """UI设置服务适配器

    适配配置服务的功能，使其符合IUISettingsService接口。
    """

    def __init__(
        self,
        config_service: IConfigService,
        event_service: IEventService,
        history_service: HistoryStorageService,
        transcription_service=None,
        ai_processing_controller=None,
    ):
        """初始化UI设置服务适配器

        Args:
            config_service: 配置服务
            event_service: 事件服务
            history_service: 历史记录存储服务
            transcription_service: 转录服务（可选）
            ai_processing_controller: AI处理控制器（可选）
        """
        self.config_service = config_service
        self.event_service = event_service
        self.history_service = history_service
        self.transcription_service = transcription_service
        self.ai_processing_controller = ai_processing_controller
        app_logger.log_audio_event("UISettingsServiceAdapter initialized", {})

    def get_all_settings(self) -> Dict[str, Any]:
        """获取所有设置"""
        return self.config_service.get_all_settings()

    def set_setting(self, key: str, value: Any) -> None:
        """设置单个配置项"""
        self.config_service.set_setting(key, value)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取单个配置项"""
        return self.config_service.get_setting(key, default)

    def save_settings(self) -> None:
        """保存设置到文件"""
        if hasattr(self.config_service, "save_config"):
            self.config_service.save_config()

    def export_config(self, file_path: str) -> None:
        """导出配置到文件"""
        if hasattr(self.config_service, "export_config"):
            self.config_service.export_config(file_path)

    def import_config(self, file_path: str) -> None:
        """从文件导入配置"""
        if hasattr(self.config_service, "import_config"):
            self.config_service.import_config(file_path)

    def reset_to_defaults(self) -> None:
        """重置为默认配置"""
        # Backward/forward compatible: refactored config service exposes `reset_to_default(key=None)`
        if hasattr(self.config_service, "reset_to_default"):
            self.config_service.reset_to_default()
            return
        if hasattr(self.config_service, "reset_to_defaults"):
            self.config_service.reset_to_defaults()

    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        # Use authoritative defaults from the core config system.
        # Avoid relying on private attributes like `config_service._default_config` which
        # are not present on RefactoredConfigService.
        from .config.config_defaults import get_default_config

        return get_default_config()

    def get_event_service(self) -> IEventService:
        """获取事件服务"""
        return self.event_service

    def get_history_service(self) -> HistoryStorageService:
        """获取历史记录存储服务"""
        return self.history_service

    def get_transcription_service(self):
        """获取转录服务"""
        return self.transcription_service

    def get_ai_processing_controller(self):
        """获取AI处理控制器"""
        return self.ai_processing_controller


class UIModelServiceAdapter:
    """UI模型管理服务适配器

    适配模型管理功能，使其符合IUIModelService接口。
    """

    def __init__(self, voice_input_app):
        """初始化UI模型服务适配器

        Args:
            voice_input_app: VoiceInputApp实例
        """
        self.voice_input_app = voice_input_app
        app_logger.log_audio_event("UIModelServiceAdapter initialized", {})

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        engine = self.get_whisper_engine()
        if engine and hasattr(engine, "is_model_loaded"):
            return engine.is_model_loaded
        return False

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        engine = self.get_whisper_engine()
        if engine and hasattr(engine, "get_model_info"):
            return engine.get_model_info()

        # Fallback: 构建基本信息
        if engine:
            return {
                "is_loaded": getattr(engine, "is_model_loaded", False),
                "model_name": getattr(engine, "model_name", "Unknown"),
                "device": getattr(engine, "device", "Unknown"),
            }
        return {"is_loaded": False, "model_name": "Unknown", "device": "Unknown"}

    def load_model(self, model_name: str, download_if_missing: bool = False) -> bool:
        """加载模型

        Args:
            model_name: 模型名称

        Returns:
            bool: 加载是否成功
        """
        engine = self.get_whisper_engine()
        if engine and hasattr(engine, "load_model"):
            try:
                result = engine.load_model(
                    model_name, download_if_missing=download_if_missing
                )
            except TypeError:
                # 兼容旧签名
                result = engine.load_model(model_name)
            return bool(result)
        return False

    def unload_model(self) -> None:
        """卸载模型"""
        engine = self.get_whisper_engine()
        if engine and hasattr(engine, "unload_model"):
            engine.unload_model()

    def test_model(self) -> Dict[str, Any]:
        """测试模型"""
        # 简单的模型测试实现
        engine = self.get_whisper_engine()
        if not engine:
            return {"success": False, "error": "No engine available"}

        if not self.is_model_loaded():
            return {"success": False, "error": "Model not loaded"}

        return {
            "success": True,
            "model_name": getattr(engine, "model_name", "Unknown"),
            "device": getattr(engine, "device", "Unknown"),
        }

    def get_whisper_engine(self) -> Optional[Any]:
        """获取Whisper引擎"""
        if hasattr(self.voice_input_app, "whisper_engine"):
            return self.voice_input_app.whisper_engine
        return None


class UIAudioServiceAdapter:
    """UI音频服务适配器

    适配音频设备管理功能，使其符合IUIAudioService接口。
    """

    def __init__(self, voice_input_app):
        """初始化UI音频服务适配器

        Args:
            voice_input_app: VoiceInputApp实例
        """
        self.voice_input_app = voice_input_app
        app_logger.log_audio_event("UIAudioServiceAdapter initialized", {})

    def get_audio_devices(self) -> list:
        """获取可用音频设备列表"""
        try:
            from ...audio.recorder import AudioRecorder

            temp_recorder = AudioRecorder()
            devices = temp_recorder.get_audio_devices()
            temp_recorder.cleanup()
            return devices
        except Exception as e:
            app_logger.log_error(e, "get_audio_devices")
            return []

    def refresh_audio_devices(self) -> None:
        """刷新音频设备列表"""
        # 这个方法主要用于UI刷新，具体实现可能需要重新初始化录音器
        pass


class UIGPUServiceAdapter:
    """UI GPU服务适配器

    适配GPU信息查询功能，使其符合IUIGPUService接口。
    """

    def __init__(self):
        """初始化UI GPU服务适配器"""
        app_logger.log_audio_event("UIGPUServiceAdapter initialized", {})

    def get_gpu_info(self) -> Dict[str, Any]:
        """获取GPU信息（sherpa-onnx不使用GPU）"""
        # sherpa-onnx 使用 CPU，不需要 GPU
        return {
            "cuda_available": False,
            "message": "sherpa-onnx uses CPU-only inference (no GPU required)",
            "device": "cpu",
        }

    def check_gpu_availability(self) -> bool:
        """检查GPU是否可用（sherpa-onnx不使用GPU）"""
        return False  # sherpa-onnx 总是使用 CPU
