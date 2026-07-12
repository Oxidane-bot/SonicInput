"""Regression checks for source files that Hatch discovers through Git rules."""

from pathlib import Path
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_tracked_runtime_python_files_are_not_gitignored() -> None:
    result = subprocess.run(
        ["git", "ls-files", "-ci", "--exclude-standard", "--", "src"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )

    ignored_python_files = [
        path for path in result.stdout.splitlines() if Path(path).suffix == ".py"
    ]

    assert ignored_python_files == []
