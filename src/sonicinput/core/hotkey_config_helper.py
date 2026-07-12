"""Hotkey configuration helper utilities

Provides functions to handle both old and new hotkey configuration formats.

Note: This file uses raw string literals for legacy config keys ("hotkey", "hotkeys")
to maintain backward compatibility. New code should use ConfigKeys constants.
"""

from typing import List, Tuple


def get_hotkeys_from_config(config_service) -> Tuple[List[str], str]:
    """Extract hotkeys list and backend from configuration

    Supports both old and new configuration formats:
    - Old: "hotkeys": ["ctrl+shift+v", "f12"]
    - New: "hotkeys": {"keys": ["ctrl+shift+v", "f12"], "backend": "auto"}

    Args:
        config_service: Configuration service instance

    Returns:
        Tuple of (hotkeys_list, backend)
        - hotkeys_list: List of hotkey strings
        - backend: Backend name ("auto", "win32", or "pynput")
    """
    hotkeys_config = config_service.get_setting("hotkeys", None)

    if hotkeys_config is None:
        # Very old format: single "hotkey" key
        single_hotkey = config_service.get_setting("hotkey", "ctrl+alt+space")
        return ([single_hotkey], "auto")

    if isinstance(hotkeys_config, list):
        # Old format: list of hotkeys
        return (hotkeys_config, "auto")

    if isinstance(hotkeys_config, dict):
        # New format: dict with "keys" and "backend"
        keys = hotkeys_config.get("keys", ["ctrl+alt+space"])
        backend = hotkeys_config.get("backend", "auto")
        return (keys, backend)

    # Fallback
    return (["ctrl+alt+space"], "auto")
