"""Resolve application assets for source, wheel, and frozen runtimes."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterator


def _candidate_assets_dirs() -> Iterator[Path]:
    """Yield asset directories in runtime-specific priority order."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    is_frozen = bool(
        getattr(sys, "frozen", False) or bundle_dir or "__compiled__" in globals()
    )
    if is_frozen:
        if bundle_dir:
            yield Path(bundle_dir) / "assets"
        yield Path(sys.executable).resolve().parent / "assets"

    package_dir = Path(__file__).resolve().parent.parent
    # Wheels place assets next to the Python package. Source checkouts and
    # frozen bundles use their respective roots instead.
    yield package_dir / "assets"
    if package_dir.parent.name == "src":
        yield package_dir.parent.parent / "assets"
    elif is_frozen:
        yield package_dir.parent / "assets"


def get_assets_dir() -> Path | None:
    """Return the first existing bundled asset directory, if available."""
    checked: set[Path] = set()
    for assets_dir in _candidate_assets_dirs():
        if assets_dir in checked:
            continue
        checked.add(assets_dir)
        if assets_dir.is_dir():
            return assets_dir
    return None
