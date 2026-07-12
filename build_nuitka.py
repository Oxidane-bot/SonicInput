#!/usr/bin/env python
"""
Nuitka compilation script - Package as single file executable

This script compiles SonicInput into a standalone Windows executable using Nuitka.
Includes support for sherpa-onnx C extension modules and all required dependencies.
"""

import hashlib
import json
import os
import shutil
import string
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree


_QML_ROOT_MODULES = (
    "QtQml",
    "QtQuick",
    "QtQuick/Controls",
)
_QML_TREE_MODULES = (
    "QtQml/Models",
    "QtQml/WorkerScript",
    "QtQuick/Controls/Basic",
    "QtQuick/Controls/FluentWinUI3",
    "QtQuick/Controls/Fusion",
    "QtQuick/Controls/impl",
    "QtQuick/Effects",
    "QtQuick/Layouts",
    "QtQuick/Templates",
    "QtQuick/Window",
)


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


def _fingerprint_files(paths: list[Path], context: dict[str, object]) -> str:
    """Return a cheap, deterministic cache key for staged build inputs."""
    digest = hashlib.sha256()
    digest.update(json.dumps(context, sort_keys=True).encode("utf-8"))
    for path in sorted(paths, key=lambda item: item.as_posix().casefold()):
        stat = path.stat()
        digest.update(
            f"{path.as_posix()}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8")
        )
    return digest.hexdigest()


def _stage_manifest_path(staging_dir: Path) -> Path:
    return staging_dir.parent / f".{staging_dir.name}.manifest.json"


def _stage_cache_is_current(staging_dir: Path, fingerprint: str) -> bool:
    if not staging_dir.is_dir():
        return False
    manifest_path = _stage_manifest_path(staging_dir)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return manifest.get("fingerprint") == fingerprint


def _write_stage_manifest(staging_dir: Path, fingerprint: str) -> None:
    manifest_path = _stage_manifest_path(staging_dir)
    temporary_path = manifest_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps({"fingerprint": fingerprint}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)


def _reset_staging_dir(staging_dir: Path) -> None:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    _stage_manifest_path(staging_dir).unlink(missing_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)


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


def _asset_source_paths(assets_dir: Path) -> list[Path]:
    font_source_dir = assets_dir / "fonts" / "resource-han-rounded"
    return [
        assets_dir / "icon.png",
        *sorted((assets_dir / "i18n").glob("*.qm")),
        *sorted((assets_dir / "i18n").glob("*.ts")),
        font_source_dir / "ResourceHanRoundedCN-Regular.ttf",
        font_source_dir / "ResourceHanRoundedCN-Bold.ttf",
        font_source_dir / "OFL-License.txt",
        font_source_dir / "FONT-NOTICE.txt",
    ]


def stage_assets() -> Path:
    assets_dir = Path("assets")
    staging_dir = Path("build") / "staging" / "assets"
    fingerprint = _fingerprint_files(
        _asset_source_paths(assets_dir), {"stage": "assets-v2"}
    )
    if _stage_cache_is_current(staging_dir, fingerprint):
        print(f"[CACHE] Reusing staged assets: {staging_dir}")
        return staging_dir

    _reset_staging_dir(staging_dir)

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

    _write_stage_manifest(staging_dir, fingerprint)
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


