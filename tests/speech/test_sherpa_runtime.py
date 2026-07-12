from __future__ import annotations

import os
from pathlib import Path

import pytest

from sonicinput.speech.sherpa_runtime import (
    configure_sherpa_dll_search_path,
    inspect_onnxruntime_candidates,
)


def test_onnxruntime_package_dll_precedes_system32() -> None:
    onnxruntime = pytest.importorskip("onnxruntime")

    ort_dll = Path(onnxruntime.__file__).resolve().parent / "capi" / "onnxruntime.dll"
    sherpa_dll = (
        Path(pytest.importorskip("sherpa_onnx").__file__).resolve().parent
        / "lib"
        / "onnxruntime.dll"
    )
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
    onnxruntime = pytest.importorskip("onnxruntime")

    ort_capi_dir = Path(onnxruntime.__file__).resolve().parent / "capi"

    configured = [Path(path) for path in configure_sherpa_dll_search_path()]

    assert ort_capi_dir in configured
