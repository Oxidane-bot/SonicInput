import ast
from pathlib import Path


def test_hotkey_manager_uses_module_time_in_nested_event_filter() -> None:
    source_path = Path("src/sonicinput/core/hotkey_manager_pynput.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    time_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        and any(alias.name == "time" for alias in node.names)
    ]

    assert len(time_imports) == 1
    assert time_imports[0].lineno < 30
