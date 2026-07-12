from pathlib import Path


def test_nuitka_build_includes_pypinyin_runtime_dictionaries() -> None:
    build_script = Path("build_nuitka.py").read_text(encoding="utf-8")

    assert '"--include-package-data=pypinyin"' in build_script
    assert "def _qml_plugin_data_options" in build_script
    assert "nuitka_cmd.extend(_qml_plugin_data_options(staged_qml_dir))" in build_script
    assert '"Qt6QuickControls2FluentWinUI3StyleImpl.dll"' in build_script
    assert '"Qt6QuickLayouts.dll"' in build_script


def test_nuitka_build_uses_cached_trimmed_qml_staging() -> None:
    build_script = Path("build_nuitka.py").read_text(encoding="utf-8")

    assert '"QtQuick/Controls/FluentWinUI3"' in build_script
    assert '"QtQuick/Controls/Basic"' in build_script
    assert '"QtQuick/Controls/Fusion"' in build_script
    assert '"QtQuick/Window"' in build_script
    assert '"QtQuick/VirtualKeyboard"' not in build_script
    assert "def _stage_cache_is_current" in build_script
    assert "SONICINPUT_NUITKA_WORK_DIR" in build_script
    assert "SONICINPUT_RELEASE_DIR" in build_script
    assert "def _remove_reserved_files" not in build_script
    assert '"--noinclude-data-files=**/NUL"' in build_script
    assert '"--include-package=onnxruntime"' not in build_script
    assert "def _validate_nuitka_output" in build_script
    assert "compiled_exe_path.unlink(missing_ok=True)" in build_script
    assert "compiled_report_path.unlink(missing_ok=True)" in build_script
    assert "[ERROR] Expected output file not found" in build_script


def test_release_script_rejects_stale_artifacts_and_times_out_smoke_commands() -> None:
    release_script = Path("scripts/release.ps1").read_text(encoding="utf-8")

    assert "$process.WaitForExit($TimeoutSeconds * 1000)" in release_script
    assert "[System.Diagnostics.ProcessStartInfo]::new()" in release_script
    assert "Remove-Item -LiteralPath $staleArtifact -Force" in release_script
    assert "SONICINPUT_PACKAGE_SMOKE_MODEL_DIR" in release_script
    assert "$offlineZipPath" in release_script
