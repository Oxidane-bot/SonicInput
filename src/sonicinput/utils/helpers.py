"""Filesystem path helpers."""

import os
import platform
from pathlib import Path

_CONFIG_DIR_NAME = "SonicInput"


def get_app_data_dir() -> Path:
    """Return the platform-specific application data directory."""
    if platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / _CONFIG_DIR_NAME
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / _CONFIG_DIR_NAME
    return Path.home() / ".config" / _CONFIG_DIR_NAME
