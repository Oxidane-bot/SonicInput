"""Shared modern PySide widget styles for SonicInput."""

from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


class ModernColors:
    SURFACE_HOVER = "#282d3a"
    TEXT_PRIMARY = "#f4f7fb"
    TEXT_SECONDARY = "#aab2c0"
    ACCENT_2 = "#22d3ee"
    RECORDING = "#ff5a66"
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
