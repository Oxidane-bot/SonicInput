"""主窗口组件 - 最小化GUI实现（使用依赖注入）"""

from typing import Any, Dict, Optional

from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ..core.services.events import Events
from ..core.services.ui_services import UIMainService, UIModelService, UISettingsService
from ..utils import app_logger


class ModelTestThread(QThread):
    """Model test thread to avoid blocking UI"""

    progress_update = Signal(str)
    test_complete = Signal(bool, dict, str)

    def __init__(self, whisper_engine, parent=None):
        super().__init__(parent)
        self.whisper_engine = whisper_engine

    def run(self):
        try:
            import numpy as np

            self.progress_update.emit(
                QCoreApplication.translate(
                    "MainWindow", "Creating test audio (2s low-level noise)..."
                )
            )
            # Create low-level white noise instead of silence to avoid hallucination
            # Use shorter duration and very low amplitude
            duration = 2  # 2 seconds
            sample_rate = 16000
            audio_length = int(duration * sample_rate)

            # Generate very low amplitude white noise
            test_audio = np.random.normal(0, 0.001, audio_length).astype(np.float32)

            app_logger.log_audio_event(
                "Model test requested",
                {"audio_type": "low_noise", "duration": duration, "amplitude": "0.001"},
            )

            self.progress_update.emit(
                QCoreApplication.translate(
                    "MainWindow", "Running transcription test..."
                )
            )
            result = self.whisper_engine.transcribe(test_audio)

            # Check for hallucination patterns
            text_output = result.get("text", "").strip()
            is_hallucination = self._is_likely_hallucination(text_output)

            # For test purposes, hallucination on noise is actually expected behavior
            test_success = True  # Model responded without crashing

            result_info = {
                "text": text_output,
                "is_hallucination": is_hallucination,
                "confidence": result.get("confidence", 0),
                "language": result.get("language", "unknown"),
            }

            app_logger.log_audio_event(
                "Model test completed",
                {
                    "result": text_output,
                    "is_hallucination": is_hallucination,
                    "test_success": test_success,
                    "confidence": result.get("confidence", 0),
                },
            )

            self.test_complete.emit(test_success, result_info, "")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            app_logger.log_error(e, "ModelTestThread.run")
            # 添加详细的错误信息到结果中
            self.test_complete.emit(False, {}, error_msg)

    def _is_likely_hallucination(self, text: str) -> bool:
        """Check if text output is likely a Whisper hallucination"""
        if not text:
            return False

        text_lower = text.lower().strip()

        # Common Whisper hallucination patterns
        common_hallucinations = [
            "thank you",
            "thanks",
            "thank you.",
            "thanks.",
            "bye",
            "bye.",
            "goodbye",
            "goodbye.",
            "you",
            "you.",
            "okay",
            "okay.",
            "ok",
            "ok.",
            "yes",
            "yes.",
            "no",
            "no.",
            "yeah",
            "yeah.",
            "um",
            "uh",
            "hmm",
            "mm",
            "hello",
            "hi",
            "hey",
            "music",
            "applause",
            "laughter",
            "silence",
            "quiet",
            "pause",
        ]

        return text_lower in common_hallucinations


