#!/usr/bin/env python3
"""Compatibility launcher for source checkouts and Nuitka builds."""

from pathlib import Path
import sys


def _run() -> None:
    source_root = Path(__file__).resolve().parent / "src"
    source_root_text = str(source_root)
    if source_root_text not in sys.path:
        sys.path.insert(0, source_root_text)

    from sonicinput.main import main

    main()


if __name__ == "__main__":
    _run()
