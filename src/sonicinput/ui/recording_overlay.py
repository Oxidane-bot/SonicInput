"""Recording Overlay Window - 重构版本使用组件化架构"""

from PySide6.QtCore import QCoreApplication, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QWidget

from ..core.interfaces import IConfigService
from ..core.services.config import ConfigKeys
from ..utils import app_logger
from .overlay import StatusIndicator
from .overlay_components import (
    AnimationController,
    AudioVisualizer,
    OverlayUIBuilder,
    TimerManager,
)


class RecordingOverlay(QWidget):
    """Recording Overlay Window with Thread-safe singleton pattern"""

    # Thread-safe singleton implementation
    _instance = None
    _initialized = False
    _creation_lock = None  # Python threading lock for reliable thread safety

    # 线程安全信号
    stop_recording_requested = Signal()
    show_recording_requested = Signal()
    hide_recording_requested = Signal()
    show_processing_requested = Signal()  # 显示处理状态
    show_completed_requested = Signal(int)  # 显示完成状态（参数：延迟毫秒）
    show_warning_requested = Signal(int)  # 显示警告状态（参数：延迟毫秒）
    show_error_requested = Signal(int)  # 显示错误状态（参数：延迟毫秒）
    set_status_requested = Signal(str)
    update_waveform_requested = Signal(object)
    update_audio_level_requested = Signal(float)  # 音频级别更新
    start_processing_animation_requested = Signal()
    stop_processing_animation_requested = Signal()
    hide_recording_delayed_requested = Signal(int)  # 延迟隐藏（毫秒）

    def __new__(cls, parent=None):
        """Thread-safe singleton pattern using Python threading"""
        # 初始化线程锁（只在首次需要时创建）
        if cls._creation_lock is None:
            import threading

            cls._creation_lock = threading.Lock()

        with cls._creation_lock:
            if cls._instance is None:
                try:
                    app_logger.log_audio_event(
                        "Creating new RecordingOverlay singleton instance", {}
                    )
                    cls._instance = super().__new__(cls)
                    app_logger.log_audio_event(
                        "RecordingOverlay singleton instance created successfully", {}
                    )
                except Exception as e:
                    app_logger.log_error(e, "RecordingOverlay_singleton_creation")
                    # 即使创建失败，也不要让整个应用崩溃
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, parent=None):
        """Qt-safe initialization (no locks needed - main thread only)"""
        # Prevent re-initialization
        if self._initialized:
            app_logger.log_audio_event(
                "RecordingOverlay already initialized, resetting for reuse", {}
            )
            try:
                self._reset_for_reuse()
            except Exception as e:
                app_logger.log_error(e, "RecordingOverlay_reset_for_reuse")
            return

        try:
            app_logger.log_audio_event("Starting RecordingOverlay initialization", {})
            super().__init__(parent)
            self._initialized = True
            app_logger.log_audio_event(
                "RecordingOverlay parent initialization completed", {}
            )
        except Exception as e:
            app_logger.log_error(e, "RecordingOverlay_parent_initialization")
            # 尝试基本的初始化
            try:
                super().__init__(parent)
                self._initialized = True
            except Exception as e2:
                app_logger.log_error(e2, "RecordingOverlay_fallback_initialization")
                raise

        try:
            app_logger.log_audio_event(
                "Setting up RecordingOverlay state variables", {}
            )
            # Phase 2: is_recording is now a computed property (see @property below)
            self.current_status = "Ready"
            self.recording_duration = 0
            self._state_manager = (
                None  # Phase 1: Optional StateManager injection for SSOT compliance
            )
            app_logger.log_audio_event(
                "RecordingOverlay state variables initialized", {}
            )
        except Exception as e:
            app_logger.log_error(e, "RecordingOverlay_state_setup")
            raise

        try:
            app_logger.log_audio_event(
                "Setting up RecordingOverlay window attributes", {}
            )
            # 设置窗口属性
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            app_logger.log_audio_event(
                "RecordingOverlay window attributes configured", {}
            )
        except Exception as e:
            app_logger.log_error(e, "RecordingOverlay_window_attributes")
            raise

        try:
            app_logger.log_audio_event("Starting RecordingOverlay UI setup", {})
            # 使用UIBuilder构建UI
            ui_builder = OverlayUIBuilder()
            ui_components = ui_builder.build_ui(self, self.request_stop_recording)

            # 设置UI组件属性
            self.background_frame = ui_components["background_frame"]
            self.status_indicator = ui_components["status_indicator"]
            self.audio_level_bars = ui_components["audio_level_bars"]
            self.title_label = ui_components["title_label"]
            self.time_label = ui_components["time_label"]
            self.close_button = ui_components["close_button"]
            self.stop_button = ui_components["stop_button"]
            self.position_manager = ui_components["position_manager"]
            self.current_audio_level = ui_components["current_audio_level"]
            self.config_service = None  # 将在set_config_service中设置

            app_logger.log_audio_event("RecordingOverlay UI setup completed", {})
        except Exception as e:
            app_logger.log_error(e, "RecordingOverlay_UI_setup")
            raise

        try:
            app_logger.log_audio_event("Initializing overlay components", {})

            # 初始化定时器管理器
            self.timer_manager = TimerManager()
            # 为了兼容性，保留对原定时器的引用
            self.update_timer = self.timer_manager.update_timer
            self.delayed_hide_timer = self.timer_manager.delayed_hide_timer

            # 连接定时器回调
            self.timer_manager.safe_connect(
                self.update_timer, self.update_recording_time, "recording_timer"
            )
            self.timer_manager.safe_connect(
                self.delayed_hide_timer, self._hide_recording_impl, "delayed_hide"
            )

            # 初始化动画控制器
            self.animation_controller = AnimationController(self)
            # 为了兼容性，保留对原动画的引用
            self.fade_animation = self.animation_controller.fade_animation
            self.breathing_timer = self.animation_controller.breathing_timer
            self.breathing_phase = self.animation_controller.breathing_phase
            self.is_processing = self.animation_controller.is_processing
            self.status_animation = self.animation_controller.status_animation
            self.status_opacity = self.animation_controller.status_opacity

            # 初始化音频可视化器（在audio_level_bars创建后）
            try:
                self.audio_visualizer = AudioVisualizer(self.audio_level_bars)
                app_logger.log_audio_event("AudioVisualizer initialized", {})
            except Exception as e:
                app_logger.log_error(e, "audio_visualizer_init")
                self.audio_visualizer = None

            app_logger.log_audio_event(
                "Overlay components initialized successfully", {}
            )

        except Exception as e:
            app_logger.log_error(e, "overlay_components_init")
            # 组件初始化失败不应阻止基本功能
            pass

        try:
            app_logger.log_audio_event(
                "Connecting RecordingOverlay thread-safe signals", {}
            )
            # 连接线程安全信号
            self.show_recording_requested.connect(self._show_recording_impl)
            self.hide_recording_requested.connect(self._hide_recording_impl)
            self.show_processing_requested.connect(self._show_processing_impl)
            self.show_completed_requested.connect(self._show_completed_impl)
            self.show_warning_requested.connect(self._show_warning_impl)
            self.show_error_requested.connect(self._show_error_impl)
            self.set_status_requested.connect(self._set_status_text_impl)
            self.update_waveform_requested.connect(self._update_waveform_impl)
            self.update_audio_level_requested.connect(self._update_audio_level_impl)
            self.start_processing_animation_requested.connect(
                self._start_processing_animation_impl
            )
            self.stop_processing_animation_requested.connect(
                self._stop_processing_animation_impl
            )
            self.hide_recording_delayed_requested.connect(
                self._hide_recording_delayed_impl
            )
            app_logger.log_audio_event(
                "RecordingOverlay all thread-safe signals connected", {}
            )
        except Exception as e:
            app_logger.log_error(e, "thread_safe_signals_connection")

        app_logger.log_audio_event(
            "Recording overlay initialized successfully", {"singleton_id": id(self)}
        )

    # ==================== 状态管理 ====================

    def _ensure_animation_state(self, should_animate: bool, context: str = ""):
        """确保动画状态与期望状态一致（简化版，委托给AnimationController）"""
        if not self.animation_controller:
            return

        try:
            if should_animate:
                self._start_processing_animation_impl()
            else:
                self._stop_processing_animation_impl()
        except Exception as e:
            app_logger.log_error(e, f"ensure_animation_state_{context}")

    def set_config_service(self, config_service: IConfigService) -> None:
        """设置配置服务"""
        self.config_service = config_service
        # 传递给PositionManager
        if hasattr(self, "position_manager"):
            self.position_manager.set_config_service(config_service)
        app_logger.log_audio_event("Config service set for overlay", {})

    def set_state_manager(self, state_manager) -> None:
        """Set StateManager for SSOT compliance (Phase 1: Injection only)

        Args:
            state_manager: StateManager instance for authoritative state queries
        """
        self._state_manager = state_manager
        app_logger.log_audio_event(
            "StateManager injected into RecordingOverlay",
            {"has_state_manager": self._state_manager is not None},
        )

    @property
    def is_recording(self) -> bool:
        """Is recording state (computed from StateManager - SSOT compliant)

        Returns:
            True if recording (STARTING or RECORDING), False otherwise
        """
        if self._state_manager is None:
            # Fallback during initialization or if StateManager not injected
            app_logger.log_audio_event(
                "WARNING: is_recording queried without StateManager",
                {"stack": False},  # Don't log stack by default to avoid spam
            )
            return False

        try:
            from ..core.interfaces.state import RecordingState

            recording_state = self._state_manager.get_recording_state()
            return recording_state in [
                RecordingState.STARTING,
                RecordingState.RECORDING,
            ]
        except Exception as e:
            app_logger.log_error(e, "is_recording_property_query")
            return False

    # Phase 4: Removed @is_recording.setter - Property is now read-only
    # Phase 4: Removed _get_authoritative_recording_state() - Use property directly

    def _reset_for_reuse(self) -> None:
        """重置overlay状态以支持稳定的多次使用（Qt main thread only）"""
        try:
            app_logger.log_audio_event(
                "Starting overlay reset for reuse",
                {
                    "singleton_id": id(self),
                    "is_visible": self.isVisible()
                    if hasattr(self, "isVisible")
                    else False,
                },
            )

            # 改进：立即停止所有动画和定时器，避免竞态条件
            self._force_stop_all_animations()

            # 短暂延迟让Qt事件循环处理
            from PySide6.QtCore import QTimer

            QTimer.singleShot(10, self._delayed_reset)

        except Exception as e:
            app_logger.log_error(e, "overlay_reset_for_reuse_initial")
            # 如果重置失败，尝试强制重置到基本状态
            try:
                # Phase 3: Removed `self.is_recording = False` - Queried from StateManager
                self.current_status = "Ready"
                if hasattr(self, "isVisible") and self.isVisible():
                    self.hide()
            except (RuntimeError, AttributeError):
                pass  # 忽略Qt对象已删除或属性不存在的错误

    def _force_stop_all_animations(self) -> None:
        """强制停止所有动画和定时器"""
        try:
            # 停止所有定时器
            timers_to_stop = ["update_timer", "breathing_timer", "delayed_hide_timer"]

            for timer_name in timers_to_stop:
                if hasattr(self, timer_name):
                    timer = getattr(self, timer_name)
                    if timer and hasattr(timer, "isActive"):
                        try:
                            if timer.isActive():
                                timer.stop()
                            # 立即删除定时器对象
                            timer.deleteLater()
                            setattr(self, timer_name, None)
                            app_logger.log_audio_event(
                                f"Force stopped and deleted {timer_name}", {}
                            )
                        except (RuntimeError, AttributeError):
                            # 对象可能已被删除
                            setattr(self, timer_name, None)

            # 停止动画
            if hasattr(self, "status_animation") and self.status_animation:
                try:
                    if self.status_animation.state() == QPropertyAnimation.Running:
                        self.status_animation.stop()
                    self.status_animation.deleteLater()
                    self.status_animation = None
                    app_logger.log_audio_event("Force stopped status animation", {})
                except (RuntimeError, AttributeError):
                    self.status_animation = None

        except Exception as e:
            app_logger.log_error(e, "force_stop_all_animations")

    def _delayed_reset(self) -> None:
        """延迟重置，确保Qt事件循环处理完成"""
        try:
            app_logger.log_audio_event("Starting delayed overlay reset", {})

            # 首先隐藏窗口，避免在重置过程中出现闪烁
            if hasattr(self, "isVisible") and self.isVisible():
                self.hide()
                app_logger.log_audio_event("Overlay hidden during delayed reset", {})

            # 重置所有状态变量
            # Phase 3: Removed `self.is_recording = False` - Queried from StateManager
            self.current_status = "Ready"
            self.recording_duration = 0
            self.breathing_phase = 0
            self.is_processing = False

            # 清理音频级别条状态
            if hasattr(self, "audio_level_bars"):
                try:
                    for bar in self.audio_level_bars:
                        if bar:
                            bar.setStyleSheet("""
                                QLabel {
                                    background-color: rgba(80, 80, 90, 100);
                                    border-radius: 2px;
                                }
                            """)
                except Exception as e:
                    app_logger.log_error(e, "reset_audio_level_bars")

            # 重新连接所有信号
            self._reconnect_signals()

            # 重置窗口属性
            self._reset_window_properties()

            app_logger.log_audio_event(
                "Recording overlay delayed reset completed", {"singleton_id": id(self)}
            )

        except Exception as e:
            app_logger.log_error(e, "delayed_reset")
            # 如果重置失败，尝试强制重置到基本状态
            try:
                # Phase 3: Removed `self.is_recording = False` - Queried from StateManager
                self.current_status = "Ready"
                if hasattr(self, "isVisible") and self.isVisible():
                    self.hide()
            except (RuntimeError, AttributeError):
                pass  # 忽略Qt对象已删除或属性不存在的错误

    def _cleanup_all_timers(self) -> None:
        """彻底清理所有定时器"""
        try:
            timers_to_cleanup = [
                ("update_timer", "update_recording_time"),
                ("breathing_timer", "update_breathing"),
                ("delayed_hide_timer", "_hide_recording_impl"),
                ("status_animation", None),  # QPropertyAnimation
            ]

            for timer_name, callback_name in timers_to_cleanup:
                if hasattr(self, timer_name):
                    timer = getattr(self, timer_name)
                    if timer:
                        try:
                            if hasattr(timer, "isActive") and timer.isActive():
                                timer.stop()
                                app_logger.log_audio_event(f"Stopped {timer_name}", {})

                            # 断开信号连接
                            if callback_name and hasattr(timer, "timeout"):
                                try:
                                    import warnings

                                    with warnings.catch_warnings():
                                        warnings.simplefilter("ignore", RuntimeWarning)
                                        timer.timeout.disconnect()
                                except (TypeError, RuntimeError):
                                    pass  # 信号未连接或对象已删除
                        except Exception as e:
                            app_logger.log_error(e, f"cleanup_timer_{timer_name}")

            app_logger.log_audio_event("All timers cleaned up", {})

        except Exception as e:
            app_logger.log_error(e, "cleanup_all_timers")

    def _reconnect_signals(self) -> None:
        """重新连接所有信号"""
        try:
            # 重新连接线程安全信号
            signal_connections = [
                (self.show_recording_requested, self._show_recording_impl),
                (self.hide_recording_requested, self._hide_recording_impl),
                (self.show_processing_requested, self._show_processing_impl),
                (self.show_completed_requested, self._show_completed_impl),
                (self.show_warning_requested, self._show_warning_impl),
                (self.show_error_requested, self._show_error_impl),
                (self.set_status_requested, self._set_status_text_impl),
                (self.update_waveform_requested, self._update_waveform_impl),
                (self.update_audio_level_requested, self._update_audio_level_impl),
                (
                    self.start_processing_animation_requested,
                    self._start_processing_animation_impl,
                ),
                (
                    self.stop_processing_animation_requested,
                    self._stop_processing_animation_impl,
                ),
                (
                    self.hide_recording_delayed_requested,
                    self._hide_recording_delayed_impl,
                ),
            ]

            for signal, slot in signal_connections:
                try:
                    # 先断开所有连接
                    signal.disconnect()
                except (TypeError, RuntimeError):
                    pass  # 信号未连接或对象已删除

                try:
                    # 重新连接
                    signal.connect(slot)
                except Exception as e:
                    app_logger.log_error(e, f"reconnect_signal_{signal}")

            app_logger.log_audio_event("Signals reconnected", {})

        except Exception as e:
            app_logger.log_error(e, "reconnect_signals")

    def _reset_window_properties(self) -> None:
        """重置窗口属性到初始状态"""
        try:
            # 重置窗口属性
            self.setWindowOpacity(1.0)

            # 重置样式
            if hasattr(self, "status_label") and self.status_label:
                self.status_label.setText(
                    QCoreApplication.translate("RecordingOverlay", "Ready")
                )
                self.status_label.setStyleSheet("color: #CCCCCC; font-weight: bold;")

            # 确保窗口标志正确
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )

            app_logger.log_audio_event("Window properties reset", {})

        except Exception as e:
            app_logger.log_error(e, "reset_window_properties")

    @classmethod
    def reset_singleton(cls) -> None:
        """强制重置单例实例（仅在极端情况下使用，Qt main thread only）"""
        try:
            if cls._instance is not None:
                app_logger.log_audio_event("Force resetting overlay singleton", {})
                # 尝试清理现有实例
                try:
                    if hasattr(cls._instance, "update_timer"):
                        cls._instance.update_timer.stop()
                    if hasattr(cls._instance, "breathing_timer"):
                        cls._instance.breathing_timer.stop()
                    if cls._instance.isVisible():
                        cls._instance.hide()
                except (RuntimeError, AttributeError):
                    pass  # 忽略清理错误（对象已删除或属性不存在）

                cls._instance = None
                cls._initialized = False
                app_logger.log_audio_event("Overlay singleton reset completed", {})
        except Exception as e:
            app_logger.log_error(e, "force_reset_singleton")

    # setup_overlay_ui方法已迁移到OverlayUIBuilder类

    def show_recording(self) -> None:
        """Show recording status - Thread-safe public interface"""
        self.show_recording_requested.emit()

    def request_stop_recording(self) -> None:
        """Request recording stop from the owning application."""
        self.stop_recording_requested.emit()

    def _show_recording_impl(self) -> None:
        """Show recording status - Internal implementation (Qt main thread only)

        Event-driven design: RECORDING_STARTED event semantics = "show recording UI"
        No state checks needed - Qt's show() is idempotent (safe to call multiple times)
        """
        # Removed visibility/state checks - let event semantics drive behavior
        # RECORDING_STARTED event = display recording UI (period)
        # Qt show() is idempotent - no side effects from repeated calls

        self.recording_duration = 0

        # 更新状态指示器为录音状态（红色）
        try:
            self.status_indicator.set_state(StatusIndicator.STATE_RECORDING)
            self.title_label.setText(
                QCoreApplication.translate("RecordingOverlay", "Recording")
            )
            self.time_label.setText("00:00")
        except Exception as e:
            app_logger.log_error(e, "status_update_show")

        # 立即激活音频可视化条（显示微小初始值）
        # 这样用户看到窗口时可视化条就已经是激活状态，避免延迟感
        try:
            if self.audio_visualizer:
                # 设置一个小的初始音频级别（约10%），显示1-2个绿色条
                # 这会让用户感觉可视化器和窗口同时出现
                # Phase 4: Removed is_recording parameter - caller controls when to update
                self.audio_visualizer.update_audio_level(0.002)
                app_logger.log_audio_event(
                    "Audio visualizer pre-activated with initial level", {}
                )
        except Exception as e:
            app_logger.log_error(e, "audio_visualizer_preactivate")

        # 启动录音计时器（使用TimerManager组件）
        try:
            if self.timer_manager:
                app_logger.log_audio_event(
                    "Starting recording timer",
                    {
                        "is_recording": self.is_recording,
                        "duration": self.recording_duration,
                    },
                )
                self.timer_manager.start_update_timer(self.update_recording_time)
                app_logger.log_audio_event("Recording timer started successfully", {})
            else:
                app_logger.log_audio_event(
                    "WARNING: timer_manager is None, cannot start timer", {}
                )
        except Exception as e:
            app_logger.log_error(e, "timer_start_show")

        # 恢复位置（在显示窗口前）
        if self.config_service:
            self.position_manager.restore_position()

        # 显示窗口
        try:
            self.show()
            self.raise_()
            # self.activateWindow()
        except Exception as e:
            app_logger.log_error(e, "widget_show")

        # 淡入动画（使用AnimationController组件）
        try:
            if self.animation_controller:
                self.animation_controller.start_fade_in()
        except Exception as e:
            app_logger.log_error(e, "fade_animation_show")

        app_logger.log_audio_event("Recording overlay shown", {})

    def hide_recording(self) -> None:
        """Hide recording status - Thread-safe public interface"""
        self.hide_recording_requested.emit()

    def show_completed(self, delay_ms: int = 500) -> None:
        """显示完成状态，然后延迟隐藏 - Thread-safe public interface

        Args:
            delay_ms: 延迟隐藏的毫秒数，默认500ms（0.5秒）
        """
        self.show_completed_requested.emit(delay_ms)

    def _show_completed_impl(self, delay_ms: int) -> None:
        """显示完成状态的内部实现 - Internal implementation (Qt main thread only)"""
        try:
            # 切换到完成状态（绿色）
            self.status_indicator.set_state(StatusIndicator.STATE_COMPLETED)
            self.title_label.setText(
                QCoreApplication.translate("RecordingOverlay", "Completed")
            )

            # 取消旧的延迟隐藏定时器（避免多个定时器冲突）
            if self.delayed_hide_timer.isActive():
                self.delayed_hide_timer.stop()

            # 启动新的延迟隐藏定时器
            self.delayed_hide_timer.start(delay_ms)
        except Exception as e:
            app_logger.log_error(e, "_show_completed_impl")

    def show_warning(self, delay_ms: int = 1500) -> None:
        """显示警告状态，然后延迟隐藏 - Thread-safe public interface

        用于AI优化失败但流程继续的情况

        Args:
            delay_ms: 延迟隐藏的毫秒数，默认1500ms（1.5秒）
        """
        self.show_warning_requested.emit(delay_ms)

    def _show_warning_impl(self, delay_ms: int) -> None:
        """显示警告状态的内部实现 - Internal implementation (Qt main thread only)"""
        try:
            # 切换到警告状态（橙色）
            self.status_indicator.set_state(StatusIndicator.STATE_WARNING)
            self.title_label.setText(
                QCoreApplication.translate("RecordingOverlay", "Warning")
            )

            # 取消旧的延迟隐藏定时器（避免多个定时器冲突）
            if self.delayed_hide_timer.isActive():
                self.delayed_hide_timer.stop()

            # 启动新的延迟隐藏定时器
            self.delayed_hide_timer.start(delay_ms)
        except Exception as e:
            app_logger.log_error(e, "_show_warning_impl")

    def show_error(self, delay_ms: int = 2000) -> None:
        """显示错误状态，然后延迟隐藏 - Thread-safe public interface

        用于致命错误的情况

        Args:
            delay_ms: 延迟隐藏的毫秒数，默认2000ms（2秒）
        """
        self.show_error_requested.emit(delay_ms)

    def _show_error_impl(self, delay_ms: int) -> None:
        """显示错误状态的内部实现 - Internal implementation (Qt main thread only)"""
        try:
            # 切换到错误状态（深红色）
            self.status_indicator.set_state(StatusIndicator.STATE_ERROR)
            self.title_label.setText(
                QCoreApplication.translate("RecordingOverlay", "Error")
            )

            # 取消旧的延迟隐藏定时器（避免多个定时器冲突）
            if self.delayed_hide_timer.isActive():
                self.delayed_hide_timer.stop()

            # 启动新的延迟隐藏定时器
            self.delayed_hide_timer.start(delay_ms)
        except Exception as e:
            app_logger.log_error(e, "_show_error_impl")

    def show_processing(self) -> None:
        """显示AI处理状态（黄色）- Thread-safe public interface"""
        self.show_processing_requested.emit()

    def _show_processing_impl(self) -> None:
        """显示AI处理状态的内部实现 - Internal implementation (Qt main thread only)"""
        try:
            # 设置处理状态（黄色）
            self.status_indicator.set_state(StatusIndicator.STATE_PROCESSING)
            self.title_label.setText(
                QCoreApplication.translate("RecordingOverlay", "Processing")
            )

            # 停止录音计时器（录音已结束）
            # Phase 3: Removed `self.is_recording = False` - State already IDLE in StateManager
            if self.timer_manager:
                self.timer_manager.stop_update_timer(self.update_recording_time)

            # 取消之前的延迟隐藏定时器
            # 悬浮窗现在由事件控制（TEXT_INPUT_COMPLETED 或错误事件）
            if self.delayed_hide_timer.isActive():
                self.delayed_hide_timer.stop()
        except Exception as e:
            app_logger.log_error(e, "_show_processing_impl")

    def _hide_recording_impl(self) -> None:
        """Hide recording status - Internal implementation (Qt main thread only)"""
        # 检查窗口是否真的可见，而不是检查 is_recording 状态
        if not self.isVisible():
            # 窗口已经隐藏，无需重复操作
            return

        # Phase 3: Removed `self.is_recording = False` - State managed by StateManager

        # 停止所有计时器（使用TimerManager组件）
        try:
            if self.timer_manager:
                self.timer_manager.stop_update_timer(self.update_recording_time)

            if self.animation_controller:
                self.animation_controller.stop_breathing_animation()
        except Exception as e:
            app_logger.log_error(e, "components_cleanup_hide")

        # 重置所有状态
        self.recording_duration = 0
        self.breathing_phase = 0
        self.is_processing = False

        # 重置音频级别条显示（使用AudioVisualizer组件）
        try:
            if self.audio_visualizer:
                self.audio_visualizer.reset_level_bars()
            self.current_audio_level = 0.0
        except Exception as e:
            app_logger.log_error(e, "audio_visualizer_reset_hide")

        # 重置计时器显示
        try:
            self.time_label.setText("00:00")
        except Exception as e:
            app_logger.log_error(e, "time_label_reset_hide")

        # 不重置状态指示器 - 状态由下次 show_recording 或 show_completed 设置

        # 直接隐藏窗口，不使用淡出动画
        # 移除复杂的淡出动画逻辑以避免信号竞态条件导致的闪退
        try:
            self._safe_hide()
        except Exception as e:
            app_logger.log_error(e, "direct_hide")
            # 强制隐藏
            self.hide()

        app_logger.log_audio_event("Recording overlay hidden", {})

        # 保存位置（如果有配置服务且开启自动保存）
        if self.config_service and self.config_service.get_setting(
            ConfigKeys.UI_OVERLAY_POSITION_AUTO_SAVE, True
        ):
            self.position_manager.save_position()

    def _safe_hide(self) -> None:
        """Safely hide the widget with error handling"""
        try:
            if self.isVisible():
                self.hide()
        except Exception as e:
            app_logger.log_error(e, "safe_hide_widget")

    def hide_recording_delayed(self, delay_ms: int = 1000) -> None:
        """延迟隐藏录音状态 - Thread-safe public interface"""
        self.hide_recording_delayed_requested.emit(delay_ms)

    def _hide_recording_delayed_impl(self, delay_ms: int) -> None:
        """延迟隐藏录音状态 - Internal implementation (via signal)"""
        try:
            # 取消旧的延迟隐藏定时器（避免多个定时器冲突）
            if self.delayed_hide_timer.isActive():
                self.delayed_hide_timer.stop()

            # 启动新的延迟隐藏定时器
            self.delayed_hide_timer.start(delay_ms)
        except Exception as e:
            app_logger.log_error(e, "_hide_recording_delayed_impl")

    def update_waveform(self, audio_data) -> None:
        """Update waveform display - Thread-safe public interface"""
        self.update_waveform_requested.emit(audio_data)

    def _update_waveform_impl(self, audio_data) -> None:
        """Update audio level display - Internal implementation (Performance optimized)"""
        # 优化: 缓存is_recording检查
        is_currently_recording = self.is_recording

        if is_currently_recording and audio_data is not None:
            try:
                import numpy as np

                # 计算音频级别 (RMS)
                if hasattr(audio_data, "__len__") and len(audio_data) > 0:
                    if isinstance(audio_data, np.ndarray):
                        level = float(np.sqrt(np.mean(audio_data**2)))
                    else:
                        level = float(abs(sum(audio_data)) / len(audio_data))

                    # 标准化到 0-1 范围 - 大幅提高敏感度让正常说话音量也能显示
                    level = min(1.0, max(0.0, level * 20))  # 提高敏感度到20倍（从8倍）
                    self.current_audio_level = level

                    # 调试日志：每秒记录一次音量级别（已禁用，避免日志洪流）
                    # if not hasattr(self, '_last_audio_log_time'):
                    #     self._last_audio_log_time = 0
                    # import time
                    # current_time = time.time()
                    # if current_time - self._last_audio_log_time >= 1.0:
                    #     app_logger.log_audio_event("Audio level update", {
                    #         "raw_level": f"{raw_level:.6f}",
                    #         "normalized_level": f"{level:.4f}",
                    #         "sensitivity_multiplier": 20
                    #     })
                    #     self._last_audio_log_time = current_time

                    # 更新音频级别条
                    self._update_audio_level_bars(level)
            except Exception:
                # 如果计算失败，使用默认的随机级别模拟
                pass

    def update_audio_level(self, level: float) -> None:
        """Update audio level display - Thread-safe public interface"""
        self.update_audio_level_requested.emit(level)

    def _update_audio_level_impl(self, level: float) -> None:
        """Update audio level bars - Internal implementation (Performance optimized)"""
        # 优化: 缓存is_recording检查
        is_currently_recording = self.is_recording

        # Phase 4: Guard moved to caller - only call when recording
        if self.audio_visualizer and is_currently_recording:
            self.audio_visualizer.update_audio_level(level)
            # 更新本地引用以保持兼容性
            self.current_audio_level = self.audio_visualizer.get_current_level()
        elif self.audio_visualizer:
            # Fallback: 如果visualizer未初始化，保持兼容性
            self.current_audio_level = min(1.0, max(0.0, level * 20))

    def set_status_text(self, text: str) -> None:
        """Set status text - Thread-safe public interface"""
        self.set_status_requested.emit(text)

    def _set_status_text_impl(self, text: str) -> None:
        """Set status text - Internal implementation (Qt main thread only)"""
        self.current_status = text
        # 新设计中不显示文本，只通过颜色指示状态

        # 根据状态改变颜色和启动/停止动画，包括定时器管理
        # 状态管理：确保动画状态与文本状态同步
        if "error" in text.lower():
            self._ensure_animation_state(False, "error_state")
            self._stop_timer_if_needed()
        elif "processing" in text.lower() or "ai" in text.lower():
            self._ensure_animation_state(True, "processing_state")
            self._stop_timer_if_needed()  # 处理时停止录音计时
        elif "recording" in text.lower():
            self._ensure_animation_state(False, "recording_state")
            # 录音状态保持计时器运行
        elif "inputting" in text.lower():
            self._ensure_animation_state(True, "inputting_state")
            self._stop_timer_if_needed()  # 输入时停止录音计时
        elif "completed" in text.lower():
            self._ensure_animation_state(False, "completed_state")
            self._stop_timer_if_needed()  # 完成时停止录音计时
        elif "stopped" in text.lower() or "idle" in text.lower():
            self._ensure_animation_state(False, "idle_state")
            self._stop_timer_if_needed()  # 停止时停止录音计时
        else:
            self._ensure_animation_state(False, "default_state")
            self._stop_timer_if_needed()

        # 状态指示器现在由 set_state(), show_processing(), show_completed() 直接管理
        # 不再通过文本推断状态

    def _stop_timer_if_needed(self) -> None:
        """Stop recording timer when not in recording state"""
        try:
            if hasattr(self, "update_timer") and self.update_timer.isActive():
                if (
                    not self.is_recording
                    or "recording" not in self.current_status.lower()
                ):
                    self.update_timer.stop()
                    # 断开计时器连接
                    try:
                        self.update_timer.timeout.disconnect(self.update_recording_time)
                    except (TypeError, RuntimeError):
                        pass  # 信号未连接或对象已删除
        except Exception as e:
            app_logger.log_error(e, "stop_timer_if_needed")

    def update_recording_time(self) -> None:
        """Update recording time (Qt main thread only) - Performance optimized"""
        # 优化: 缓存属性调用结果,避免每秒查询StateManager
        is_currently_recording = self.is_recording

        if is_currently_recording:
            self.recording_duration += 1
            minutes = self.recording_duration // 60
            seconds = self.recording_duration % 60
            try:
                # 优化: 复用格式化字符串,避免重复计算
                time_str = f"{minutes:02d}:{seconds:02d}"
                self.time_label.setText(time_str)
                # 只在前几次更新时记录日志，避免日志过多
                if self.recording_duration <= 3:
                    app_logger.log_audio_event(
                        "Recording time updated",
                        {
                            "duration": self.recording_duration,
                            "display": time_str,
                        },
                    )
            except Exception as e:
                app_logger.log_error(e, "update_recording_time")
        else:
            # If not recording, stop the timer immediately
            app_logger.log_audio_event(
                "Recording timer callback called but is_recording is False - stopping timer",
                {"duration": self.recording_duration},
            )
            try:
                if hasattr(self, "update_timer") and self.update_timer.isActive():
                    self.update_timer.stop()
                    try:
                        self.update_timer.timeout.disconnect(self.update_recording_time)
                    except (TypeError, RuntimeError):
                        pass  # 信号未连接或对象已删除
            except Exception as e:
                app_logger.log_error(e, "stop_timer_in_update")

    def center_on_screen(self) -> None:
        """Center on screen - Delegate to PositionManager"""
        self.position_manager.center_on_screen()

    def set_position(self, position: str) -> None:
        """Set window position - Delegate to PositionManager"""
        self.position_manager.set_preset_position(position)

    def mousePressEvent(self, event):
        """鼠标按下事件 - 用于拖拽窗口"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 拖拽窗口"""
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 拖拽结束后保存位置"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 拖拽结束后保存位置
            if self.config_service and self.config_service.get_setting(
                ConfigKeys.UI_OVERLAY_POSITION_AUTO_SAVE, True
            ):
                self.position_manager.save_position()
            event.accept()

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_recording()
        elif event.key() == Qt.Key.Key_Space:
            self.hide_recording()  # Space键也可以关闭悬浮窗

    # ==================== 动画系统 ====================

    def start_processing_animation(self) -> None:
        """启动处理动画 - Thread-safe public interface"""
        self.start_processing_animation_requested.emit()

    def _start_processing_animation_impl(self) -> None:
        """启动呼吸动画 - Internal implementation (使用AnimationController组件)"""
        if self.animation_controller:
            self.animation_controller.start_breathing_animation()
            # 同步状态以保持兼容性
            self.is_processing = self.animation_controller.is_processing
            self.breathing_phase = self.animation_controller.breathing_phase

    def stop_processing_animation(self) -> None:
        """停止处理动画 - Thread-safe public interface"""
        self.stop_processing_animation_requested.emit()

    def _stop_processing_animation_impl(self) -> None:
        """停止呼吸动画 - Internal implementation (使用AnimationController组件)"""
        if self.animation_controller:
            self.animation_controller.stop_breathing_animation()
            # 同步状态以保持兼容性
            self.is_processing = self.animation_controller.is_processing
            self.breathing_phase = self.animation_controller.breathing_phase

    def update_breathing(self) -> None:
        """更新呼吸效果（委托给AnimationController）"""
        # 这个方法现在由AnimationController内部调用，这里保留是为了兼容性
        # 实际的呼吸动画逻辑已经在AnimationController._update_breathing中实现
        pass

    def paintEvent(self, event):
        """重写绘制事件（已禁用呼吸发光效果）"""
        super().paintEvent(event)
        # 绿色呼吸光晕效果已被移除，保持界面简洁

    # Position management methods delegated to PositionManager
    # See recording_overlay_utils/position_manager.py for implementation

    def cleanup_resources(self) -> None:
        """清理UI资源 - 防止内存泄漏"""
        try:
            # 停止所有定时器
            timers = [
                ("update_timer", self.update_timer),
                ("breathing_timer", self.breathing_timer),
                ("delayed_hide_timer", self.delayed_hide_timer),
            ]

            for timer_name, timer in timers:
                if hasattr(self, timer_name) and timer:
                    if timer.isActive():
                        timer.stop()

                    # 彻底断开信号连接
                    import warnings

                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        timer.timeout.disconnect()

                    # 标记为删除
                    timer.deleteLater()
                    setattr(self, timer_name, None)

            # 清理图形效果
            if hasattr(self, "background_frame") and self.background_frame:
                graphics_effect = self.background_frame.graphicsEffect()
                if graphics_effect:
                    graphics_effect.deleteLater()
                    self.background_frame.setGraphicsEffect(None)

            # 清理音频级别条
            if hasattr(self, "audio_level_bars"):
                for bar in self.audio_level_bars:
                    if bar:
                        bar.deleteLater()
                self.audio_level_bars.clear()

            # 断开所有信号连接
            try:
                self.disconnect()
            except Exception as e:
                app_logger.log_error(
                    e,
                    "overlay_disconnect_signals_failed",
                    {
                        "context": "Failed to disconnect RecordingOverlay signals during cleanup"
                    },
                )

            app_logger.log_audio_event(
                "RecordingOverlay resources cleaned up successfully", {}
            )

        except Exception as e:
            app_logger.log_error(e, "RecordingOverlay_cleanup_resources")

    def cleanup(self) -> None:
        """清理所有资源 - 优雅关闭入口"""
        try:
            app_logger.log_audio_event("RecordingOverlay cleanup started", {})

            # 1. 停止所有定时器
            self._cleanup_all_timers()

            # 2. 停止所有动画
            if hasattr(self, "fade_animation") and self.fade_animation:
                self.fade_animation.stop()

            # 3. 隐藏窗口
            if self.isVisible():
                self.hide()

            app_logger.log_audio_event("RecordingOverlay cleanup completed", {})

        except Exception as e:
            app_logger.log_error(e, "recording_overlay_cleanup")

    def close(self) -> bool:
        """重写close方法，确保清理"""
        try:
            self.cleanup()
            return super().close()
        except Exception as e:
            app_logger.log_error(e, "recording_overlay_close")
            return False
