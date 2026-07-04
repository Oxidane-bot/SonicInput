"""Controller logging helper methods

Provides convenience methods to standardize logging patterns across controllers,
eliminating code duplication and improving consistency.
"""

from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from ...utils import ErrorMessageTranslator, app_logger


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
    @contextmanager
    def log_safe_operation(
        operation_name: str,
        error_domain: str,
        event_service: Optional[Any] = None,
        error_event_name: str = "generic_error",
        suppress_exceptions: bool = False,
    ) -> Generator[None, None, None]:
        """Context manager for safe operation wrapping with auto-logging

        Provides automatic error handling and logging for operations.
        Translates exceptions to user-friendly messages and emits events.

        Args:
            operation_name: Name of operation being performed
            error_domain: Domain for ErrorMessageTranslator (e.g., "recording", "transcription")
            event_service: Event service for emitting error events
            error_event_name: Event name to emit on error
            suppress_exceptions: Whether to catch and suppress exceptions

        Yields:
            None

        Raises:
            Original exception if suppress_exceptions=False

        Example:
            with ControllerLogging.log_safe_operation(
                "start_recording",
                "recording",
                self._events,
                Events.RECORDING_ERROR
            ):
                # operation code
                self._audio_service.start_recording(device_id)
        """
        try:
            app_logger.log_audio_event(f"Starting {operation_name}", {})
            yield
            app_logger.log_audio_event(f"{operation_name} completed successfully", {})
        except Exception as e:
            app_logger.log_error(e, operation_name)

            # Translate error to user-friendly message
            error_info = ErrorMessageTranslator.translate(e, error_domain)
            user_message = error_info.get("user_message", str(e))

            # Emit error event if service provided
            if event_service:
                try:
                    event_service.emit(error_event_name, user_message)
                except Exception as emit_error:
                    app_logger.log_error(
                        emit_error,
                        f"emit_error_event(event={error_event_name})",
                    )

            if not suppress_exceptions:
                raise

    @staticmethod
    def log_conditional_event(
        success: bool,
        operation_name: str,
        context: Dict[str, Any],
        error: Optional[Exception] = None,
        error_message: Optional[str] = None,
        success_event: Optional[str] = None,
        error_event: Optional[str] = None,
        event_service: Optional[Any] = None,
    ) -> None:
        """Log conditional success/failure events with consistent formatting

        Logs either success or failure events based on operation outcome.
        Emits appropriate events through event service if provided.

        Args:
            success: Whether operation succeeded
            operation_name: Name of operation
            context: Operation context/metrics
            error: Exception object (if failed)
            error_message: User-friendly error message (if failed)
            success_event: Event name to emit on success
            error_event: Event name to emit on failure
            event_service: Event service for emitting events

        Example:
            result = attempt_transcription()
            ControllerLogging.log_conditional_event(
                success=result is not None,
                operation_name="transcription",
                context={"duration": 2.5},
                error=None if result else Exception("Failed"),
                error_message="Transcription failed",
                success_event=Events.TRANSCRIPTION_COMPLETED,
                error_event=Events.TRANSCRIPTION_ERROR,
                event_service=self._events
            )
        """
        if success:
            app_logger.log_audio_event(f"{operation_name} succeeded", context)
            if success_event and event_service:
                try:
                    event_service.emit(success_event, context)
                except Exception as e:
                    app_logger.log_error(
                        e,
                        f"emit_success_event(event={success_event})",
                    )
        else:
            app_logger.log_audio_event(
                f"{operation_name} failed: {error_message or 'Unknown error'}",
                {**context, "error": str(error) if error else error_message},
            )
            if error:
                app_logger.log_error(error, operation_name)
            if error_event and event_service:
                try:
                    event_service.emit(error_event, error_message or str(error))
                except Exception as e:
                    app_logger.log_error(e, f"emit_error_event(event={error_event})")

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
