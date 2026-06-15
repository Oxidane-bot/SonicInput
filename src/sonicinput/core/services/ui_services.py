"""UI服务实现

真正的UI服务实现，直接依赖核心服务，不依赖VoiceInputApp。
采用纯依赖注入模式，符合SOLID原则。
"""

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from ...utils import app_logger
from ..interfaces import (
    IConfigService,
    IEventService,
    ISpeechService,
    IStateManager,
)
from .config import ConfigKeys
from ..services.storage import HistoryStorageService, ReviewStorageService

if TYPE_CHECKING:
    from .launch_at_login_service import LaunchAtLoginService

_UNSET = object()


class UIMainService:
    """UI主窗口服务实现

    直接依赖核心服务，通过事件驱动实现功能。
    """

    def __init__(
        self,
        config_service: IConfigService,
        event_service: IEventService,
        state_manager: IStateManager,
    ):
        """初始化UI主服务

        Args:
            config_service: 配置服务
            event_service: 事件服务
            state_manager: 状态管理器
        """
        self.config = config_service
        self.events = event_service
        self.state = state_manager
        app_logger.log_audio_event("UIMainService initialized", {})

    def is_recording(self) -> bool:
        """检查是否正在录音"""
        return self.state.is_recording

    def start_recording(self) -> None:
        """开始录音

        通过事件驱动，不直接调用控制器
        """
        from .events import Events

        self.events.emit(Events.RECORDING_STARTED)

    def stop_recording(self) -> None:
        """停止录音

        通过事件驱动，不直接调用控制器
        """
        from .events import Events

        self.events.emit(Events.RECORDING_STOPPED)

    def get_current_status(self) -> str:
        """获取当前状态文本"""
        if self.is_recording():
            return "Recording..."
        return "Ready"

    def get_event_service(self) -> IEventService:
        """获取事件服务"""
        return self.events

    def show_settings(self) -> None:
        """显示设置窗口

        这个方法在MainWindow中实现，这里不需要实现
        """
        pass

    def reload_hotkeys(self) -> None:
        """重新加载快捷键配置

        通过配置重载服务实现
        """
        from .events import Events

        self.events.emit(Events.CONFIG_CHANGED, {"section": "hotkeys"})

    def get_whisper_engine(self) -> Optional[Any]:
        """获取Whisper引擎

        注意：这个方法在新架构中应该通过 IUIModelService 访问，
        这里保留是为了向后兼容。
        """
        # 通过容器获取 speech service
        # 但这里我们没有容器的引用...
        # 这个方法应该被废弃，UI应该使用 IUIModelService
        app_logger.log_audio_event(
            "UIMainService.get_whisper_engine() called - deprecated",
            {"message": "Use IUIModelService instead"},
        )
        return None

    def cleanup(self) -> None:
        """清理资源"""
        app_logger.log_audio_event("UIMainService cleanup", {})


