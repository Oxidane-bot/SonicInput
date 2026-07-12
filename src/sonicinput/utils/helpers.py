"""Filesystem path helpers."""

import os
import platform
from pathlib import Path

from ..core.services.config.app_constants import Paths


def get_app_data_dir() -> Path:
    """Return the platform-specific application data directory."""
    if platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / Paths.CONFIG_DIR_NAME
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / Paths.CONFIG_DIR_NAME
    return Path.home() / ".config" / Paths.CONFIG_DIR_NAME
