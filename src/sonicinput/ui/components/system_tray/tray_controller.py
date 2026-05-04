"""System tray controller - Business logic component

Handles the business logic for system tray operations including:
- State management
- Event handling
- Notification logic
- Integration with other services
"""

import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtWidgets import QSystemTrayIcon

from ....core.interfaces import EventPriority, IEventService
from ....core.interfaces.config import IConfigService
from ....core.services.config.config_keys import ConfigKeys
from ....core.services.events import Events
from ....core.interfaces.state import AppState, IStateManager, RecordingState
from ....utils import app_logger
from .tray_widget import TrayWidget


class TrayController(QObject):
    """System tray controller

    Manages system tray business logic and coordinates between
    the tray widget and application services.

    Note: Inherits from QObject to support Qt signals.
    Implements LifecycleComponent pattern manually to avoid metaclass conflicts.
    """

    # Business logic signals
    show_settings_requested = Signal()
    toggle_recording_requested = Signal()
    exit_application_requested = Signal()

    def __init__(
        self,
        config_service: Optional[IConfigService] = None,
        event_service: Optional[IEventService] = None,
        state_manager: Optional[IStateManager] = None,
        parent: Optional[QObject] = None,
    ):
        # Initialize QObject
        super().__init__(parent)

        # Initialize lifecycle state (manual implementation)
        self._component_name = "tray_controller"
        self._is_running = False

        # Import here to avoid circular import
        import threading

        self._lock = threading.RLock()

        # Store dependencies
        self._config_service = config_service
        self._event_service = event_service
        self._state_manager = state_manager
        self._parent = parent

        # UI widget
        self._tray_widget: Optional[TrayWidget] = None
        self._about_window = None

        # State tracking
        self._recording_state = RecordingState.IDLE
        self._app_state = AppState.IDLE
        self._notifications_enabled = True
        self._last_trigger_time = 0.0

    # ==================== Lifecycle Methods (manual implementation) ====================

    def start(self) -> bool:
        """Start the component"""
        if self._is_running:
            return True

        try:
            # Initialize
            if not self._do_initialize({}):
                return False

            # Start
            if not self._do_start():
                return False

            self._is_running = True
            return True
        except Exception as e:
            app_logger.log_error(e, f"{self._component_name}_start")
            return False

    def stop(self) -> bool:
        """Stop the component"""
        if not self._is_running:
            return True

        try:
            # Stop
            if not self._do_stop():
                return False

            # Cleanup
            self._do_cleanup()

            self._is_running = False
            return True
        except Exception as e:
            app_logger.log_error(e, f"{self._component_name}_stop")
            return False

    def cleanup(self) -> None:
        """Clean up resources (backward compatible entrypoint)."""
        self.stop()

    @property
    def is_running(self) -> bool:
        """Check if component is running"""
        return self._is_running

    def _handle_exception(self, exc: Exception, context: str) -> None:
        """Handle exception in component"""
        app_logger.log_error(exc, f"{self._component_name}_{context}")

    def _log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log component event"""
        app_logger.log_audio_event(
            event_type, {**data, "component": self._component_name}
        )

    def _load_config_setting(self, key: str, default: Any) -> Any:
        """Load configuration setting with default fallback"""
        if self._config_service:
            return self._config_service.get_setting(key, default)
        return default

    # ==================== Lifecycle Implementation ====================

    def _do_initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the tray controller

        Args:
            config: Initialization configuration

        Returns:
            True if initialization successful
        """
        # Load configuration
        self._load_configuration()

        # Create UI widget
        self._tray_widget = TrayWidget()

        # Check if tray widget was successfully created (system tray available)
        if not self._tray_widget.is_tray_available():
            self._log_event(
                "system_tray_not_available",
                {"message": "System tray not available, continuing without tray"},
            )
            # Even if tray is not available, we consider this a successful initialization
            # The controller can still handle events and provide functionality
        else:
            # Connect UI events to business logic only if tray is available
            self._connect_widget_signals()

            # Show startup notification only if tray is available
            self._show_startup_notification()

        # Subscribe to application events (regardless of tray availability)
        self._subscribe_to_events()

        return True

    def _do_start(self) -> bool:
        """Start the tray controller

        Returns:
            True if start successful
        """
        # Show tray icon
        if self._tray_widget:
            self._tray_widget.show()

        return True

    def _do_stop(self) -> bool:
        """Stop the tray controller

        Returns:
            True if stop successful
        """
        # Hide tray icon
        if self._tray_widget:
            self._tray_widget.hide()

        return True

    def _do_cleanup(self) -> None:
        """Clean up resources"""
        # Unsubscribe from events
        self._unsubscribe_from_events()

        # Clean up widget
        if self._tray_widget:
            self._tray_widget.cleanup()
            self._tray_widget = None

    def _get_component_health(self) -> Dict[str, Any]:
        """Get component-specific health information

        Returns:
            Dictionary of component-specific health data
        """
        widget_created = self._tray_widget is not None
        widget_available = widget_created and self._tray_widget.is_tray_available()

        return {
            "widget_created": widget_created,
            "widget_available": widget_available,
            "widget_visible": (
                self._tray_widget.is_visible() if self._tray_widget else False
            ),
            "notifications_enabled": self._notifications_enabled,
            "recording_state": self._recording_state.value,
            "app_state": self._app_state.value,
        }

    # ==================== Configuration ====================

    def _load_configuration(self) -> None:
        """Load configuration settings"""
        # Load notification settings using base class helper
        self._notifications_enabled = self._load_config_setting(
            ConfigKeys.UI_TRAY_NOTIFICATIONS, True
        )

    # ==================== Event Handling ====================

    def _connect_widget_signals(self) -> None:
        """Connect widget signals to business logic"""
        if not self._tray_widget:
            return

        # Connect icon activation
        self._tray_widget.icon_activated.connect(self._on_icon_activated)

        # Connect menu actions
        self._tray_widget.menu_action_triggered.connect(self._on_menu_action)

    def _subscribe_to_events(self) -> None:
        """Subscribe to application events"""
        if not self._event_service:
            return

        try:
            # Subscribe to recording state changes
            self._event_service.subscribe(
                Events.RECORDING_STATE_CHANGED,
                self._on_recording_state_changed,
                priority=EventPriority.HIGH,
            )

            # Subscribe to app state changes
            self._event_service.subscribe(
                Events.APP_STATE_CHANGED,
                self._on_app_state_changed,
                priority=EventPriority.HIGH,
            )

            # Subscribe to processing events
            self._event_service.subscribe(
                Events.TRANSCRIPTION_STARTED,
                self._on_processing_started,
                priority=EventPriority.NORMAL,
            )

            self._event_service.subscribe(
                Events.TRANSCRIPTION_COMPLETED,
                self._on_processing_completed,
                priority=EventPriority.NORMAL,
            )

            self._event_service.subscribe(
                Events.TRANSCRIPTION_ERROR,
                self._on_processing_failed,
                priority=EventPriority.NORMAL,
            )

            self._event_service.subscribe(
                Events.UI_LANGUAGE_CHANGED,
                self._on_language_changed,
                priority=EventPriority.NORMAL,
            )

        except Exception as e:
            self._handle_exception(e, "subscribe_to_events")
            # Re-raise the exception to cause initialization to fail
            raise

    def _unsubscribe_from_events(self) -> None:
        """Unsubscribe from application events"""
        if not self._event_service:
            return

        # Unsubscribe all events for this component
        events_to_unsubscribe = [
            Events.RECORDING_STATE_CHANGED,
            Events.APP_STATE_CHANGED,
            Events.TRANSCRIPTION_STARTED,
            Events.TRANSCRIPTION_COMPLETED,
            Events.TRANSCRIPTION_ERROR,
            Events.UI_LANGUAGE_CHANGED,
        ]

        for event in events_to_unsubscribe:
            try:
                self._event_service.unsubscribe_all(event)
            except Exception as e:
                self._handle_exception(e, f"unsubscribe_event_{event}")

    def _on_icon_activated(self, reason) -> None:
        """Handle tray icon activation

        Args:
            reason: Activation reason from Qt
        """
        try:
            with self._lock:
                # Extract integer value from PySide6 enum (uses .value attribute)
                reason_value = reason.value if hasattr(reason, "value") else int(reason)

                # Handle different activation types
                if reason_value == 2:  # DoubleClick
                    app_logger.log_audio_event(
                        "Processing double-click event", {"action": "show_settings"}
                    )
                    self._handle_show_settings()
                elif reason_value == 3:  # Trigger (single click on Windows)
                    now = time.time()
                    if now - self._last_trigger_time <= 0.4:
                        app_logger.log_audio_event(
                            "Processing trigger double-click",
                            {"action": "show_settings"},
                        )
                        self._handle_show_settings()
                    self._last_trigger_time = now
                elif reason_value == 4:  # MiddleClick
                    app_logger.log_audio_event(
                        "Processing middle-click event", {"action": "toggle_recording"}
                    )
                    self._handle_toggle_recording()

                # 详细日志记录激活事件
                app_logger.log_audio_event(
                    "Tray icon activation detailed",
                    {
                        "reason_raw": reason,  # 让 logger 序列化器处理枚举
                        "reason_value": reason_value,
                        "reason_type": type(reason).__name__,
                        "component": self._component_name,
                    },
                )

                app_logger.log_audio_event(
                    "Tray icon activated",
                    {"reason": reason_value, "component": self._component_name},
                )

        except Exception as e:
            self._handle_exception(e, "icon_activation")
            # Fallback: show settings
            self._handle_show_settings()

    def _on_menu_action(self, action_name: str) -> None:
        """Handle menu action triggered

        Args:
            action_name: Name of the triggered action
        """
        try:
            with self._lock:
                if action_name == "toggle_recording":
                    self._handle_toggle_recording()
                elif action_name == "show_settings":
                    self._handle_show_settings()
                elif action_name == "show_about":
                    self._handle_show_about()
                elif action_name == "exit_application":
                    self._handle_exit_application()

                app_logger.log_audio_event(
                    "Tray menu action triggered",
                    {"action": action_name, "component": self._component_name},
                )

        except Exception as e:
            app_logger.log_error(e, f"tray_menu_action_{action_name}")

    # ==================== Business Logic Handlers ====================

    def _handle_toggle_recording(self) -> None:
        """Handle recording toggle request"""
        self.toggle_recording_requested.emit()

    def _handle_show_settings(self) -> None:
        """Handle show settings request"""
        app_logger.log_audio_event(
            "Show settings handler called",
            {
                "component": self._component_name,
                "signal_about_to_emit": "show_settings_requested",
            },
        )
        self.show_settings_requested.emit()
        app_logger.log_audio_event(
            "Show settings signal emitted", {"component": self._component_name}
        )

    def _handle_show_about(self) -> None:
        """Handle show about request"""
        self._show_about_dialog()

    def _handle_exit_application(self) -> None:
        """Handle exit application request"""
        self.exit_application_requested.emit()

    # ==================== State Event Handlers ====================

    def _on_recording_state_changed(self, event_data: Dict[str, Any] = None) -> None:
        """Handle recording state change

        Args:
            event_data: Event data containing new state (optional)
        """
        try:
            if not event_data:
                return

            new_state = event_data.get("new_state")
            if new_state:
                self._recording_state = new_state
                self._update_ui_for_recording_state()

        except Exception as e:
            app_logger.log_error(e, "recording_state_change_handler")

    def _on_app_state_changed(self, event_data: Dict[str, Any] = None) -> None:
        """Handle app state change

        Args:
            event_data: Event data containing new state (optional)
        """
        try:
            if not event_data:
                return

            new_state = event_data.get("new_state")
            if new_state:
                self._app_state = new_state
                self._update_ui_for_app_state()

        except Exception as e:
            app_logger.log_error(e, "app_state_change_handler")

    def _on_language_changed(self, event_data: Dict[str, Any] = None) -> None:
        """Handle runtime UI language change."""
        if not self._tray_widget:
            return

        self._tray_widget.retranslate_ui()
        self._refresh_tray_text()

    def _refresh_tray_text(self) -> None:
        """Refresh tray tooltip and labels without triggering notifications."""
        if not self._tray_widget:
            return
        recording = self._recording_state == RecordingState.RECORDING
        self._tray_widget.set_tooltip(self._get_tray_tooltip(recording))

        if recording:
            self._tray_widget.update_status_text(
                QCoreApplication.translate("TrayController", "Recording...")
            )
            self._tray_widget.update_recording_action_text(
                QCoreApplication.translate("TrayController", "Stop Recording")
            )
        else:
            self._update_ui_for_app_state()
            self._tray_widget.update_recording_action_text(
                QCoreApplication.translate("TrayController", "Start Recording")
            )

    def _on_processing_started(self, event_data: Dict[str, Any] = None) -> None:
        """Handle processing started event

        Args:
            event_data: Optional event data (may be None if no data provided)
        """
        if self._tray_widget:
            self._tray_widget.update_status_text(
                QCoreApplication.translate("TrayController", "Processing...")
            )

    def _on_processing_completed(self, event_data: Dict[str, Any] = None) -> None:
        """Handle processing completed event

        Args:
            event_data: Optional event data (may be None if no data provided)
        """
        if self._tray_widget:
            self._tray_widget.update_status_text(
                QCoreApplication.translate("TrayController", "Ready")
            )
            if self._notifications_enabled:
                self._tray_widget.show_message(
                    QCoreApplication.translate("TrayController", "Sonic Input"),
                    QCoreApplication.translate(
                        "TrayController", "Text processed successfully!"
                    ),
                    QSystemTrayIcon.MessageIcon.Information,
                )

    def _on_processing_failed(self, event_data: Dict[str, Any] = None) -> None:
        """Handle processing failed event

        Args:
            event_data: Optional event data (may be None if no data provided)
        """
        if self._tray_widget:
            self._tray_widget.update_status_text(
                QCoreApplication.translate("TrayController", "Error")
            )
            if self._notifications_enabled:
                error_msg = (
                    event_data.get(
                        "error",
                        QCoreApplication.translate("TrayController", "Unknown error"),
                    )
                    if event_data
                    else QCoreApplication.translate("TrayController", "Unknown error")
                )
                self._tray_widget.show_message(
                    QCoreApplication.translate("TrayController", "Sonic Input Error"),
                    QCoreApplication.translate(
                        "TrayController", "Processing failed: {error}"
                    ).format(error=error_msg),
                    QSystemTrayIcon.MessageIcon.Critical,
                )

    # ==================== UI Updates ====================

    def _get_tray_tooltip(self, recording: bool) -> str:
        """Build localized tray tooltip text."""
        if recording:
            return QCoreApplication.translate(
                "TrayController",
                "Sonic Input - Recording\nRight-click for menu, Double-click for settings",
            )
        return QCoreApplication.translate(
            "TrayController",
            "Sonic Input - Ready\nRight-click for menu, Double-click for settings",
        )

    def _update_ui_for_recording_state(self, show_notification: bool = True) -> None:
        """Update UI based on recording state"""
        if not self._tray_widget:
            return

        recording = self._recording_state == RecordingState.RECORDING
        # Update icon
        self._tray_widget.update_icon(recording)

        # Update tooltip
        tooltip = self._get_tray_tooltip(recording)
        if recording:
            self._tray_widget.update_status_text(
                QCoreApplication.translate("TrayController", "Recording...")
            )
            self._tray_widget.update_recording_action_text(
                QCoreApplication.translate("TrayController", "Stop Recording")
            )
        else:
            self._tray_widget.update_status_text(
                QCoreApplication.translate("TrayController", "Ready")
            )
            self._tray_widget.update_recording_action_text(
                QCoreApplication.translate("TrayController", "Start Recording")
            )

        self._tray_widget.set_tooltip(tooltip)

        # Show notification
        if show_notification and self._notifications_enabled and recording:
            self._tray_widget.show_message(
                QCoreApplication.translate("TrayController", "Recording Started"),
                QCoreApplication.translate(
                    "TrayController", "Voice recording is active. Speak now!"
                ),
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def _update_ui_for_app_state(self) -> None:
        """Update UI based on app state"""
        if not self._tray_widget:
            return

        # Update status based on app state
        status_text = {
            AppState.STARTING: QCoreApplication.translate(
                "TrayController", "Starting..."
            ),
            AppState.IDLE: QCoreApplication.translate("TrayController", "Ready"),
            AppState.RECORDING: QCoreApplication.translate(
                "TrayController", "Recording..."
            ),
            AppState.PROCESSING: QCoreApplication.translate(
                "TrayController", "Processing..."
            ),
            AppState.INPUT_READY: QCoreApplication.translate(
                "TrayController", "Input Ready"
            ),
            AppState.ERROR: QCoreApplication.translate("TrayController", "Error"),
            AppState.STOPPING: QCoreApplication.translate(
                "TrayController", "Stopping..."
            ),
        }.get(self._app_state, QCoreApplication.translate("TrayController", "Unknown"))

        self._tray_widget.update_status_text(status_text)

    # ==================== Notifications ====================

    def _show_startup_notification(self) -> None:
        """Show startup notification"""
        if self._tray_widget and self._notifications_enabled:
            self._tray_widget.show_message(
                QCoreApplication.translate("TrayController", "Sonic Input"),
                QCoreApplication.translate(
                    "TrayController",
                    "Application is running! Right-click the tray icon (green dot) to access features, or double-click to open settings.",
                ),
                QSystemTrayIcon.MessageIcon.Information,
                8000,  # 8 seconds
            )

    def _show_about_dialog(self) -> None:
        """Show Fluent about window."""
        from ...fluent_about_window import FluentAboutWindow

        if self._about_window is None:
            self._about_window = FluentAboutWindow()

        self._about_window.show()
        self._about_window.raise_()
        self._about_window.activateWindow()

    # ==================== Public Interface ====================

    def set_notifications_enabled(self, enabled: bool) -> None:
        """Enable or disable notifications

        Args:
            enabled: Whether to enable notifications
        """
        with self._lock:
            self._notifications_enabled = enabled

            app_logger.log_audio_event(
                "Notifications setting changed",
                {"enabled": enabled, "component": self._component_name},
            )

    def show_notification(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        timeout: int = 3000,
    ) -> bool:
        """Show a notification

        Args:
            title: Notification title
            message: Notification message
            icon: Icon type
            timeout: Display timeout

        Returns:
            True if notification was shown
        """
        if self._tray_widget and self._notifications_enabled:
            return self._tray_widget.show_message(title, message, icon, timeout)
        return False

    def show_error_notification(self, message: str) -> bool:
        """Show error notification

        Args:
            message: Error message

        Returns:
            True if notification was shown
        """
        return self.show_notification(
            "Voice Input Error", message, QSystemTrayIcon.MessageIcon.Critical
        )

    def show_success_notification(self, message: str) -> bool:
        """Show success notification

        Args:
            message: Success message

        Returns:
            True if notification was shown
        """
        return self.show_notification(
            "Voice Input", message, QSystemTrayIcon.MessageIcon.Information
        )
