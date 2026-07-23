from __future__ import annotations

import os
from pathlib import Path

import pytest

from sonicinput.speech.sherpa_runtime import (
    configure_sherpa_dll_search_path,
    inspect_onnxruntime_candidates,
)


def _optional_package_dir(package_name: str) -> Path:
    package = pytest.importorskip(package_name)
    package_file = getattr(package, "__file__", None)
    if package_file is None:
        pytest.skip(f"{package_name} is not installed as an importable package")
    return Path(package_file).resolve().parent


def test_onnxruntime_package_dll_precedes_system32() -> None:
    ort_dll = _optional_package_dir("onnxruntime") / "capi" / "onnxruntime.dll"
    sherpa_dll = _optional_package_dir("sherpa_onnx") / "lib" / "onnxruntime.dll"
    system32_dll = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "onnxruntime.dll"
    )

    candidates = inspect_onnxruntime_candidates()
    paths = [Path(str(candidate["path"])) for candidate in candidates]

    assert ort_dll in paths
    assert sherpa_dll in paths
    assert paths.index(sherpa_dll) < paths.index(ort_dll)
    if system32_dll.exists():
        assert paths.index(ort_dll) < paths.index(system32_dll)


def test_configure_sherpa_dll_search_path_includes_onnxruntime_capi() -> None:
    ort_capi_dir = _optional_package_dir("onnxruntime") / "capi"

    configured = [Path(path) for path in configure_sherpa_dll_search_path()]

    assert ort_capi_dir in configured
