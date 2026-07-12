"""Release metadata must stay aligned across its supported runtime surfaces."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from sonicinput import __version__
from sonicinput.core.services.config.app_constants import AppInfo


def test_runtime_versions_match_project_metadata() -> None:
    with Path("pyproject.toml").open("rb") as pyproject_file:
        project_version = tomllib.load(pyproject_file)["project"]["version"]

    assert __version__ == project_version
    assert AppInfo.VERSION == project_version
