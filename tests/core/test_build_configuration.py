from pathlib import Path


def test_nuitka_build_includes_pypinyin_runtime_dictionaries() -> None:
    build_script = Path("build_nuitka.py").read_text(encoding="utf-8")

    assert '"--include-package-data=pypinyin"' in build_script
    assert "def _qml_plugin_data_options" in build_script
    assert "nuitka_cmd.extend(_qml_plugin_data_options(staged_qml_dir))" in build_script
    assert '"Qt6QuickControls2FluentWinUI3StyleImpl.dll"' in build_script
    assert '"Qt6QuickLayouts.dll"' in build_script