def _qml_stage_source_paths(source_qml_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for import_name in _QML_ROOT_MODULES:
        source_dir = source_qml_dir / import_name
        if not source_dir.is_dir():
            raise RuntimeError(f"Required QML import not found: {source_dir}")
        paths.extend(path for path in source_dir.iterdir() if path.is_file())

    for import_name in _QML_TREE_MODULES:
        source_dir = source_qml_dir / import_name
        if not source_dir.is_dir():
            raise RuntimeError(f"Required QML import not found: {source_dir}")
        paths.extend(path for path in source_dir.rglob("*") if path.is_file())
    return paths


def _copy_qml_root_files(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for path in source_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, target_dir / path.name)


def stage_qml_runtime() -> Path:
    """Stage the verified QML runtime closure used by the Fluent UI surfaces."""
    source_qml_dir = _resolve_pyside6_qml_dir()
    try:
        import PySide6
    except Exception as exc:
        raise RuntimeError("PySide6 is required to stage QML runtime modules.") from exc

    staging_dir = Path("build") / "staging" / "qml"
    target_root = staging_dir / "PySide6" / "qml"
    fingerprint = _fingerprint_files(
        _qml_stage_source_paths(source_qml_dir),
        {
            "stage": "qml-v2",
            "pyside6_version": getattr(PySide6, "__version__", "unknown"),
            "root_modules": _QML_ROOT_MODULES,
            "tree_modules": _QML_TREE_MODULES,
        },
    )
    if _stage_cache_is_current(staging_dir, fingerprint):
        print(f"[CACHE] Reusing staged QML runtime: {staging_dir}")
        return staging_dir

    _reset_staging_dir(staging_dir)
    target_root.mkdir(parents=True, exist_ok=True)

    for import_name in _QML_ROOT_MODULES:
        source_dir = source_qml_dir / import_name
        _copy_qml_root_files(source_dir, target_root / import_name)

    for import_name in _QML_TREE_MODULES:
        source_dir = source_qml_dir / import_name
        shutil.copytree(source_dir, target_root / import_name, dirs_exist_ok=True)

    _write_stage_manifest(staging_dir, fingerprint)
    return staging_dir


def _qml_plugin_data_options(staging_dir: Path) -> list[str]:
    """Keep QML module plugins when Nuitka treats staged DLLs as non-data files."""
    qml_root = staging_dir / "PySide6" / "qml"
    options = []
    for plugin_path in sorted(qml_root.rglob("*plugin.dll")):
        relative_path = plugin_path.relative_to(staging_dir).as_posix()
        options.append(f"--include-data-file={plugin_path}={relative_path}")
    return options


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


def _bundled_onnxruntime_dll() -> Path:
    """Verify the ORT DLL provided by the package included in the release."""
    try:
        import onnxruntime
    except Exception as exc:
        raise RuntimeError(
            "onnxruntime is required for the local ASR release build."
        ) from exc

    dll_path = Path(onnxruntime.__file__).resolve().parent / "capi" / "onnxruntime.dll"
    if not dll_path.is_file():
        raise RuntimeError(f"Bundled onnxruntime.dll not found: {dll_path}")
    return dll_path


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


def _build_path(environment_name: str, default_path: str) -> Path:
    configured_path = Path(os.environ.get(environment_name, default_path)).expanduser()
    if configured_path.is_absolute():
        return configured_path
    return Path.cwd() / configured_path


def _validate_nuitka_output(output_dir: Path) -> None:
    standalone_dir = output_dir / "app.dist"
    report_path = output_dir / "nuitka-report.xml"
    if not standalone_dir.is_dir():
        raise RuntimeError(f"Standalone output not found: {standalone_dir}")
    if not report_path.is_file():
        raise RuntimeError(f"Nuitka report not found: {report_path}")

    required_paths = [
        Path("assets/icon.png"),
        Path("assets/i18n/sonicinput_en_US.qm"),
        Path("assets/i18n/sonicinput_zh_CN.qm"),
        Path("onnxruntime.dll"),
        Path("onnxruntime/capi/onnxruntime.dll"),
        Path("onnxruntime/capi/onnxruntime_pybind11_state.pyd"),
        Path("pypinyin/phrases_dict.json"),
        Path("pypinyin/pinyin_dict.json"),
        Path("PySide6/qml/QtQuick/Controls/FluentWinUI3/qmldir"),
        Path("sonicinput/ui/qml/FluentSettingsWindow.qml"),
    ]
    missing = [
        path.as_posix()
        for path in required_paths
        if not (standalone_dir / path).is_file()
    ]
    if not list((standalone_dir / "sherpa_onnx" / "lib").glob("_sherpa_onnx*.pyd")):
        missing.append("sherpa_onnx/lib/_sherpa_onnx*.pyd")
    if missing:
        raise RuntimeError("Missing packaged runtime files: " + ", ".join(missing))

    forbidden_paths = [
        Path("PySide6/qml/QtQuick/VirtualKeyboard"),
        Path("PySide6/qml/QtWebEngine"),
        Path("cryptography"),
    ]
    unexpected = [
        path.as_posix() for path in forbidden_paths if (standalone_dir / path).exists()
    ]
    if (standalone_dir / "samplerate.pyd").exists():
        unexpected.append("samplerate.pyd")
    if unexpected:
        raise RuntimeError("Unexpected packaged files: " + ", ".join(unexpected))

    report = ElementTree.parse(report_path)
    module_names = {
        module.attrib["name"]
        for module in report.iter("module")
        if "name" in module.attrib
    }
    onnxruntime_module_count = sum(
        name == "onnxruntime" or name.startswith("onnxruntime.")
        for name in module_names
    )
    if onnxruntime_module_count > 40:
        raise RuntimeError(
            "ONNX Runtime module closure is unexpectedly large: "
            f"{onnxruntime_module_count} modules"
        )
    if any(name == "sympy" or name.startswith("sympy.") for name in module_names):
        raise RuntimeError("Unexpected SymPy dependency in release payload")

    payload_size = sum(
        path.stat().st_size for path in standalone_dir.rglob("*") if path.is_file()
    )
    print(
        f"[AUDIT] Standalone payload: {payload_size / (1024 * 1024):.2f} MB; "
        f"onnxruntime modules: {onnxruntime_module_count}"
    )


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

    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        archive.write(exe_path, exe_path.name)
        for model_path in sorted(models_dir.rglob("*")):
            if model_path.is_file():
                archive_name = (
                    Path("models") / model_path.relative_to(models_dir)
                ).as_posix()
                archive.write(model_path, archive_name)

    print(f"[OFFLINE] Bundle created: {zip_path}")
    return zip_path


version = get_version()
print(f"Building SonicInput v{version}")
build_start = time.perf_counter()
nuitka_output_dir = _build_path("SONICINPUT_NUITKA_WORK_DIR", "build/nuitka")
release_dir = _build_path("SONICINPUT_RELEASE_DIR", f"dist/release/v{version}")
nuitka_output_dir.mkdir(parents=True, exist_ok=True)
release_dir.mkdir(parents=True, exist_ok=True)

stage_start = time.perf_counter()
staged_assets_dir = stage_assets()
staged_qml_dir = stage_qml_runtime()
stage_elapsed = time.perf_counter() - stage_start
print(f"Using staged assets: {staged_assets_dir}")
print(f"Using staged QML runtime: {staged_qml_dir}")
print(f"[TIME] Asset staging: {stage_elapsed:.2f}s")
bundled_onnxruntime_dll = _bundled_onnxruntime_dll()
print(f"[INFO] Verified bundled onnxruntime.dll: {bundled_onnxruntime_dll}")

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
    "--include-package-data=sherpa_onnx",  # Include model/config data and C extension
    "--include-package-data=pypinyin",  # Runtime dictionaries used by lexicon matching
    "--noinclude-data-files=**/NUL",  # Do not mutate site-packages for a Windows-reserved filename
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
    f"--output-dir={nuitka_output_dir}",
    f"--report={nuitka_output_dir / 'nuitka-report.xml'}",
    "--report-diffable",
    "app.py",
]
nuitka_cmd.extend(_qml_plugin_data_options(staged_qml_dir))

