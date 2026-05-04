"""Shared modern PySide widget styles for SonicInput."""

from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


class ModernColors:
    BACKGROUND = "#0f1117"
    SURFACE = "#171a22"
    SURFACE_RAISED = "#20242f"
    SURFACE_HOVER = "#282d3a"
    BORDER = "#303646"
    TEXT_PRIMARY = "#f4f7fb"
    TEXT_SECONDARY = "#aab2c0"
    ACCENT = "#7c5cff"
    ACCENT_2 = "#22d3ee"
    RECORDING = "#ff5a66"
    SUCCESS = "#3ddc97"
    WARNING = "#ffb84d"


def _svg_icon(color: str, path: str) -> QIcon:
    pixmap = QPixmap(20, 20)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont()
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(pixmap.rect(), 0x84, path)
    painter.end()
    return QIcon(pixmap)


def simple_text_icon(symbol: str, color: str = ModernColors.TEXT_SECONDARY) -> QIcon:
    """Create a small text-based icon for native Qt actions."""
    return _svg_icon(color, symbol)


def settings_window_style() -> str:
    return f"""
        QMainWindow {{
            background-color: {ModernColors.BACKGROUND};
        }}
        QWidget#settings_root {{
            background-color: {ModernColors.BACKGROUND};
            color: {ModernColors.TEXT_PRIMARY};
            font-size: 13px;
        }}
        QFrame#settings_shell {{
            background-color: {ModernColors.SURFACE};
            border: 1px solid {ModernColors.BORDER};
            border-radius: 8px;
        }}
        QListWidget#settings_sidebar {{
            background-color: {ModernColors.SURFACE};
            border: none;
            outline: none;
            padding: 8px;
            color: {ModernColors.TEXT_SECONDARY};
        }}
        QListWidget#settings_sidebar::item {{
            min-height: 38px;
            padding: 0 12px;
            border-radius: 7px;
            margin: 2px 0;
        }}
        QListWidget#settings_sidebar::item:selected {{
            background-color: {ModernColors.SURFACE_RAISED};
            color: {ModernColors.TEXT_PRIMARY};
            border-left: 3px solid {ModernColors.ACCENT_2};
        }}
        QListWidget#settings_sidebar::item:hover {{
            background-color: {ModernColors.SURFACE_HOVER};
            color: {ModernColors.TEXT_PRIMARY};
        }}
        QStackedWidget#settings_content_stack {{
            background-color: {ModernColors.SURFACE};
            border: none;
        }}
        QScrollArea {{
            background-color: transparent;
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: transparent;
        }}
        QGroupBox {{
            background-color: {ModernColors.SURFACE_RAISED};
            border: 1px solid {ModernColors.BORDER};
            border-radius: 8px;
            margin-top: 16px;
            padding: 14px 12px 12px 12px;
            color: {ModernColors.TEXT_PRIMARY};
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            left: 10px;
            color: {ModernColors.TEXT_PRIMARY};
        }}
        QLabel {{
            color: {ModernColors.TEXT_SECONDARY};
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: #11141b;
            border: 1px solid {ModernColors.BORDER};
            border-radius: 6px;
            padding: 6px 8px;
            color: {ModernColors.TEXT_PRIMARY};
            selection-background-color: {ModernColors.ACCENT};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {ModernColors.ACCENT_2};
        }}
        QCheckBox {{
            color: {ModernColors.TEXT_PRIMARY};
            spacing: 8px;
        }}
        QPushButton {{
            background-color: {ModernColors.SURFACE_RAISED};
            border: 1px solid {ModernColors.BORDER};
            border-radius: 7px;
            padding: 7px 14px;
            color: {ModernColors.TEXT_PRIMARY};
            min-height: 22px;
        }}
        QPushButton:hover {{
            background-color: {ModernColors.SURFACE_HOVER};
            border-color: #465166;
        }}
        QPushButton#ok_btn, QPushButton#apply_btn {{
            background-color: {ModernColors.ACCENT};
            border-color: {ModernColors.ACCENT};
            color: white;
            font-weight: 600;
        }}
        QPushButton#ok_btn:hover, QPushButton#apply_btn:hover {{
            background-color: #8b73ff;
        }}
        QPushButton#reset_btn {{
            color: {ModernColors.WARNING};
        }}
    """


def tray_menu_style() -> str:
    return f"""
        QMenu#sonic_tray_menu {{
            background-color: #1b1f29;
            color: {ModernColors.TEXT_PRIMARY};
            border: 1px solid #3a4252;
            border-radius: 9px;
            padding: 6px;
        }}
        QWidget#trayMenuHeader {{
            background-color: transparent;
        }}
        QLabel#trayMenuTitle {{
            color: {ModernColors.TEXT_PRIMARY};
            font-size: 14px;
            font-weight: 700;
            background: transparent;
        }}
        QLabel#trayMenuStatus {{
            color: {ModernColors.TEXT_SECONDARY};
            font-size: 12px;
            background: transparent;
        }}
        QMenu#sonic_tray_menu::item {{
            min-width: 152px;
            padding: 8px 18px 8px 18px;
            border-radius: 7px;
            margin: 1px 2px;
        }}
        QMenu#sonic_tray_menu::icon {{
            padding-left: 4px;
            width: 18px;
            height: 18px;
        }}
        QMenu#sonic_tray_menu::item:selected {{
            background-color: {ModernColors.SURFACE_HOVER};
        }}
        QMenu#sonic_tray_menu::item:disabled {{
            color: {ModernColors.TEXT_SECONDARY};
        }}
        QMenu#sonic_tray_menu::separator {{
            height: 1px;
            background-color: #353d4c;
            margin: 5px 8px;
        }}
    """


def overlay_hud_style() -> str:
    return f"""
        QFrame#recordingOverlayHud {{
            background-color: rgba(18, 21, 30, 236);
            border: 1px solid rgba(124, 92, 255, 92);
            border-radius: 14px;
        }}
        QLabel#overlayTitle {{
            color: {ModernColors.TEXT_PRIMARY};
            font-size: 12px;
            font-weight: 600;
            background: transparent;
        }}
        QLabel#overlayTimer {{
            color: {ModernColors.TEXT_SECONDARY};
            font-size: 12px;
            background: transparent;
        }}
        QPushButton#overlay_stop_button {{
            background-color: rgba(255, 90, 102, 34);
            border: 1px solid rgba(255, 90, 102, 120);
            border-radius: 12px;
            color: {ModernColors.RECORDING};
            font-size: 13px;
            font-weight: 700;
            min-width: 24px;
            max-width: 24px;
            min-height: 24px;
            max-height: 24px;
            padding: 0;
        }}
        QPushButton#overlay_stop_button:hover {{
            background-color: rgba(255, 90, 102, 70);
        }}
    """
