"""Controller logging helper methods

Provides convenience methods to standardize logging patterns across controllers,
eliminating code duplication and improving consistency.
"""

from typing import Any, Dict, Optional

from ...utils import app_logger


class ControllerLogging:
    """Static helper methods for controller logging patterns"""

    @staticmethod
    def log_initialization(
        component_name: str, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log component initialization with consistent formatting

        Args:
            component_name: Name of the component being initialized
            context: Optional context data (config details, version, etc.)

        Example:
            ControllerLogging.log_initialization("RecordingController")
            ControllerLogging.log_initialization(
                "AIProcessingController",
                {"ai_enabled": True, "provider": "groq"}
            )
        """
        default_context = {"component": component_name}
        if context:
            default_context.update(context)

        app_logger.log_audio_event(f"{component_name} initialized", default_context)

    @staticmethod
    def log_state_change(
        component_name: str,
        old_state: Any,
        new_state: Any,
        context: Optional[Dict[str, Any]] = None,
        is_forced: bool = False,
    ) -> None:
        """Log state transitions with consistent formatting

        Args:
            component_name: Component whose state changed
            old_state: Previous state value
            new_state: New state value
            context: Additional context for the state change
            is_forced: Whether state change was forced (e.g., recovery)

        Example:
            ControllerLogging.log_state_change(
                "recording",
                RecordingState.IDLE,
                RecordingState.RECORDING,
                {"device_id": 0}
            )

            ControllerLogging.log_state_change(
                "app",
                AppState.PROCESSING,
                AppState.IDLE,
                {"reason": "error_recovery"},
                is_forced=True
            )
        """
        old_state_name = (
            old_state.name if hasattr(old_state, "name") else str(old_state)
        )
        new_state_name = (
            new_state.name if hasattr(new_state, "name") else str(new_state)
        )

        message = (
            f"State transition: {component_name} {old_state_name} -> {new_state_name}"
        )
        if is_forced:
            message += " (forced recovery)"

        ctx = context or {}
        ctx.update(
            {
                "component": component_name,
                "old_state": old_state_name,
                "new_state": new_state_name,
                "forced": is_forced,
            }
        )

        app_logger.log_audio_event(message, ctx)
