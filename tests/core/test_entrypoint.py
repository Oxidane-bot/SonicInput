"""Regression tests for the installed SonicInput command entry point."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest


def _sonicinput_entry_point() -> importlib.metadata.EntryPoint:
    matches = [
        entry_point
        for entry_point in importlib.metadata.entry_points(group="console_scripts")
        if entry_point.name == "sonicinput"
    ]
    assert len(matches) == 1
    return matches[0]


def test_console_entry_point_is_importable() -> None:
    entry_point = _sonicinput_entry_point()

    assert entry_point.value == "sonicinput.main:main"
    assert callable(entry_point.load())


def test_module_help_exits_successfully_without_starting_gui(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["APPDATA"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, "-m", "sonicinput.main", "--help"],
        check=False,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
    assert "--diagnostics" in result.stdout
    assert not (tmp_path / "SonicInput" / "logs" / "runtime_state.json").exists()


def test_package_smoke_cli_returns_its_check_result(monkeypatch) -> None:
    from sonicinput import main

    monkeypatch.setattr(sys, "argv", ["sonicinput", "--package-smoke"])
    with (
        patch.object(main, "initialize_runtime_diagnostics"),
        patch.object(main, "_update_runtime_state"),
        patch.object(main.signal, "signal"),
        patch.object(main, "run_package_smoke", return_value=True),
    ):
        with pytest.raises(SystemExit) as exit_info:
            main.main()

    assert exit_info.value.code == 0
