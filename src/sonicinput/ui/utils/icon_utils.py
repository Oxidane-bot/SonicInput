"""Application icon utilities

Provides icon loading from pre-generated resources.
"""

from pathlib import Path
from typing import Dict

from PySide6.QtGui import QIcon

# Icon cache to avoid repeated file loading
_ICON_CACHE: Dict[str, QIcon] = {}


def _get_icon_path(filename: str) -> Path:
    """Get path to icon file in resources directory

    Args:
        filename: Icon filename (e.g., "app_icon.ico")

    Returns:
        Path to the icon file
    """
    # Navigate from ui/utils/ to resources/icons/
    return Path(__file__).parent.parent.parent / "resources" / "icons" / filename


def get_app_icon() -> QIcon:
    """Load application icon from resources (cached)

    Returns:
        QIcon with the application logo (multi-resolution)
    """
    if "app" not in _ICON_CACHE:
        icon = QIcon()
        # Load multiple resolutions for best quality across different DPIs
        for size in [16, 32, 48, 256]:
            png_path = _get_icon_path(f"app_icon_{size}.png")
            if png_path.exists():
                icon.addFile(str(png_path))

        # Fallback to default if no size-specific files found
        if icon.isNull():
            default_path = _get_icon_path("app_icon.png")
            if default_path.exists():
                icon = QIcon(str(default_path))

        _ICON_CACHE["app"] = icon

    return _ICON_CACHE["app"]
