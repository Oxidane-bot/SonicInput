import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "sonicinput"

LEGACY_UI_MODULE_PATHS = [
    SRC / "ui" / "settings_window.py",
    SRC / "ui" / "recording_overlay.py",
    SRC / "ui" / "settings_tabs",
    SRC / "ui" / "dialogs" / "batch_reprocess_dialog.py",
    SRC / "ui" / "overlay_components",
    SRC / "ui" / "overlay",
    SRC / "ui" / "controllers",
]

FORBIDDEN_IMPORT_MODULES = {
    "sonicinput.ui.settings_window",
    "sonicinput.ui.recording_overlay",
    "sonicinput.ui.settings_tabs",
    "sonicinput.ui.dialogs.batch_reprocess_dialog",
    "sonicinput.ui.overlay_components",
    "sonicinput.ui.overlay",
    "sonicinput.ui.controllers",
}


def _production_python_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_legacy_user_visible_qwidget_modules_are_removed():
    remaining = [path for path in LEGACY_UI_MODULE_PATHS if path.exists()]

    assert remaining == []


def test_production_code_does_not_reference_legacy_user_visible_ui_modules():
    offenders: list[str] = []

    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module in FORBIDDEN_IMPORT_MODULES
            ):
                offenders.append(f"{path.relative_to(ROOT)}: from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_IMPORT_MODULES:
                        offenders.append(
                            f"{path.relative_to(ROOT)}: import {alias.name}"
                        )

    assert offenders == []


def test_ui_package_exports_fluent_runtime_entry_points_only():
    import sonicinput.ui as ui

    assert hasattr(ui, "FluentSettingsWindow")
    assert hasattr(ui, "FluentRecordingOverlay")
    assert hasattr(ui, "MainWindow")
    assert not hasattr(ui, "SettingsWindow")
    assert not hasattr(ui, "RecordingOverlay")
