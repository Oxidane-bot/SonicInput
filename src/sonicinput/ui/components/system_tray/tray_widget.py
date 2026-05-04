"""System tray widget - Pure UI component

Handles only the visual aspects of the system tray icon and menu.
No business logic or state management.
"""

from typing import Dict, Optional

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ...styles.modern_styles import (
    ModernColors,
    simple_text_icon,
    tray_menu_style,
)


class TrayWidget(QObject):
    """Pure UI component for system tray

    Responsible only for:
    - Creating and displaying the tray icon
    - Managing the context menu UI
    - Icon visual updates
    - User interaction event forwarding
    """

    # UI events (forwarded to controller)
    icon_activated = Signal(object)  # QSystemTrayIcon.ActivationReason
    menu_action_triggered = Signal(str)  # action name

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        self._tray_icon: Optional[QSystemTrayIcon] = None
        self._context_menu: Optional[QMenu] = None
        self._menu_actions: Dict[str, QAction] = {}

        # Check system tray availability
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # In test environment or systems without tray support,
            # just log and continue without creating the actual tray
            print("Warning: System tray is not available on this system.")
            return

        self._setup_tray_icon()

    def _setup_tray_icon(self) -> None:
        """Initialize the system tray icon"""
        # Create icon (单一设计，不区分状态)
        icon = self._create_icon()

        # Create system tray icon
        self._tray_icon = QSystemTrayIcon(icon)

        # Create context menu
        self._create_context_menu()
        self.retranslate_ui()

        # Set initial tooltip
        self.set_tooltip(
            QCoreApplication.translate(
                "TrayWidget",
                "SonicInput - Ready\nRight-click for menu, Double-click for settings",
            )
        )

        # Connect signals
        self._tray_icon.activated.connect(self._on_icon_activated)

        # Show the icon
        self._tray_icon.show()

    def _create_icon(self) -> QIcon:
        """Create modern minimalist microphone tray icon with gradient

        Returns:
            QIcon for the tray
        """
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QLinearGradient

        size = 32
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Calculate proportions
        center_x = size / 2
        center_y = size / 2

        # Microphone capsule dimensions (main body) - 调整比例与静态图标一致
        capsule_width = size * 0.42
        capsule_height = size * 0.52
        capsule_x = center_x - capsule_width / 2
        capsule_y = center_y - capsule_height / 2 - size * 0.18

        # Create gradient for microphone body - 使用光谱上距离较远的颜色
        gradient = QLinearGradient(
            center_x, capsule_y, center_x, capsule_y + capsule_height
        )

        # Orange to Purple gradient (光谱上距离远，视觉冲击力强)
        gradient.setColorAt(0, QColor(255, 152, 0))  # Material Orange 500
        gradient.setColorAt(1, QColor(156, 39, 176))  # Material Purple 500

        # Draw microphone capsule (rounded rectangle, capsule-like)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        capsule_rect = QRectF(capsule_x, capsule_y, capsule_width, capsule_height)
        painter.drawRoundedRect(capsule_rect, capsule_width * 0.5, capsule_width * 0.5)

        # Draw connection stem (simple line) - 加长连接杆
        stem_top_y = capsule_y + capsule_height
        stem_bottom_y = center_y + size * 0.35
        pen = painter.pen()
        pen.setWidth(max(2, int(size * 0.09)))
        pen.setColor(QColor(156, 39, 176))  # 使用紫色（渐变的终点色）
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(
            int(center_x), int(stem_top_y), int(center_x), int(stem_bottom_y)
        )

        # Draw base (rounded rectangle at bottom) - 调整底座
        base_width = size * 0.58
        base_height = size * 0.13
        base_x = center_x - base_width / 2
        base_y = stem_bottom_y - base_height / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(156, 39, 176))  # 使用紫色（渐变的终点色）
        base_rect = QRectF(base_x, base_y, base_width, base_height)
        painter.drawRoundedRect(base_rect, base_height * 0.5, base_height * 0.5)

        painter.end()

        return QIcon(pixmap)

    def _create_menu_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("trayMenuHeader")
        header.setFixedWidth(220)

        layout = QVBoxLayout(header)
        layout.setContentsMargins(12, 10, 12, 9)
        layout.setSpacing(4)

        title = QLabel("SonicInput")
        title.setObjectName("trayMenuTitle")
        layout.addWidget(title)

        self._status_label = QLabel(QCoreApplication.translate("TrayWidget", "Ready"))
        self._status_label.setObjectName("trayMenuStatus")
        layout.addWidget(self._status_label)

        return header

    def _create_context_menu(self) -> None:
        """Create the context menu"""
        self._context_menu = QMenu()
        self._context_menu.setObjectName("sonic_tray_menu")
        self._context_menu.setStyleSheet(tray_menu_style())

        header_action = QWidgetAction(self._context_menu)
        header_action.setDefaultWidget(self._create_menu_header())
        self._context_menu.addAction(header_action)
        self._menu_actions["header"] = header_action

        self._context_menu.addSeparator()

        # Recording action
        recording_action = QAction(
            QCoreApplication.translate("TrayWidget", "Start Recording"),
            self._context_menu,
        )
        recording_action.setIcon(simple_text_icon("●", ModernColors.RECORDING))
        recording_action.triggered.connect(
            lambda: self.menu_action_triggered.emit("toggle_recording")
        )
        self._context_menu.addAction(recording_action)
        self._menu_actions["recording"] = recording_action

        self._context_menu.addSeparator()

        # Settings
        settings_action = QAction(
            QCoreApplication.translate("TrayWidget", "Settings"), self._context_menu
        )
        settings_action.setIcon(simple_text_icon("⚙", ModernColors.ACCENT_2))
        settings_action.triggered.connect(
            lambda: self.menu_action_triggered.emit("show_settings")
        )
        self._context_menu.addAction(settings_action)
        self._menu_actions["settings"] = settings_action

        # About
        about_action = QAction(
            QCoreApplication.translate("TrayWidget", "About"), self._context_menu
        )
        about_action.setIcon(simple_text_icon("i", ModernColors.TEXT_SECONDARY))
        about_action.triggered.connect(
            lambda: self.menu_action_triggered.emit("show_about")
        )
        self._context_menu.addAction(about_action)
        self._menu_actions["about"] = about_action

        self._context_menu.addSeparator()

        # Exit
        exit_action = QAction(
            QCoreApplication.translate("TrayWidget", "Exit"), self._context_menu
        )
        exit_action.setIcon(simple_text_icon("×", ModernColors.WARNING))
        exit_action.triggered.connect(
            lambda: self.menu_action_triggered.emit("exit_application")
        )
        self._context_menu.addAction(exit_action)
        self._menu_actions["exit"] = exit_action

        # Set the menu
        self._tray_icon.setContextMenu(self._context_menu)

    def _on_icon_activated(self, reason) -> None:
        """Handle tray icon activation"""
        self.icon_activated.emit(reason)

    # ==================== Public UI Interface ====================

    def retranslate_ui(self) -> None:
        """Update static menu text for the current language."""
        if not self._context_menu:
            return
        if "settings" in self._menu_actions:
            self._menu_actions["settings"].setText(
                QCoreApplication.translate("TrayWidget", "Settings")
            )
        if "recording" in self._menu_actions:
            self._menu_actions["recording"].setText(
                QCoreApplication.translate("TrayWidget", "Start Recording")
            )
        if "about" in self._menu_actions:
            self._menu_actions["about"].setText(
                QCoreApplication.translate("TrayWidget", "About")
            )
        if "exit" in self._menu_actions:
            self._menu_actions["exit"].setText(
                QCoreApplication.translate("TrayWidget", "Exit")
            )

    def update_icon(self, recording: bool) -> None:
        """Update the tray icon visual state (保持接口兼容性，但不再切换图标)

        Args:
            recording: 保留参数用于兼容性，实际不使用
        """
        # 不再根据状态切换图标，保持单一设计
        pass

    def set_tooltip(self, tooltip: str) -> None:
        """Set the tray icon tooltip

        Args:
            tooltip: Tooltip text
        """
        if self._tray_icon:
            self._tray_icon.setToolTip(tooltip)

    def update_status_text(self, status: str) -> None:
        """Update the status text in the menu

        Args:
            status: Status text to display
        """
        label = getattr(self, "_status_label", None)
        if label is not None:
            label.setText(status)

    def update_recording_action_text(self, text: str) -> None:
        """Update the recording action text

        Args:
            text: Action text (e.g., "Start Recording" or "Stop Recording")
        """
        if "recording" in self._menu_actions:
            self._menu_actions["recording"].setText(text)

    def show_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        timeout: int = 3000,
    ) -> bool:
        """Show a system tray message

        Args:
            title: Message title
            message: Message content
            icon: Message icon type
            timeout: Display timeout in milliseconds

        Returns:
            True if message was shown, False if not supported
        """
        if self._tray_icon and QSystemTrayIcon.supportsMessages():
            self._tray_icon.showMessage(title, message, icon, timeout)
            return True
        return False

    def show(self) -> None:
        """Show the tray icon"""
        if self._tray_icon:
            self._tray_icon.show()

    def hide(self) -> None:
        """Hide the tray icon"""
        if self._tray_icon:
            self._tray_icon.hide()

    def is_visible(self) -> bool:
        """Check if tray icon is visible

        Returns:
            True if visible, False otherwise
        """
        return self._tray_icon.isVisible() if self._tray_icon else False

    def supports_messages(self) -> bool:
        """Check if system supports tray messages

        Returns:
            True if messages are supported, False if tray not available
        """
        return self._tray_icon is not None and QSystemTrayIcon.supportsMessages()

    def cleanup(self) -> None:
        """Clean up resources"""
        if self._tray_icon:
            self._tray_icon.hide()
            self._tray_icon = None

        if self._context_menu:
            self._context_menu = None

        self._menu_actions.clear()

    def is_tray_available(self) -> bool:
        """Check if system tray is available

        Returns:
            True if tray icon was created successfully
        """
        return self._tray_icon is not None
