#!/usr/bin/env python
"""
Nuitka compilation script - Package as single file executable

This script compiles SonicInput into a standalone Windows executable using Nuitka.
Includes support for sherpa-onnx C extension modules and all required dependencies.
"""

import os
import shutil
import string
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree


# Read version number
def get_version():
    """Read version from pyproject.toml"""
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        with open(pyproject, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("version ="):
                    # Extract version: version = "0.1.2" -> 0.1.2
                    return line.split('"')[1]
    return "0.0.0"


def _collect_translation_text(assets_dir: Path) -> str:
    text_chunks = []
    i18n_dir = assets_dir / "i18n"
    for ts_file in sorted(i18n_dir.glob("*.ts")):
        try:
            tree = ElementTree.parse(ts_file)
        except Exception:
            continue
        root = tree.getroot()
        for elem in root.iter():
            if elem.tag in {"source", "translation"} and elem.text:
                text_chunks.append(elem.text)

    base_chars = (
        string.ascii_letters
        + string.digits
        + " .,:;!?\"'()[]{}<>+-=*/\\\\|@#$%^&~`_"
        + "\n\r\t"
    )
    text_chunks.append(base_chars)
    unique_chars = sorted(set("".join(text_chunks)))
    return "".join(unique_chars)


def _subset_font(source_font: Path, target_font: Path, text: str) -> None:
    try:
        from fontTools.subset import Options, Subsetter
        from fontTools.ttLib import TTFont
    except Exception as exc:
        raise RuntimeError(
            "fontTools is required to subset bundled fonts. "
            "Install build dependencies (e.g., uv sync --group dev)."
        ) from exc

    options = Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recalc_bounds = True
    options.recalc_timestamp = True
    options.prune_unicode_ranges = True

    font = TTFont(str(source_font))
    subsetter = Subsetter(options=options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    target_font.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(target_font))


def stage_assets() -> Path:
    assets_dir = Path("assets")
    staging_dir = Path("build") / "assets_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Copy icon
    shutil.copy2(assets_dir / "icon.png", staging_dir / "icon.png")

    # Copy compiled translations only
    i18n_dir = staging_dir / "i18n"
    i18n_dir.mkdir(parents=True, exist_ok=True)
    for qm_file in (assets_dir / "i18n").glob("*.qm"):
        shutil.copy2(qm_file, i18n_dir / qm_file.name)

    # Subset bundled fonts
    font_source_dir = assets_dir / "fonts" / "resource-han-rounded"
    font_target_dir = staging_dir / "fonts" / "resource-han-rounded"
    font_target_dir.mkdir(parents=True, exist_ok=True)
    subset_text = _collect_translation_text(assets_dir)
    for font_name in [
        "ResourceHanRoundedCN-Regular.ttf",
        "ResourceHanRoundedCN-Bold.ttf",
    ]:
        _subset_font(
            font_source_dir / font_name, font_target_dir / font_name, subset_text
        )

    # Copy font license/notice
    for doc_name in ["OFL-License.txt", "FONT-NOTICE.txt"]:
        shutil.copy2(font_source_dir / doc_name, font_target_dir / doc_name)

    return staging_dir


def _resolve_pyside6_qml_dir() -> Path:
    try:
        import PySide6
    except Exception as exc:
        raise RuntimeError("PySide6 is required to stage QML runtime modules.") from exc

    qml_dir = Path(PySide6.__file__).resolve().parent / "qml"
    if not qml_dir.exists():
        raise RuntimeError(f"PySide6 QML directory not found: {qml_dir}")
    return qml_dir


def stage_qml_runtime() -> Path:
    """Stage only the QML imports used by the Fluent UI surfaces."""
    source_qml_dir = _resolve_pyside6_qml_dir()
    staging_dir = Path("build") / "qml_staging"
    target_root = staging_dir / "PySide6" / "qml"

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    target_root.mkdir(parents=True, exist_ok=True)

    qml_imports = [
        "Qt",
        "QtCore",
        "QtQml",
        "QtQuick",
    ]
    for import_name in qml_imports:
        source_dir = source_qml_dir / import_name
        if not source_dir.exists():
            raise RuntimeError(f"Required QML import not found: {source_dir}")
        shutil.copytree(source_dir, target_root / import_name)

    return staging_dir


def _qml_plugin_data_options(staging_dir: Path) -> list[str]:
    """Keep QML module plugins when Nuitka treats staged DLLs as non-data files."""
    qml_root = staging_dir / "PySide6" / "qml"
    options = []
    for plugin_path in sorted(qml_root.rglob("*plugin.dll")):
        relative_path = plugin_path.relative_to(staging_dir).as_posix()
        options.append(f"--include-data-file={plugin_path}={relative_path}")
    return options


def _remove_reserved_files(package_name: str) -> None:
    """Remove Windows-reserved filenames (e.g., NUL) from package data."""
    try:
        module = __import__(package_name)
    except Exception:
        return

    package_dir = Path(module.__file__).resolve().parent
    for path in package_dir.rglob("*"):
        if path.is_file() and path.name.lower() == "nul":
            try:
                path.unlink()
                print(f"[CLEAN] Removed reserved file: {path}")
            except Exception as exc:
                print(f"[WARN] Could not remove reserved file {path}: {exc}")


def _resolve_pyside6_dll(dll_name: str) -> Path | None:
    try:
        import PySide6
    except Exception:
        return None

    dll_path = Path(PySide6.__file__).resolve().parent / dll_name
    return dll_path if dll_path.exists() else None


def _resolve_shiboken6_dll(dll_name: str) -> Path | None:
    try:
        import shiboken6
    except Exception:
        return None

    dll_path = Path(shiboken6.__file__).resolve().parent / dll_name
    return dll_path if dll_path.exists() else None


def _find_onnxruntime_dll() -> Path | None:
    env_paths = [
        os.environ.get("ONNXRUNTIME_DLL_PATH"),
        os.environ.get("ONNXRUNTIME_DLL"),
    ]
    for env_path in env_paths:
        if env_path:
            candidate = Path(env_path)
            if candidate.exists():
                return candidate

    def _probe_dir(base_dir: Path) -> Path | None:
        for rel in [
            Path("onnxruntime.dll"),
            Path("lib") / "onnxruntime.dll",
            Path("capi") / "onnxruntime.dll",
        ]:
            candidate = base_dir / rel
            if candidate.exists():
                return candidate
        return None

    try:
        import onnxruntime

        candidate = _probe_dir(Path(onnxruntime.__file__).resolve().parent)
        if candidate:
            return candidate
    except Exception:
        pass

    try:
        import sherpa_onnx

        candidate = _probe_dir(Path(sherpa_onnx.__file__).resolve().parent)
        if candidate:
            return candidate
    except Exception:
        pass

    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    system_candidate = system_root / "System32" / "onnxruntime.dll"
    if system_candidate.exists():
        return system_candidate

    for path_entry in os.environ.get("PATH", "").split(os.pathsep):
        if not path_entry:
            continue
        candidate = Path(path_entry) / "onnxruntime.dll"
        if candidate.exists():
            return candidate

    return None


def _resolve_offline_models_dir() -> Path | None:
    candidates = [
        os.environ.get("SONICINPUT_OFFLINE_MODELS_DIR"),
        os.environ.get("OFFLINE_MODELS_DIR"),
    ]
    for candidate in candidates:
        if candidate:
            models_dir = Path(candidate).expanduser()
            if not models_dir.is_absolute():
                models_dir = (Path.cwd() / models_dir).resolve()
            return models_dir
    return None


def _build_offline_bundle(
    exe_path: Path, models_dir: Path, dist_dir: Path
) -> Path | None:
    models_dir = models_dir.expanduser()
    if not models_dir.is_absolute():
        models_dir = (Path.cwd() / models_dir).resolve()

    if not models_dir.exists():
        print(f"[WARN] Offline models dir does not exist: {models_dir}")
        return None

    expected_dirs = [
        "sherpa-onnx-streaming-paraformer-bilingual-zh-en",
        "sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16",
    ]
    missing = [name for name in expected_dirs if not (models_dir / name).is_dir()]
    if missing:
        print("[WARN] Offline models dir is missing required model folders:")
        for name in missing:
            print(f"  - {name}")
        return None

    zip_base = dist_dir / f"{exe_path.stem}-offline"
    zip_path = zip_base.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()

    with tempfile.TemporaryDirectory(
        prefix=f"{exe_path.stem}-offline-staging-", dir=dist_dir
    ) as temp_dir:
        staging_dir = Path(temp_dir)
        shutil.copy2(exe_path, staging_dir / exe_path.name)
        shutil.copytree(models_dir, staging_dir / "models")
        zip_path = Path(shutil.make_archive(str(zip_base), "zip", root_dir=staging_dir))

    print(f"[OFFLINE] Bundle created: {zip_path}")
    return zip_path


version = get_version()
print(f"Building SonicInput v{version}")
build_start = time.perf_counter()

stage_start = time.perf_counter()
staged_assets_dir = stage_assets()
staged_qml_dir = stage_qml_runtime()
stage_elapsed = time.perf_counter() - stage_start
print(f"Using staged assets: {staged_assets_dir}")
print(f"Using staged QML runtime: {staged_qml_dir}")
print(f"[TIME] Asset staging: {stage_elapsed:.2f}s")
_remove_reserved_files("sherpa_onnx")
onnxruntime_dll = _find_onnxruntime_dll()
if not onnxruntime_dll:
    print("[ERROR] onnxruntime.dll not found; local ASR engine will not work.")
    print("[HINT] Ensure onnxruntime.dll is available or set ONNXRUNTIME_DLL_PATH.")
    sys.exit(1)
print(f"[INFO] Using onnxruntime.dll: {onnxruntime_dll}")

# Nuitka command with sherpa-onnx support
nuitka_cmd = [
    sys.executable,
    "-m",
    "nuitka",
    "--standalone",  # Create standalone distribution
    "--onefile",  # Package everything into single .exe
    "--assume-yes-for-downloads",  # Allow required Nuitka helper downloads in non-interactive builds
    "--windows-console-mode=attach",  # Attach to console when launched from cmd, GUI when double-clicked
    "--enable-plugin=pyside6",  # Enable PySide6 plugin for Qt support
    # Package inclusions
    "--include-package=sonicinput",  # Main application package
    "--include-package=sherpa_onnx",  # sherpa-onnx package (local ASR engine, includes C extension)
    "--include-package-data=sherpa_onnx",  # Include model/config data (remove NUL file if present)
    "--include-package-data=pypinyin",  # Runtime dictionaries used by lexicon matching
    f"--include-data-file={onnxruntime_dll}=sherpa_onnx/lib/onnxruntime.dll",
    "--include-module=sonicinput.utils.constants",  # Ensure constants.py is included
    "--include-module=PySide6.QtUiTools",  # qt_material needs QtUiTools at runtime
    "--include-package=PySide6.QtQml",  # Fluent QML settings/overlay host
    "--include-package=PySide6.QtQuick",  # Qt Quick scene graph/window support
    "--include-package=PySide6.QtQuickControls2",  # FluentWinUI3 controls style
    f"--include-data-dir={staged_assets_dir}=assets",  # UI translations/fonts and other assets
    f"--include-data-dir={staged_qml_dir}=.",  # Minimal QML imports used by Fluent surfaces
    "--include-data-dir=src/sonicinput/ui/qml=sonicinput/ui/qml",  # QML UI files
    # Windows API dependencies (for clipboard input and GUI operations)
    "--include-package=win32clipboard",  # Clipboard operations (clipboard input method)
    "--include-package=win32con",  # Windows constants
    "--include-package=win32api",  # Windows API wrapper
    "--include-package=win32gui",  # Windows GUI operations
    "--include-package=pywintypes",  # pywin32 base types
    # pynput backend support (alternative hotkey manager)
    "--include-package=pynput",  # pynput library for keyboard/mouse control
    # Exclude test/dev dependencies
    "--nofollow-import-to=pytest",
    "--nofollow-import-to=mypy",
    "--nofollow-import-to=tests",
    "--nofollow-import-to=scipy",
    "--nofollow-import-to=PySide6.QtPdf",
    "--nofollow-import-to=PySide6.QtWebEngineCore",
    "--nofollow-import-to=PySide6.QtWebEngineQuick",
    "--nofollow-import-to=PySide6.QtWebEngineWidgets",
    "--nofollow-import-to=PySide6.QtWebView",
    "--noinclude-dlls=qt6pdf.dll",
    "--noinclude-dlls=qt6pdfquick.dll",
    "--noinclude-dlls=qt6pdfwidgets.dll",
    "--noinclude-dlls=qt6web*.dll",
    "--noinclude-dlls=*webengine*.dll",
    # Application metadata
    "--windows-icon-from-ico=src/sonicinput/resources/icons/app_icon.ico",
    "--output-dir=dist",
    "app.py",
]
nuitka_cmd.extend(_qml_plugin_data_options(staged_qml_dir))

qml_runtime_dll_names = [
    "Qt6LabsQmlModels.dll",
    "Qt6QmlCore.dll",
    "Qt6QuickControls2Basic.dll",
    "Qt6QuickControls2BasicStyleImpl.dll",
    "Qt6QuickControls2FluentWinUI3StyleImpl.dll",
    "Qt6QuickControls2Fusion.dll",
    "Qt6QuickControls2FusionStyleImpl.dll",
    "Qt6QuickControls2Impl.dll",
    "Qt6QuickEffects.dll",
    "Qt6QuickLayouts.dll",
    "Qt6QuickShapes.dll",
]
for dll_name in qml_runtime_dll_names:
    dll_path = _resolve_pyside6_dll(dll_name)
    if not dll_path:
        raise RuntimeError(f"Required QML runtime library not found: {dll_name}")
    nuitka_cmd.append(f"--include-data-file={dll_path}={dll_name}")

qt_dll_names = [
    "Qt6UiTools.dll",
    "pyside6.abi3.dll",
    "pyside6qml.abi3.dll",
]
found_qt_dlls = False
for dll_name in qt_dll_names:
    dll_path = _resolve_pyside6_dll(dll_name)
    if dll_path:
        found_qt_dlls = True
        nuitka_cmd.append(f"--include-data-file={dll_path}=PySide6/{dll_name}")

shiboken_dll = _resolve_shiboken6_dll("shiboken6.abi3.dll")
if shiboken_dll:
    nuitka_cmd.append(
        f"--include-data-file={shiboken_dll}=shiboken6/shiboken6.abi3.dll"
    )

if not found_qt_dlls or not shiboken_dll:
    print("[WARN] QtUiTools dependencies not fully found; QtUiTools may fail to load.")

print("\nRunning Nuitka compilation...\n")
print(f"Command: {' '.join(nuitka_cmd)}\n")

# Execute compilation
compile_start = time.perf_counter()
result = subprocess.run(nuitka_cmd)
compile_elapsed = time.perf_counter() - compile_start
total_elapsed = time.perf_counter() - build_start

if result.returncode == 0:
    # Compilation successful, rename output file
    dist_dir = Path("dist")
    old_name = dist_dir / "app.exe"
    new_name = dist_dir / f"SonicInput-v{version}-win64.exe"

    if old_name.exists():
        # Delete target file if exists
        if new_name.exists():
            new_name.unlink()

        # Rename
        shutil.move(str(old_name), str(new_name))
        print("\n[SUCCESS] Build successful!")
        print(f"[OUTPUT] {new_name}")
        print(f"[SIZE] {new_name.stat().st_size / (1024 * 1024):.2f} MB")
        print(f"[TIME] Compile: {compile_elapsed:.2f}s")
        print(f"[TIME] Total: {total_elapsed:.2f}s")
        offline_models_dir = _resolve_offline_models_dir()
        if offline_models_dir:
            _build_offline_bundle(new_name, offline_models_dir, dist_dir)
    else:
        print(f"\n[WARNING] Expected output file not found: {old_name}")
        # List dist directory contents
        if dist_dir.exists():
            print("\nFiles in dist directory:")
            for file in dist_dir.iterdir():
                print(f"  - {file.name}")
        print(f"[TIME] Compile: {compile_elapsed:.2f}s")
        print(f"[TIME] Total: {total_elapsed:.2f}s")
else:
    print(f"\n[ERROR] Build failed with exit code {result.returncode}")
    print(f"[TIME] Compile: {compile_elapsed:.2f}s")
    print(f"[TIME] Total: {total_elapsed:.2f}s")

sys.exit(result.returncode)