class UISettingsService:
    """UI设置服务实现

    封装配置服务，提供UI友好的接口。
    """

    def __init__(
        self,
        config_service: IConfigService,
        event_service: IEventService,
        history_service: HistoryStorageService,
        transcription_service=None,
        ai_processing_controller=None,
        localization_service=None,
        launch_at_login_service: "LaunchAtLoginService | None" = None,
        review_storage_service: ReviewStorageService | None = None,
        container=None,
    ):
        """初始化UI设置服务

        Args:
            config_service: 配置服务
            event_service: 事件服务
            history_service: 历史记录存储服务
            transcription_service: 转录服务(可选,用于retry processing)
            ai_processing_controller: AI处理控制器(可选,用于retry processing)
            launch_at_login_service: 开机自启系统集成服务（可选）
            review_storage_service: Review suggestions/lexicon 存储服务（可选）
            container: DI容器(可选,用于热重载后获取最新服务)
        """
        self.config_service = config_service
        self.event_service = event_service
        self.history_service = history_service
        self._transcription_service = transcription_service
        self._ai_processing_controller = ai_processing_controller
        self.localization_service = localization_service
        self._launch_at_login_service = launch_at_login_service
        self._review_storage_service = review_storage_service
        self._container = container
        app_logger.log_audio_event("UISettingsService initialized", {})

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

    def save_config(self) -> None:
        """保存配置到文件（别名方法）

        这个方法是为了兼容不同的调用方式而存在的。
        settings_window.py 调用 save_config()，其他地方可能调用 save_settings()。
        实现立即保存，不使用防抖延迟。
        """
        if hasattr(self.config_service, "save_config"):
            # 立即保存，不使用防抖延迟
            success = self.config_service.save_config()
            if success:
                from ...utils import app_logger

                app_logger.log_audio_event("Config saved immediately from UI", {})
            return success
        return False

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
        if hasattr(self.config_service, "reset_to_defaults"):
            self.config_service.reset_to_defaults()

    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        if hasattr(self.config_service, "get_default_config"):
            try:
                return copy.deepcopy(self.config_service.get_default_config())
            except Exception:
                pass
        try:
            from .config.config_defaults import get_default_config

            return copy.deepcopy(get_default_config())
        except Exception:
            return {}

    def get_event_service(self) -> IEventService:
        """获取事件服务"""
        return self.event_service

    def get_config_service(self) -> IConfigService:
        """获取底层配置服务。"""
        return self.config_service

    def get_history_service(self) -> HistoryStorageService:
        """获取历史记录存储服务"""
        return self.history_service

    def get_review_storage_service(self):
        """获取 Review suggestions/lexicon 存储服务。"""
        if self._review_storage_service is not None:
            return self._review_storage_service

        if self._container is None:
            return None

        try:
            service = self._container.resolve(ReviewStorageService)
            if service:
                self._review_storage_service = service
            return service
        except Exception:
            return None

    def list_review_suggestions(self, limit: int = 100) -> list[dict[str, Any]]:
        """列出待审查 suggestions，供 Review UI 展示。"""
        service = self.get_review_storage_service()
        if service is None:
            return []
        return service.list_pending_suggestions(limit=limit)

    def list_review_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        """列出最近的 review jobs，供 Review UI 展示运行状态。"""
        service = self.get_review_storage_service()
        if service is None:
            return []
        list_jobs = getattr(service, "list_review_jobs", None)
        if not callable(list_jobs):
            return []
        return list_jobs(limit=limit)

    def decide_review_suggestion(
        self,
        suggestion_id: str,
        decision: str,
        note: str | None = None,
    ) -> bool:
        """接受/拒绝/忽略/归档一条 review suggestion。"""
        service = self.get_review_storage_service()
        if service is None:
            return False
        service.record_decision(suggestion_id, decision, note=note)
        return True

    def list_lexicon_entries(self, limit: int = 200) -> list[dict[str, Any]]:
        """列出 active 本地词汇记忆。"""
        service = self.get_review_storage_service()
        if service is None:
            return []
        return service.list_active_lexicon_entries(limit=limit)

    def clear_lexicon_entries(self) -> bool:
        """清空/归档 active 本地词汇记忆。"""
        service = self.get_review_storage_service()
        if service is None:
            return False
        service.clear_lexicon_entries()
        return True

    def clear_review_learning_data(self) -> bool:
        """清空本地 review 学习数据。

        这会重置：
        - 已接受的 lexicon memory
        - 用于 suppress 相似建议的 review decisions / processed statuses
        但不会删除 review jobs 审计记录。
        """
        service = self.get_review_storage_service()
        if service is None:
            return False
        clear_learning_data = getattr(service, "clear_learning_data", None)
        if not callable(clear_learning_data):
            return False
        clear_learning_data()
        return True

    def export_lexicon_entries(self, file_path: str | None = None) -> dict[str, Any]:
        """导出 active 本地词汇记忆为 JSON 文件。"""
        service = self.get_review_storage_service()
        if service is None:
            return {
                "success": False,
                "path": "",
                "count": 0,
                "reason": "review_storage_unavailable",
            }

        entries = service.list_active_lexicon_entries(limit=10000)
        if file_path:
            target_path = Path(file_path).expanduser()
        else:
            target_path = (
                Path.home()
                / "Documents"
                / "SonicInput"
                / "exports"
                / f"lexicon_memory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(entries),
            "entries": entries,
        }
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "success": True,
            "path": str(target_path),
            "count": len(entries),
        }

    def export_review_debug_report(
        self,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """导出 prompt/validator 失败模式建议，供本地调试使用。"""
        service = self.get_review_storage_service()
        if service is None:
            return {
                "success": False,
                "path": "",
                "count": 0,
                "reason": "review_storage_unavailable",
            }

        try:
            suggestions = service.list_pending_suggestions(limit=1000)
            recent_jobs = service.list_review_jobs(limit=50)
        except Exception as exc:
            return {
                "success": False,
                "path": "",
                "count": 0,
                "reason": str(exc),
            }

        debug_suggestions = [
            item
            for item in suggestions
            if str(item.get("suggestion_type", "") or "") == "prompt_failure_pattern"
        ]
        if file_path:
            target_path = Path(file_path).expanduser()
        else:
            target_path = (
                Path.home()
                / "Documents"
                / "SonicInput"
                / "exports"
                / f"review_debug_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(debug_suggestions),
            "suggestions": debug_suggestions,
            "recent_jobs": recent_jobs,
        }
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "success": True,
            "path": str(target_path),
            "count": len(debug_suggestions),
        }

    def run_review_now(self) -> dict[str, Any]:
        """手动触发一次本地 review。

        该方法供 UI 的 "Run Review Now" 调用。它会绕过 idle/min-interval 门禁，
        但仍保留录音、转写、AI 处理中止和 session budget 保护。
        """
        if not self.config_service.get_setting(ConfigKeys.REVIEW_ENABLED, False):
            return {
                "ran": False,
                "reason": "review_disabled",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }

        if self._container is None:
            return {
                "ran": False,
                "reason": "review_scheduler_unavailable",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }

        try:
            from .review_scheduler_service import ReviewSchedulerService

            scheduler = self._container.resolve(ReviewSchedulerService)
            result = scheduler.run_once_now()
        except Exception as exc:
            app_logger.log_audio_event(
                "UI manual review run failed",
                {"error": str(exc)},
            )
            return {
                "ran": False,
                "reason": "review_run_failed",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }

        return {
            "ran": bool(getattr(result, "ran", False)),
            "reason": str(getattr(result, "reason", "")),
            "jobId": str(getattr(result, "job_id", "") or ""),
            "reviewedRecordCount": int(
                getattr(result, "reviewed_record_count", 0) or 0
            ),
            "suggestionCount": int(getattr(result, "suggestion_count", 0) or 0),
        }

    def run_idle_review_once(self) -> dict[str, Any]:
        """自动触发一次保守的 idle review。"""
        if not self.config_service.get_setting(ConfigKeys.REVIEW_ENABLED, False):
            return {
                "ran": False,
                "reason": "review_disabled",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }

        if self._container is None:
            return {
                "ran": False,
                "reason": "review_scheduler_unavailable",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }

        try:
            from .review_scheduler_service import ReviewSchedulerService

            scheduler = self._container.resolve(ReviewSchedulerService)
            result = scheduler.run_once_if_idle()
        except Exception as exc:
            app_logger.log_audio_event(
                "UI idle review run failed",
                {"error": str(exc)},
            )
            return {
                "ran": False,
                "reason": "review_run_failed",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }

        return {
            "ran": bool(getattr(result, "ran", False)),
            "reason": str(getattr(result, "reason", "")),
            "jobId": str(getattr(result, "job_id", "") or ""),
            "reviewedRecordCount": int(
                getattr(result, "reviewed_record_count", 0) or 0
            ),
            "suggestionCount": int(getattr(result, "suggestion_count", 0) or 0),
        }

    def get_transcription_service(self):
        """获取转录服务

        优先从DI容器动态获取最新服务（支持热重载后获取新实例），
        如果容器不可用则返回初始化时保存的引用。
        """
        # 优先从容器获取最新服务（热重载后会更新）
        if self._container:
            try:
                fresh_service = self._container.resolve(ISpeechService)
                if fresh_service:
                    return fresh_service
            except Exception:
                pass
        # 回退到初始化时保存的引用
        return self._transcription_service

    def get_ai_processing_controller(self):
        """获取AI处理控制器"""
        return self._ai_processing_controller

    def sync_runtime_dependencies(
        self,
        *,
        transcription_service: Any = _UNSET,
        ai_processing_controller: Any = _UNSET,
    ) -> None:
        """同步当前运行时依赖引用，供 UI 使用最新服务实例。"""
        if transcription_service is not _UNSET:
            self._transcription_service = transcription_service
        if ai_processing_controller is not _UNSET:
            self._ai_processing_controller = ai_processing_controller

    def get_launch_at_login_service(self):
        """获取开机自启系统集成服务。"""
        if self._launch_at_login_service is not None:
            return self._launch_at_login_service

        if self._container is None:
            return None

        try:
            from .launch_at_login_service import LaunchAtLoginService

            service = self._container.resolve(LaunchAtLoginService)
            if service:
                self._launch_at_login_service = service
            return service
        except Exception:
            return None

    def sync_launch_at_login(self, enabled: bool) -> None:
        """同步开机自启设置到系统层。"""
        service = self.get_launch_at_login_service()
        if service is None:
            return
        service.sync(enabled)

    def get_localization_service(self):
        """Get UI localization service."""
        return self.localization_service


