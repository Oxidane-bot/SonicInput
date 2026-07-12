"""Regression tests for packaged application asset discovery."""

from __future__ import annotations

from pathlib import Path
import sys

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from sonicinput.resources import runtime_assets


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_source_checkout_assets_are_discoverable() -> None:
    assets_dir = runtime_assets.get_assets_dir()

    assert assets_dir is not None
    assert (assets_dir / "icon.png").is_file()
    assert (
        assets_dir
        / "fonts"
        / "resource-han-rounded"
        / "ResourceHanRoundedCN-Regular.ttf"
    ).is_file()
    assert (assets_dir / "i18n" / "sonicinput_zh_CN.qm").is_file()


def test_wheel_layout_assets_are_discoverable(monkeypatch, tmp_path: Path) -> None:
    package_file = (
        tmp_path / "site-packages" / "sonicinput" / "resources" / "runtime_assets.py"
    )
    package_assets = package_file.parents[1] / "assets"
    package_assets.mkdir(parents=True)
    monkeypatch.setattr(runtime_assets, "__file__", str(package_file))

    assert runtime_assets.get_assets_dir() == package_assets


def test_wheel_layout_does_not_use_an_unrelated_parent_assets_dir(
    monkeypatch, tmp_path: Path
) -> None:
    package_file = (
        tmp_path / "site-packages" / "sonicinput" / "resources" / "runtime_assets.py"
    )
    unrelated_assets = package_file.parents[2] / "assets"
    unrelated_assets.mkdir(parents=True)
    monkeypatch.setattr(runtime_assets, "__file__", str(package_file))
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert runtime_assets.get_assets_dir() is None


def test_frozen_layout_prefers_executable_adjacent_assets(
    monkeypatch, tmp_path: Path
) -> None:
    executable = tmp_path / "SonicInput.exe"
    frozen_assets = tmp_path / "assets"
    frozen_assets.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert runtime_assets.get_assets_dir() == frozen_assets


def test_nuitka_bundle_assets_are_discoverable(monkeypatch, tmp_path: Path) -> None:
    package_file = (
        tmp_path / "app.dist" / "sonicinput" / "resources" / "runtime_assets.py"
    )
    bundle_assets = package_file.parents[2] / "assets"
    bundle_assets.mkdir(parents=True)
    monkeypatch.setattr(runtime_assets, "__file__", str(package_file))
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setitem(runtime_assets.__dict__, "__compiled__", {"compiled": True})

    assert runtime_assets.get_assets_dir() == bundle_assets


def test_runtime_consumers_share_the_asset_resolver() -> None:
    from sonicinput import main
    from sonicinput.core.services.ui_services import UILocalizationService
    from sonicinput.utils.startup_diagnostics import StartupDiagnostics

    assets_dir = runtime_assets.get_assets_dir()
    assert assets_dir is not None

    assert main.get_assets_dir is runtime_assets.get_assets_dir
    assert StartupDiagnostics()._resolve_assets_dir() == assets_dir
    assert UILocalizationService._resolve_translation_dir() == assets_dir / "i18n"


def test_hatch_packaging_keeps_assets_and_excludes_local_runtime_data() -> None:
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        config = tomllib.load(pyproject_file)

    targets = config["tool"]["hatch"]["build"]["targets"]
    sdist = targets["sdist"]
    wheel = targets["wheel"]
    excluded_paths = set(sdist["exclude"])

    assert sdist["force-include"]["assets"] == "assets"
    assert wheel["force-include"]["assets"] == "sonicinput/assets"
    assert sdist["skip-excluded-dirs"] is True
    assert {
        "/.appdata/",
        "/.models/",
        "/.mypy_cache/",
        "/.nuitka_cache/",
        "/.pytest*/",
        "/.release-venv/",
        "/.ruff_cache/",
        "/.tmp*/",
        "/.uv_cache/",
        "/.venv/",
        "/SonicInput/",
        "/artifacts/",
        "/build/",
        "/config/",
        "/dist/",
        "/logs/",
    } <= excluded_paths