qml_runtime_dll_names = [
    "Qt6QmlMeta.dll",
    "Qt6QmlModels.dll",
    "Qt6QmlWorkerScript.dll",
    "Qt6QuickControls2Basic.dll",
    "Qt6QuickControls2BasicStyleImpl.dll",
    "Qt6QuickControls2FluentWinUI3StyleImpl.dll",
    "Qt6QuickControls2Fusion.dll",
    "Qt6QuickControls2FusionStyleImpl.dll",
    "Qt6QuickControls2Impl.dll",
    "Qt6QuickEffects.dll",
    "Qt6QuickLayouts.dll",
    "Qt6QuickTemplates2.dll",
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
compiled_exe_path = nuitka_output_dir / "app.exe"
compiled_report_path = nuitka_output_dir / "nuitka-report.xml"
# A successful compiler invocation must produce a fresh executable. Removing a
# previous executable or report prevents stale build data from being promoted
# or used to audit a new release.
compiled_exe_path.unlink(missing_ok=True)
compiled_report_path.unlink(missing_ok=True)
compile_start = time.perf_counter()
result = subprocess.run(nuitka_cmd)
compile_elapsed = time.perf_counter() - compile_start
total_elapsed = time.perf_counter() - build_start

if result.returncode == 0:
    try:
        _validate_nuitka_output(nuitka_output_dir)
    except Exception as exc:
        print(f"\n[ERROR] Packaged output audit failed: {exc}")
        sys.exit(1)

    # Compilation successful, rename output file
    old_name = compiled_exe_path
    new_name = release_dir / f"SonicInput-v{version}-win64.exe"

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
            _build_offline_bundle(new_name, offline_models_dir, release_dir)
    else:
        print(f"\n[ERROR] Expected output file not found: {old_name}")
        # List the isolated Nuitka output directory for diagnostics.
        if nuitka_output_dir.exists():
            print("\nFiles in Nuitka output directory:")
            for file in nuitka_output_dir.iterdir():
                print(f"  - {file.name}")
        print(f"[TIME] Compile: {compile_elapsed:.2f}s")
        print(f"[TIME] Total: {total_elapsed:.2f}s")
        sys.exit(1)
else:
    print(f"\n[ERROR] Build failed with exit code {result.returncode}")
    print(f"[TIME] Compile: {compile_elapsed:.2f}s")
    print(f"[TIME] Total: {total_elapsed:.2f}s")

sys.exit(result.returncode)