class UILocalizationService:
    """UI localization service."""

    _LANGUAGE_DISPLAY = {
        "auto": "System (Auto)",
        "en-US": "English",
        "zh-CN": "Simplified Chinese",
    }

    def __init__(self, config_service: IConfigService, event_service: IEventService):
        self.config_service = config_service
        self.event_service = event_service
        self._translator = None
        self._current_language = None
        self._translation_dir = self._resolve_translation_dir()
        app_logger.log_audio_event(
            "UILocalizationService initialized",
            {"translation_dir": str(self._translation_dir)},
        )

    def get_supported_languages(self) -> Dict[str, str]:
        """Return supported UI languages."""
        return dict(self._LANGUAGE_DISPLAY)

    def get_configured_language(self) -> str:
        """Return configured language or auto if unset."""
        return self.config_service.get_setting(ConfigKeys.UI_LANGUAGE, "auto") or "auto"

    def get_active_language(self) -> str:
        """Return resolved active language code."""
        return self._current_language or self._resolve_language(
            self.get_configured_language()
        )

    def apply_language(self, language: Optional[str] = None) -> str:
        """Apply language change to the running UI."""
        target = self._resolve_language(language or self.get_configured_language())
        if target == self._current_language:
            return target

        applied = self._install_translator(target)
        self._current_language = target

        from .events import Events

        self.event_service.emit(
            Events.UI_LANGUAGE_CHANGED,
            {"language": target, "applied": applied},
        )
        return target

    def _resolve_language(self, language: str) -> str:
        normalized = self._normalize_language_code(language)
        if normalized == "auto":
            normalized = self._normalize_language_code(self._get_system_locale())

        if normalized in self._LANGUAGE_DISPLAY:
            return normalized

        base = normalized.split("-")[0]
        for code in self._LANGUAGE_DISPLAY:
            if code.startswith(base):
                return code

        return "en-US"

    def _normalize_language_code(self, language: Optional[str]) -> str:
        if not language:
            return "auto"

        code = language.strip().replace("_", "-")
        if code.lower() == "auto":
            return "auto"

        if "-" in code:
            parts = code.split("-", 1)
            return f"{parts[0].lower()}-{parts[1].upper()}"

        code = code.lower()
        if code == "en":
            return "en-US"
        if code == "zh":
            return "zh-CN"
        return code

    def _get_system_locale(self) -> str:
        try:
            from PySide6.QtCore import QLocale

            return QLocale.system().name()
        except Exception:
            return "en-US"

    def _install_translator(self, language: str) -> bool:
        from PySide6.QtCore import QCoreApplication, QTranslator

        app = QCoreApplication.instance()
        if app is None:
            app_logger.log_audio_event(
                "UILocalizationService skipped install (no QCoreApplication)",
                {"language": language},
            )
            return False

        if self._translator:
            app.removeTranslator(self._translator)
            self._translator = None

        if language == "en-US":
            return True

        qm_path = self._translation_dir / f"sonicinput_{language.replace('-', '_')}.qm"
        if not qm_path.exists():
            app_logger.log_audio_event(
                "Translation file missing",
                {"language": language, "path": str(qm_path)},
            )
            return False

        translator = QTranslator()
        if not translator.load(str(qm_path)):
            app_logger.log_audio_event(
                "Failed to load translation",
                {"language": language, "path": str(qm_path)},
            )
            return False

        app.installTranslator(translator)
        self._translator = translator
        return True

    @staticmethod
    def _resolve_translation_dir() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            assets_dir = parent / "assets"
            if assets_dir.is_dir():
                return assets_dir / "i18n"
        return current.parents[4] / "assets" / "i18n"


