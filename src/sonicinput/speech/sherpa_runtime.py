"""Runtime setup for sherpa-onnx native dependencies."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict, List

from loguru import logger

_DLL_HANDLES: list[object] = []
_CONFIGURED = False


def _candidate_dll_dirs() -> list[Path]:
    dirs: list[Path] = []

    exe_dir = Path(sys.executable).resolve().parent
    dirs.append(exe_dir)

    try:
        import onnxruntime

        ort_dir = Path(onnxruntime.__file__).resolve().parent
        dirs.extend([ort_dir / "capi", ort_dir])
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"onnxruntime package not available for DLL setup: {exc}")

    spec = importlib.util.find_spec("sherpa_onnx")
    if spec and spec.submodule_search_locations:
        sherpa_dir = Path(list(spec.submodule_search_locations)[0]).resolve()
        dirs.extend([sherpa_dir / "lib", sherpa_dir])

    env_dll = os.environ.get("ONNXRUNTIME_DLL_PATH") or os.environ.get(
        "ONNXRUNTIME_DLL"
    )
    if env_dll:
        dirs.append(Path(env_dll).expanduser().resolve().parent)

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in dirs:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def configure_sherpa_dll_search_path() -> List[str]:
    """Prefer bundled/package ORT DLLs before importing ``sherpa_onnx``."""

    global _CONFIGURED
    if _CONFIGURED:
        return [str(path) for path in _candidate_dll_dirs() if path.exists()]

    configured: list[str] = []
    for dll_dir in _candidate_dll_dirs():
        if not dll_dir.exists():
            continue
        if hasattr(os, "add_dll_directory"):
            try:
                _DLL_HANDLES.append(os.add_dll_directory(str(dll_dir)))
            except OSError as exc:
                logger.debug(f"Failed to add DLL directory {dll_dir}: {exc}")
                continue
        configured.append(str(dll_dir))

    _CONFIGURED = True
    if configured:
        logger.debug(f"Configured sherpa-onnx DLL search paths: {configured}")
    return configured


def inspect_onnxruntime_candidates() -> List[Dict[str, object]]:
    """Return likely ORT DLL locations with version metadata for diagnostics."""

    candidates = [path / "onnxruntime.dll" for path in _candidate_dll_dirs()]
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    candidates.append(system32 / "onnxruntime.dll")

    result: list[dict[str, object]] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        exists = candidate.exists()
        info: dict[str, object] = {
            "path": str(candidate),
            "exists": exists,
            "product_version": None,
            "file_version": None,
        }
        if exists and sys.platform == "win32":
            try:
                import win32api

                version_info = win32api.GetFileVersionInfo(str(candidate), "\\")
                ms = version_info["FileVersionMS"]
                ls = version_info["FileVersionLS"]
                info["file_version"] = (
                    f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}."
                    f"{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Failed to inspect DLL version {candidate}: {exc}")
        result.append(info)
    return result
