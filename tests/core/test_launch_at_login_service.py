"""Tests for launch-at-login Windows integration service."""

from pathlib import Path
import sys
from unittest.mock import MagicMock

from sonicinput.core.services.launch_at_login_service import LaunchAtLoginService


def _create_fake_winreg():
    fake = MagicMock()
    fake.HKEY_CURRENT_USER = object()
    fake.KEY_READ = 0x20019
    fake.KEY_SET_VALUE = 0x2
    fake.REG_SZ = 1
    return fake


def test_build_command_for_dev_mode(tmp_path, monkeypatch):
    app_entry = tmp_path / "app.py"
    app_entry.write_text("print('ok')", encoding="utf-8")
    python_path = tmp_path / "python.exe"

    monkeypatch.setattr(sys, "executable", str(python_path))
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    service = LaunchAtLoginService(
        platform_name="Windows",
        app_entry_path=app_entry,
    )

    expected = f'"{Path(sys.executable).resolve()}" "{app_entry}" --gui'
    assert service.build_command() == expected


def test_build_command_for_frozen_mode(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    service = LaunchAtLoginService(platform_name="Windows")

    expected = f'"{Path(sys.executable).resolve()}" --gui'
    assert service.build_command() == expected


def test_enable_writes_run_key_value():
    fake_winreg = _create_fake_winreg()
    key = object()
    context_manager = MagicMock()
    context_manager.__enter__.return_value = key
    fake_winreg.CreateKey.return_value = context_manager

    service = LaunchAtLoginService(
        platform_name="Windows",
        registry_module=fake_winreg,
    )

    command = '"C:\\Program Files\\SonicInput\\SonicInput.exe" --gui'
    service.enable(command)

    fake_winreg.CreateKey.assert_called_once_with(
        fake_winreg.HKEY_CURRENT_USER, service.RUN_KEY_PATH
    )
    fake_winreg.SetValueEx.assert_called_once_with(
        key, service.RUN_VALUE_NAME, 0, fake_winreg.REG_SZ, command
    )


def test_is_enabled_returns_true_when_value_exists():
    fake_winreg = _create_fake_winreg()
    key = object()
    context_manager = MagicMock()
    context_manager.__enter__.return_value = key
    fake_winreg.OpenKey.return_value = context_manager
    fake_winreg.QueryValueEx.return_value = ("cmd", fake_winreg.REG_SZ)

    service = LaunchAtLoginService(
        platform_name="Windows",
        registry_module=fake_winreg,
    )

    assert service.is_enabled() is True


def test_disable_ignores_missing_registry_value():
    fake_winreg = _create_fake_winreg()
    key = object()
    context_manager = MagicMock()
    context_manager.__enter__.return_value = key
    fake_winreg.OpenKey.return_value = context_manager
    fake_winreg.DeleteValue.side_effect = FileNotFoundError

    service = LaunchAtLoginService(
        platform_name="Windows",
        registry_module=fake_winreg,
    )

    service.disable()

    fake_winreg.DeleteValue.assert_called_once_with(key, service.RUN_VALUE_NAME)


def test_sync_is_noop_on_non_windows():
    fake_winreg = _create_fake_winreg()
    service = LaunchAtLoginService(platform_name="Linux", registry_module=fake_winreg)

    service.sync(True)

    fake_winreg.CreateKey.assert_not_called()
    fake_winreg.SetValueEx.assert_not_called()