class UIModelService:
    """UI模型管理服务实现

    直接依赖语音服务，提供模型管理功能。
    """

    def __init__(self, speech_service: ISpeechService):
        """初始化UI模型服务

        Args:
            speech_service: 语音识别服务
        """
        self.speech_service = speech_service
        app_logger.log_audio_event("UIModelService initialized", {})

    def set_speech_service(self, speech_service: ISpeechService) -> None:
        """更新运行时 speech service 引用。"""
        self.speech_service = speech_service

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        if self.speech_service and hasattr(self.speech_service, "is_model_loaded"):
            return self.speech_service.is_model_loaded
        return False

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息（返回运行时状态，不是静态元数据）"""
        # 优先从 ModelManager 获取运行时状态信息
        # ModelManager.get_model_info() 返回: {state, model_name, is_loaded, device, use_gpu}
        if hasattr(self.speech_service, "model_manager"):
            model_manager = self.speech_service.model_manager
            if model_manager and hasattr(model_manager, "get_model_info"):
                runtime_info = model_manager.get_model_info()
                if runtime_info and "model_name" in runtime_info:
                    return runtime_info

        # Fallback: 从 Engine 获取信息
        engine = None
        if hasattr(self.speech_service, "whisper_engine"):
            engine = self.speech_service.whisper_engine
        elif hasattr(self.speech_service, "_engine"):
            engine = self.speech_service._engine

        # 注意: engine.get_model_info() 可能返回静态元数据而非运行时状态
        # 所以我们优先构建运行时信息
        if engine:
            return {
                "is_loaded": getattr(engine, "is_model_loaded", False),
                "model_name": getattr(engine, "model_name", "Unknown"),
                "device": getattr(engine, "device", "Unknown"),
            }

        return {"is_loaded": False, "model_name": "Unknown", "device": "Unknown"}

    def load_model(self, model_name: str, download_if_missing: bool = False) -> bool:
        """加载模型 - 通过ModelManager确保事件正确触发

        Args:
            model_name: 模型名称

        Returns:
            bool: 加载是否成功
        """
        # 优先使用ModelManager (会自动发送MODEL_LOADED事件)
        if hasattr(self.speech_service, "model_manager"):
            model_manager = self.speech_service.model_manager
            if hasattr(model_manager, "load_model_sync"):
                try:
                    result = model_manager.load_model_sync(
                        model_name, download_if_missing=download_if_missing
                    )
                except TypeError:
                    result = model_manager.load_model_sync(model_name)
                return bool(result)

        # Fallback: 直接调用engine (向后兼容,虽然不会发送事件)
        engine = self._get_engine()
        if engine and hasattr(engine, "load_model"):
            try:
                result = engine.load_model(
                    model_name, download_if_missing=download_if_missing
                )
            except TypeError:
                result = engine.load_model(model_name)
            return bool(result)

        return False

    def unload_model(self) -> bool:
        """卸载模型 - 通过ModelManager确保事件正确触发

        Returns:
            bool: 卸载是否成功
        """
        # 优先使用ModelManager
        if hasattr(self.speech_service, "model_manager"):
            model_manager = self.speech_service.model_manager
            if hasattr(model_manager, "unload_model"):
                result = model_manager.unload_model()
                return bool(result)

        # Fallback: 直接调用engine
        engine = self._get_engine()
        if engine and hasattr(engine, "unload_model"):
            result = engine.unload_model()
            return bool(result)

        return False

    def test_model(self) -> Dict[str, Any]:
        """测试模型"""
        engine = self._get_engine()
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
        """获取语音引擎实例

        此方法提供对底层语音引擎的访问，用于与需要直接引擎访问的UI代码兼容。

        Returns:
            Optional[Any]: 引擎实例（SherpaEngine或其他），如果不可用则返回None
        """
        return self._get_engine()

    def _get_engine(self) -> Optional[Any]:
        """获取底层引擎（内部方法）"""
        # 优先检查 RefactoredTranscriptionService 的 model_manager
        if hasattr(self.speech_service, "model_manager"):
            model_manager = self.speech_service.model_manager
            if hasattr(model_manager, "_whisper_engine"):
                return model_manager._whisper_engine
            elif hasattr(model_manager, "get_whisper_engine"):
                return model_manager.get_whisper_engine()
        # 回退到直接检查
        if hasattr(self.speech_service, "whisper_engine"):
            return self.speech_service.whisper_engine
        elif hasattr(self.speech_service, "_engine"):
            return self.speech_service._engine
        return None


class UIAudioService:
    """UI音频服务实现

    提供音频设备管理功能。
    """

    def __init__(self):
        """初始化UI音频服务"""
        app_logger.log_audio_event("UIAudioService initialized", {})

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
        """刷新音频设备列表

        主要用于UI刷新，具体实现可能需要重新初始化录音器
        """
        pass


class UIGPUService:
    """UI GPU服务实现

    提供GPU信息查询功能。
    """

    def __init__(self):
        """初始化UI GPU服务"""
        app_logger.log_audio_event("UIGPUService initialized", {})

    def get_gpu_info(self) -> Dict[str, Any]:
        """获取GPU信息"""
        try:
            from ...speech.gpu_manager import GPUManager

            temp_gpu_manager = GPUManager()
            gpu_info = temp_gpu_manager.get_device_info()
            return gpu_info
        except Exception as e:
            app_logger.log_error(e, "get_gpu_info")
            return {"error": str(e), "cuda_available": False}

    def check_gpu_availability(self) -> bool:
        """检查GPU是否可用"""
        gpu_info = self.get_gpu_info()
        return gpu_info.get("cuda_available", False)
