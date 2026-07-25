from pathlib import Path


def test_nuitka_build_includes_pypinyin_runtime_dictionaries() -> None:
    build_script = Path("build_nuitka.py").read_text(encoding="utf-8")

    assert '"--include-package-data=pypinyin"' in build_script
    assert "def _qml_plugin_data_options" in build_script
    assert "nuitka_cmd.extend(_qml_plugin_data_options(staged_qml_dir))" in build_script
    assert '"Qt6QuickControls2FluentWinUI3StyleImpl.dll"' in build_script
    assert '"Qt6QuickLayouts.dll"' in build_script
    assert "def _sherpa_onnxruntime_dll" in build_script
    assert 'f"--include-data-file={sherpa_onnxruntime_dll}=onnxruntime.dll"' in (
        build_script
    )


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
    assert "SONICINPUT_NUITKA_COMPILER" in build_script
    assert 'compiler_option = "--msvc=14.3"' in build_script
    assert 'compiler_option = "--mingw64"' in build_script
    assert "_validate_nuitka_output(nuitka_output_dir, sherpa_onnxruntime_dll)" in (
        build_script
    )
    assert "def _validate_nuitka_output" in build_script
    assert "compiled_exe_path.unlink(missing_ok=True)" in build_script
    assert "compiled_report_path.unlink(missing_ok=True)" in build_script
    assert "[ERROR] Expected output file not found" in build_script


def test_release_script_rejects_stale_artifacts_and_times_out_smoke_commands() -> None:
    release_script = Path("scripts/release.ps1").read_text(encoding="utf-8")

    assert "$process.WaitForExit($TimeoutSeconds * 1000)" in release_script
    assert "[System.Diagnostics.ProcessStartInfo]::new()" in release_script
    assert "$startInfo.RedirectStandardOutput = $true" in release_script
    assert "$startInfo.RedirectStandardError = $true" in release_script
    assert "$process.StandardOutput.ReadToEndAsync()" in release_script
    assert "$process.StandardError.ReadToEndAsync()" in release_script
    assert "Remove-Item -LiteralPath $staleArtifact -Force" in release_script
    assert "SONICINPUT_PACKAGE_SMOKE_MODEL_DIR" in release_script
    assert "$offlineZipPath" in release_script


def test_ci_uses_locked_dependency_and_dead_code_gates() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "uv sync --locked --extra dev" in workflow
    assert "vulture src app.py build_nuitka.py scripts --min-confidence 80" in workflow
    assert "actions/cache@" not in workflow
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9" in workflow


def test_release_workflow_builds_and_publishes_the_tagged_version() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert (
        "Tag ${{ steps.release.outputs.tag }} does not match pyproject.toml" in workflow
    )
    assert ".\\scripts\\release.ps1 -NoOffline" in workflow
    assert "gh release create" in workflow
    assert "RELEASE_NOTES.md" in workflow
    assert "timeout-minutes: 90" in workflow
    assert "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9" in workflow
    assert "NUITKA_CACHE_DIR" in workflow
    assert "SONICINPUT_NUITKA_COMPILER: msvc" in workflow
    assert "runs-on: windows-2022" in workflow
    assert "Microsoft.VisualStudio.Component.VC.Tools.x86.x64" in workflow
    assert "vcvars64.bat" in workflow
    assert "nuitka-msvc-probe.py" in workflow
    assert "--msvc=14.3" in workflow
    assert "nuitka-${{ runner.os }}-windows-2022-msvc-py" in workflow