class MainWindow(QMainWindow):
    """最小化主窗口 - 使用依赖注入的UI服务"""

    # 信号定义
    window_closing = Signal()
    _REVIEW_AUTO_TIMER_INTERVAL_MS = 60_000

    def __init__(
        self,
        ui_main_service: Optional[UIMainService] = None,
        ui_settings_service: Optional[UISettingsService] = None,
        ui_model_service: Optional[UIModelService] = None,
        parent=None,
    ):
        """初始化主窗口

        Args:
            ui_main_service: UI主窗口服务（可选，推荐通过构造函数注入）
            ui_settings_service: UI设置服务（可选，推荐通过构造函数注入）
            ui_model_service: UI模型服务（可选，推荐通过构造函数注入）
            parent: 父窗口
        """
        super().__init__(parent)
        self.ui_main_service = ui_main_service
        self.ui_settings_service = ui_settings_service
        self.ui_model_service = ui_model_service
        self._settings_window: Optional[Any] = (
            None  # FluentSettingsWindow, lazy-init in show_settings
        )

        self.setup_window()
        self.setup_ui()

        # 如果服务已经注入，连接事件
        if self.ui_main_service:
            self._connect_service_events()
        if self.ui_settings_service:
            self._setup_review_auto_timer()

        app_logger.log_audio_event(
            "MainWindow initialized", {"services_injected": ui_main_service is not None}
        )

    def setup_window(self) -> None:
        """配置窗口基本属性"""
        from .utils import create_app_icon

        self.setWindowTitle(QCoreApplication.translate("MainWindow", "Sonic Input"))
        self.setWindowIcon(create_app_icon())
        self.setFixedSize(400, 300)  # 固定小尺寸
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)

        # 默认隐藏 - 使用系统托盘
        self.hide()

    def setup_ui(self) -> None:
        """设置最小化UI界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 状态显示
        self.status_label = QLabel(
            QCoreApplication.translate("MainWindow", "Sonic Input")
        )
        self.status_label.setProperty("status_key", "title")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.status_label)

        # 录音控制
        self.recording_button = QPushButton(
            QCoreApplication.translate("MainWindow", "Start Recording")
        )
        self.recording_button.setProperty("recording_state", "idle")
        self.recording_button.clicked.connect(self.toggle_recording)
        layout.addWidget(self.recording_button)

        # 设置按钮
        self.settings_button = QPushButton(
            QCoreApplication.translate("MainWindow", "Settings")
        )
        self.settings_button.clicked.connect(self.show_settings)
        layout.addWidget(self.settings_button)

        # 最小化到托盘按钮
        self.minimize_button = QPushButton(
            QCoreApplication.translate("MainWindow", "Minimize to Tray")
        )
        self.minimize_button.clicked.connect(self.hide)
        layout.addWidget(self.minimize_button)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Update UI text for the current language."""
        self.setWindowTitle(QCoreApplication.translate("MainWindow", "Sonic Input"))

        status_key = self.status_label.property("status_key") or "title"
        status_map = {
            "title": QCoreApplication.translate("MainWindow", "Sonic Input"),
            "ready": QCoreApplication.translate("MainWindow", "Ready"),
            "recording": QCoreApplication.translate("MainWindow", "Recording..."),
        }
        if status_key in status_map:
            self.status_label.setText(status_map[status_key])

        recording_state = self.recording_button.property("recording_state") or "idle"
        if recording_state == "recording":
            self.recording_button.setText(
                QCoreApplication.translate("MainWindow", "Stop Recording")
            )
        else:
            self.recording_button.setText(
                QCoreApplication.translate("MainWindow", "Start Recording")
            )

        self.settings_button.setText(
            QCoreApplication.translate("MainWindow", "Settings")
        )
        self.minimize_button.setText(
            QCoreApplication.translate("MainWindow", "Minimize to Tray")
        )

    def set_ui_services(
        self,
        ui_main_service: UIMainService,
        ui_settings_service: UISettingsService,
        ui_model_service: UIModelService,
    ) -> None:
        """设置UI服务（依赖注入）

        Args:
            ui_main_service: 主窗口UI服务
            ui_settings_service: 设置窗口UI服务
            ui_model_service: 模型管理UI服务
        """
        self.ui_main_service = ui_main_service
        self.ui_settings_service = ui_settings_service
        self.ui_model_service = ui_model_service
        self._connect_service_events()
        self._setup_review_auto_timer()

    def _setup_review_auto_timer(self) -> None:
        """Start a conservative periodic review tick.

        The timer itself is cheap and the settings service keeps review disabled
        by default. When enabled, each tick still goes through ReviewSchedulerService
        idle/busy/min-interval/session-budget gates.
        """
        if not self.ui_settings_service:
            return
        timer = getattr(self, "_review_auto_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(self._REVIEW_AUTO_TIMER_INTERVAL_MS)
            timer.timeout.connect(self._on_review_auto_timer)
            self._review_auto_timer = timer
        if not timer.isActive():
            timer.start()

    def _on_review_auto_timer(self) -> None:
        run_review = getattr(self.ui_settings_service, "run_idle_review_once", None)
        if not callable(run_review):
            return
        try:
            result = run_review()
        except Exception as e:
            app_logger.log_error(e, "review_auto_timer")
            return

        if isinstance(result, dict) and result.get("ran"):
            app_logger.log_audio_event(
                "Idle review completed from auto timer",
                {
                    "job_id": result.get("jobId", ""),
                    "reviewed_record_count": result.get("reviewedRecordCount", 0),
                    "suggestion_count": result.get("suggestionCount", 0),
                },
            )
            settings = getattr(self, "_settings_window", None)
            view_model = getattr(settings, "view_model", None)
            refresh = getattr(view_model, "refreshReviewSuggestions", None)
            if callable(refresh):
                refresh()

    def _connect_service_events(self) -> None:
        """连接UI服务事件"""
        if not self.ui_main_service:
            return

        # 录音状态事件
        events = self.ui_main_service.get_event_service()
        events.on(Events.RECORDING_STARTED, self._on_recording_started)
        events.on(Events.RECORDING_STOPPED, self._on_recording_stopped)
        events.on(Events.UI_LANGUAGE_CHANGED, self._on_language_changed)

        # 快捷键事件
        events.on(Events.HOTKEY_CONFLICT, self._on_hotkey_conflict)
        events.on(Events.HOTKEY_REGISTRATION_ERROR, self._on_hotkey_registration_error)

    def _on_language_changed(self, data: object = None) -> None:
        """Handle runtime UI language change."""
        self.retranslate_ui()

    def _on_recording_started(self, data: Any = None) -> None:
        """??????"""
        self.recording_button.setText(
            QCoreApplication.translate("MainWindow", "Stop Recording")
        )
        self.recording_button.setProperty("recording_state", "recording")
        self.status_label.setText(
            QCoreApplication.translate("MainWindow", "Recording...")
        )
        self.status_label.setProperty("status_key", "recording")

    def _on_recording_stopped(self, audio_length: int) -> None:
        """??????"""
        self.recording_button.setText(
            QCoreApplication.translate("MainWindow", "Start Recording")
        )
        self.recording_button.setProperty("recording_state", "idle")
        self.status_label.setText(QCoreApplication.translate("MainWindow", "Ready"))
        self.status_label.setProperty("status_key", "ready")

    def _on_hotkey_conflict(self, data: dict) -> None:
        """快捷键冲突事件"""
        from .utils import show_hotkey_conflict_error

        hotkey = data.get("hotkey", "Unknown")
        suggestions = data.get("suggestions", [])

        # 显示友好的错误对话框
        should_open_settings = show_hotkey_conflict_error(self, hotkey, suggestions)

        # 如果用户选择打开设置
        if should_open_settings:
            self.show_settings()

    def _on_hotkey_registration_error(self, data: dict) -> None:
        """Handle hotkey registration error."""
        from .utils import show_hotkey_registration_error

        hotkey = data.get("hotkey", "Unknown")
        error = data.get("error", "Unknown error")

        show_hotkey_registration_error(
            self,
            QCoreApplication.translate(
                "MainWindow", "Failed to register hotkey '{hotkey}': {error}"
            ).format(hotkey=hotkey, error=error),
            recovery_suggestions=[
                QCoreApplication.translate(
                    "MainWindow", "Try a different hotkey combination"
                ),
                QCoreApplication.translate(
                    "MainWindow",
                    "Check the hotkey format (e.g., 'ctrl+shift+v')",
                ),
                QCoreApplication.translate("MainWindow", "Restart the application"),
            ],
        )

    def toggle_recording(self) -> None:
        """切换录音状态"""
        if not self.ui_main_service:
            return

        if self.ui_main_service.is_recording():
            self.ui_main_service.stop_recording()
        else:
            self.ui_main_service.start_recording()

    def show_settings(self) -> None:
        """显示设置窗口"""
        try:
            if not hasattr(self, "_settings_window") or not self._settings_window:
                from .fluent_settings_window import FluentSettingsWindow

                self._settings_window = FluentSettingsWindow(
                    self.ui_settings_service, self.ui_model_service
                )
                app_logger.log_audio_event("Fluent settings window created", {})

                # 连接模型管理信号
                if hasattr(self._settings_window, "model_load_requested"):
                    self._settings_window.model_load_requested.connect(
                        self._on_model_load_requested
                    )
                if hasattr(self._settings_window, "model_unload_requested"):
                    self._settings_window.model_unload_requested.connect(
                        self._on_model_unload_requested
                    )
                if hasattr(self._settings_window, "model_test_requested"):
                    self._settings_window.model_test_requested.connect(
                        self._on_model_test_requested
                    )

                # 进程退出时主动释放 QML engine, 防止 root window/engine 泄漏。
                # closeEvent 只 hide() 主窗口, 不会触发 settings 清理。
                qapp = QApplication.instance()
                if qapp is not None:
                    qapp.aboutToQuit.connect(self._release_settings_window)

            self._settings_window.show()
            self._settings_window.raise_()
            self._settings_window.activateWindow()

        except Exception as e:
            app_logger.log_error(e, "show_settings")

    def _release_settings_window(self) -> None:
        """Drop the cached FluentSettingsWindow so its QML engine can be GC'd.

        Called from QApplication.aboutToQuit. FluentSettingsWindow is a QObject
        hosting a QQmlApplicationEngine + root window; without this the engine
        survives process shutdown long enough to log Qt warnings.
        """
        settings = getattr(self, "_settings_window", None)
        if settings is None:
            return
        try:
            if hasattr(settings, "close"):
                settings.close()
            settings.deleteLater()
        except Exception as e:
            app_logger.log_error(e, "_release_settings_window")
        finally:
            self._settings_window = None

    def _on_model_load_requested(self, model_name: str) -> None:
        """Handle model load request from settings window."""
        try:
            if self.ui_model_service:
                app_logger.log_audio_event(
                    "Model load requested via GUI", {"model": model_name}
                )

                # FluentSettingsWindow is a QObject (QML host), not a QWidget, so it
                # cannot be a dialog parent. Use None so dialogs are top-level on the
                # active screen. cancelButtonText is "" because setCancelButton(None)
                # below removes the button; PySide6 rejects None for that positional-only str.
                parent_widget = None

                progress = QProgressDialog(
                    QCoreApplication.translate(
                        "MainWindow",
                        "Loading model: {model}...\nThis may take a few seconds.",
                    ).format(model=model_name),
                    "",
                    0,
                    0,
                    parent_widget,
                )
                progress.setWindowTitle(
                    QCoreApplication.translate("MainWindow", "Loading Model")
                )
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumDuration(0)
                progress.setCancelButton(None)
                progress.show()

                QApplication.processEvents()

                try:
                    success = self.ui_model_service.load_model(
                        model_name, download_if_missing=True
                    )
                    progress.close()

                    if not success:
                        raise Exception(
                            QCoreApplication.translate(
                                "MainWindow", "Failed to load model '{model}'."
                            ).format(model=model_name)
                        )

                    app_logger.log_audio_event(
                        "Model load completed successfully via GUI",
                        {"model_name": model_name},
                    )

                    QMessageBox.information(
                        parent_widget,
                        QCoreApplication.translate("MainWindow", "Model Loaded"),
                        QCoreApplication.translate(
                            "MainWindow", "Model '{model}' loaded successfully!"
                        ).format(model=model_name),
                    )

                except Exception as load_error:
                    progress.close()
                    app_logger.log_error(load_error, "model_load_execution")
                    QMessageBox.critical(
                        parent_widget,
                        QCoreApplication.translate("MainWindow", "Model Load Failed"),
                        QCoreApplication.translate(
                            "MainWindow",
                            "Failed to load model '{model}':\n{error}",
                        ).format(model=model_name, error=load_error),
                    )

                if hasattr(self, "_settings_window") and self._settings_window:
                    QTimer.singleShot(100, self._settings_window.refresh_model_status)

        except Exception as e:
            app_logger.log_error(e, "model_load_request_gui")
            QMessageBox.critical(
                None,
                QCoreApplication.translate("MainWindow", "Error"),
                QCoreApplication.translate(
                    "MainWindow", "Error processing model load request:\n{error}"
                ).format(error=e),
            )

    def _on_model_unload_requested(self) -> None:
        """处理模型卸载请求"""
        try:
            if self.ui_model_service:
                app_logger.log_audio_event("Model unload requested", {})
                self.ui_model_service.unload_model()
                app_logger.log_audio_event("Model unloaded successfully", {})
                # Refresh model status in settings window
                if hasattr(self, "_settings_window") and self._settings_window:
                    self._settings_window.refresh_model_status()
        except Exception as e:
            app_logger.log_error(e, "_on_model_unload_requested")

    def _on_model_test_requested(self) -> None:
        """Handle model test request."""
        try:
            if self.ui_model_service:
                speech_engine = self.ui_model_service.get_whisper_engine()

                if not speech_engine:
                    QMessageBox.warning(
                        None,
                        QCoreApplication.translate("MainWindow", "Model Not Available"),
                        QCoreApplication.translate(
                            "MainWindow",
                            "Local speech engine is not initialized. Please load a model first.",
                        ),
                    )
                    return

                if not getattr(speech_engine, "is_model_loaded", False):
                    QMessageBox.warning(
                        None,
                        QCoreApplication.translate("MainWindow", "Model Not Loaded"),
                        QCoreApplication.translate(
                            "MainWindow",
                            "Please load a model first before testing.",
                        ),
                    )
                    return

                parent_widget = None

                progress = QProgressDialog(
                    QCoreApplication.translate("MainWindow", "Testing model..."),
                    QCoreApplication.translate("MainWindow", "Cancel"),
                    0,
                    0,
                    parent_widget,
                )
                progress.setWindowTitle(
                    QCoreApplication.translate("MainWindow", "Model Test")
                )
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumDuration(0)
                progress.setCancelButton(None)

                test_thread = ModelTestThread(speech_engine, self)

                def on_progress_update(message: str):
                    progress.setLabelText(message)

                def on_test_complete(success: bool, result: Dict[str, Any], error: str):
                    progress.close()

                    if success:
                        text_output = result.get(
                            "text",
                            QCoreApplication.translate(
                                "MainWindow", "No text detected"
                            ),
                        )
                        is_hallucination = result.get("is_hallucination", False)
                        confidence = result.get("confidence", 0)
                        detected_language = result.get("language", "unknown")

                        if is_hallucination:
                            analysis_text = QCoreApplication.translate(
                                "MainWindow",
                                "Analysis: Output '{text}' appears to be a Whisper hallucination from noise audio, which is normal behavior.",
                            ).format(text=text_output)
                        elif (
                            not text_output
                            or text_output
                            == QCoreApplication.translate(
                                "MainWindow", "No text detected"
                            )
                        ):
                            analysis_text = QCoreApplication.translate(
                                "MainWindow",
                                "Analysis: No text detected from test audio, which is expected.",
                            )
                        else:
                            analysis_text = QCoreApplication.translate(
                                "MainWindow",
                                "Analysis: Model produced text output from test audio.",
                            )

                        QMessageBox.information(
                            parent_widget,
                            QCoreApplication.translate(
                                "MainWindow", "Model Test Result"
                            ),
                            QCoreApplication.translate(
                                "MainWindow",
                                "**Model Test Successful!**\n\n"
                                "Model: {model}\n"
                                "Device: {device}\n"
                                "Detected Language: {language}\n"
                                "Test Output: '{output}'\n"
                                "Confidence: {confidence:.2f}\n\n"
                                "{analysis}\n\n"
                                "The model is working correctly and can process audio!",
                            ).format(
                                model=speech_engine.model_name,
                                device=speech_engine.device,
                                language=detected_language,
                                output=text_output,
                                confidence=confidence,
                                analysis=analysis_text,
                            ),
                        )
                    else:
                        QMessageBox.critical(
                            parent_widget,
                            QCoreApplication.translate(
                                "MainWindow", "Model Test Failed"
                            ),
                            QCoreApplication.translate(
                                "MainWindow",
                                "**Model Test Failed**\n\n"
                                "Error: {error}\n\n"
                                "Please check the model status and try again.",
                            ).format(error=error),
                        )

                test_thread.progress_update.connect(on_progress_update)
                test_thread.test_complete.connect(on_test_complete)

                progress.show()
                test_thread.start()

        except Exception as e:
            error_details = f"{type(e).__name__}: {str(e)}"
            app_logger.log_error(e, "_on_model_test_requested")
            QMessageBox.critical(
                None,
                QCoreApplication.translate("MainWindow", "Model Test Failed"),
                QCoreApplication.translate(
                    "MainWindow",
                    "**Model Test Failed**\n\n"
                    "Error: {error}\n\n"
                    "Please check the model status and try again.",
                ).format(error=error_details),
            )

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 最小化到系统托盘而不是真正关闭
        event.ignore()
        self.hide()

        # 可选：显示托盘通知
        if hasattr(self, "system_tray") and self.system_tray:
            self.system_tray.showMessage(
                QCoreApplication.translate("MainWindow", "Sonic Input"),
                QCoreApplication.translate(
                    "MainWindow", "Application minimized to tray"
                ),
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
