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
    assert "--validate" in result.stdout
    assert "--test" not in result.stdout
    assert "--diagnostics" not in result.stdout
    assert not (tmp_path / "SonicInput" / "logs" / "runtime_state.json").exists()


@pytest.mark.parametrize("legacy_argument", ["--test", "--diagnostics"])
def test_removed_cli_arguments_return_argparse_error(
    monkeypatch, legacy_argument: str
) -> None:
    from sonicinput import main

    monkeypatch.setattr(sys, "argv", ["sonicinput", legacy_argument])
    with patch.object(main, "initialize_runtime_diagnostics") as initialize:
        with pytest.raises(SystemExit) as exit_info:
            main.main()

    assert exit_info.value.code == 2
    initialize.assert_not_called()


def test_default_cli_dispatches_to_gui(monkeypatch) -> None:
    from sonicinput import main

    monkeypatch.setattr(sys, "argv", ["sonicinput"])
    with (
        patch.object(main, "initialize_runtime_diagnostics"),
        patch.object(main, "_update_runtime_state") as update_runtime_state,
        patch.object(main.signal, "signal"),
        patch.object(main, "run_gui_with_diagnostics", return_value=7) as run_gui,
    ):
        with pytest.raises(SystemExit) as exit_info:
            main.main()

    assert exit_info.value.code == 7
    run_gui.assert_called_once_with()
    update_runtime_state.assert_any_call(stage="launch_gui")


def test_validate_cli_dispatches_to_environment_validation(monkeypatch) -> None:
    from sonicinput import main

    monkeypatch.setattr(sys, "argv", ["sonicinput", "--validate"])
    with (
        patch.object(main, "initialize_runtime_diagnostics"),
        patch.object(main, "_update_runtime_state") as update_runtime_state,
        patch.object(main.signal, "signal"),
        patch.object(main, "validate_environment", return_value=(True, {})) as validate,
        patch.object(main, "run_gui_with_diagnostics") as run_gui,
    ):
        with pytest.raises(SystemExit) as exit_info:
            main.main()

    assert exit_info.value.code == 0
    validate.assert_called_once_with()
    run_gui.assert_not_called()
    update_runtime_state.assert_any_call(stage="run_validate")


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
