"""Launch-at-login integration service.

Provides Windows startup registration through the per-user Run registry key.
Non-Windows platforms are treated as unsupported and no-op.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from ...utils import app_logger


class LaunchAtLoginService:
    """Manage launch-at-login registration for SonicInput."""

    RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    RUN_VALUE_NAME = "SonicInput"

    def __init__(
        self,
        *,
        platform_name: str | None = None,
        registry_module: Any | None = None,
        app_entry_path: Path | None = None,
    ) -> None:
        self._platform_name = platform_name or platform.system()
        self._registry_module = registry_module
        self._app_entry_path = app_entry_path or self._resolve_app_entry_path()

    def is_supported(self) -> bool:
        """Return whether launch-at-login system integration is supported."""
        return self._platform_name == "Windows"

    def build_command(self) -> str:
        """Build startup command for current runtime mode."""
        executable = str(Path(sys.executable).resolve())

        if getattr(sys, "frozen", False):
            return f'"{executable}" --gui'

        if self._app_entry_path.exists():
            return f'"{executable}" "{self._app_entry_path}" --gui'

        return f'"{executable}" --gui'

    def is_enabled(self) -> bool:
        """Check whether startup registration currently exists."""
        if not self.is_supported():
            return False

        winreg = self._get_registry_module()
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.RUN_KEY_PATH,
                0,
                winreg.KEY_READ,
            ) as key:
                value, _ = winreg.QueryValueEx(key, self.RUN_VALUE_NAME)
                return bool(str(value).strip())
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise RuntimeError(f"Failed to query launch-at-login state: {exc}") from exc

    def enable(self, command: str | None = None) -> None:
        """Enable launch-at-login registration."""
        if not self.is_supported():
            return

        startup_command = (command or self.build_command()).strip()
        if not startup_command:
            raise RuntimeError("Startup command is empty and cannot be registered.")

        winreg = self._get_registry_module()
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY_PATH) as key:
                winreg.SetValueEx(
                    key,
                    self.RUN_VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    startup_command,
                )
        except OSError as exc:
            raise RuntimeError(f"Failed to enable launch-at-login: {exc}") from exc

        if app_logger:
            app_logger.log_audio_event(
                "Launch-at-login enabled",
                {"command": startup_command, "registry_path": self.RUN_KEY_PATH},
            )

    def disable(self) -> None:
        """Disable launch-at-login registration."""
        if not self.is_supported():
            return

        winreg = self._get_registry_module()
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.RUN_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, self.RUN_VALUE_NAME)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeError(f"Failed to disable launch-at-login: {exc}") from exc

        if app_logger:
            app_logger.log_audio_event(
                "Launch-at-login disabled",
                {"registry_path": self.RUN_KEY_PATH},
            )

    def sync(self, enabled: bool, command: str | None = None) -> None:
        """Synchronize system startup registration with target config state."""
        if not self.is_supported():
            return

        if enabled:
            self.enable(command=command)
        else:
            self.disable()

    def _get_registry_module(self):
        if self._registry_module is not None:
            return self._registry_module

        try:
            import winreg  # type: ignore

            self._registry_module = winreg
            return self._registry_module
        except Exception as exc:
            raise RuntimeError(f"Failed to import winreg: {exc}") from exc

    def _resolve_app_entry_path(self) -> Path:
        """Resolve repository app.py path for dev-mode startup command."""
        current = Path(__file__).resolve()
        for parent in current.parents:
            candidate = parent / "app.py"
            if candidate.exists():
                return candidate

        return Path.cwd() / "app.py"
