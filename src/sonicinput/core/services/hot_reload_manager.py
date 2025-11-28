"""Simplified Hot Reload Manager

Minimal hot-reload system following YAGNI principle.
Uses simple callback pattern with hard-coded reload order.
"""

from typing import Any, Dict, List, Protocol

from ...utils import app_logger


class IHotReloadable(Protocol):
    """Simple hot-reload callback interface

    Services implement this to receive config change notifications.
    """

    def get_config_dependencies(self) -> List[str]:
        """Return list of config keys this service depends on

        Returns:
            Config key paths like ["transcription.provider", "audio.device_id"]
        """
        ...

    def on_config_changed(
        self, changed_keys: List[str], new_config: Dict[str, Any]
    ) -> bool:
        """Handle config change notification

        Args:
            changed_keys: List of changed config key paths
            new_config: New configuration dictionary

        Returns:
            True if reload successful, False otherwise
        """
        ...


class HotReloadManager:
    """Simplified hot reload manager

    Coordinates config hot-reload across services with:
    - Hard-coded reload order (no topological sorting)
    - Fail-fast with user notification (no two-phase commit/rollback)
    - Simple callback interface

    Usage:
        manager = HotReloadManager()
        manager.register_service("audio", audio_service)
        manager.register_service("speech", speech_service)
        manager.notify_config_changed(changed_keys, new_config)
    """

    # Hard-coded service reload order (replaces topological sorting)
    RELOAD_ORDER = ["config", "audio", "speech", "ai", "hotkey", "input"]

    def __init__(self):
        """Initialize hot reload manager"""
        self._services: Dict[str, IHotReloadable] = {}
        self._config_to_services: Dict[str, List[str]] = {}

    def register_service(self, name: str, service: IHotReloadable) -> None:
        """Register a service for hot reload

        Args:
            name: Service name (must be in RELOAD_ORDER)
            service: Service instance implementing IHotReloadable
        """
        self._services[name] = service

        # Build reverse index: config_key -> [service_names]
        for config_key in service.get_config_dependencies():
            if config_key not in self._config_to_services:
                self._config_to_services[config_key] = []
            self._config_to_services[config_key].append(name)

    def notify_config_changed(
        self, changed_keys: List[str], new_config: Dict[str, Any]
    ) -> bool:
        """Notify services of config changes

        Args:
            changed_keys: List of changed config key paths
            new_config: New configuration dictionary

        Returns:
            True if all reloads successful, False if any failed
        """
        # Find affected services
        affected = set()
        for key in changed_keys:
            if key in self._config_to_services:
                affected.update(self._config_to_services[key])

        if not affected:
            return True

        # Reload services in hard-coded order (fail-fast)
        for service_name in self.RELOAD_ORDER:
            if service_name in affected and service_name in self._services:
                service = self._services[service_name]

                try:
                    success = service.on_config_changed(changed_keys, new_config)
                    if not success:
                        app_logger.log_error(
                            Exception(f"Config reload failed for {service_name}"),
                            "hot_reload",
                        )
                        return False
                except Exception as e:
                    app_logger.log_error(e, f"hot_reload_{service_name}")
                    return False

        return True
