"""Common operational utilities

Provides shared operational patterns to eliminate code duplication
across the codebase.
"""

import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

from PySide6.QtCore import QObject, QTimer

from ..utils import app_logger

T = TypeVar("T")


class ThreadSafeContainer(Generic[T]):
    """Thread-safe container for shared data with automatic locking"""

    def __init__(self, initial_value: Optional[T] = None):
        self._value: Optional[T] = initial_value
        self._lock = threading.RLock()

    def get(self) -> Optional[T]:
        """Get the current value thread-safely"""
        with self._lock:
            return self._value

    def set(self, value: T) -> None:
        """Set the value thread-safely"""
        with self._lock:
            self._value = value

    def update(self, updater: Callable[[Optional[T]], T]) -> T:
        """Update the value using an updater function thread-safely"""
        with self._lock:
            new_value = updater(self._value)
            self._value = new_value
            return new_value

    @contextmanager
    def lock_and_get(self):
        """Context manager for extended operations on the value"""
        with self._lock:
            yield self._value


class TimestampTracker:
    """Utility for tracking timestamps and calculating durations"""

    def __init__(self):
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.RLock()

    def mark(self, event: str) -> float:
        """Mark a timestamp for an event

        Args:
            event: Event name

        Returns:
            The timestamp that was recorded
        """
        timestamp = time.time()
        with self._lock:
            self._timestamps[event] = timestamp
        return timestamp

    def get_timestamp(self, event: str) -> Optional[float]:
        """Get the timestamp for an event

        Args:
            event: Event name

        Returns:
            Timestamp if found, None otherwise
        """
        with self._lock:
            return self._timestamps.get(event)

    def get_duration(
        self, start_event: str, end_event: Optional[str] = None
    ) -> Optional[float]:
        """Get duration between two events

        Args:
            start_event: Start event name
            end_event: End event name (if None, uses current time)

        Returns:
            Duration in seconds if start event exists, None otherwise
        """
        with self._lock:
            start_time = self._timestamps.get(start_event)
            if start_time is None:
                return None

            end_time = self._timestamps.get(end_event) if end_event else time.time()
            if end_time is None:
                return None

            return end_time - start_time

    def get_all_timestamps(self) -> Dict[str, float]:
        """Get all recorded timestamps

        Returns:
            Copy of all timestamps
        """
        with self._lock:
            return self._timestamps.copy()

    def clear(self) -> None:
        """Clear all timestamps"""
        with self._lock:
            self._timestamps.clear()


class ComponentTracker:
    """Utility for tracking component states and statistics"""

    def __init__(self):
        self._components: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def register_component(
        self, name: str, initial_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Register a component for tracking

        Args:
            name: Component name
            initial_data: Initial component data
        """
        with self._lock:
            self._components[name] = {
                "registered_at": time.time(),
                "last_updated": time.time(),
                "update_count": 0,
                **(initial_data or {}),
            }

    def update_component(self, name: str, data: Dict[str, Any]) -> None:
        """Update component data

        Args:
            name: Component name
            data: Data to update
        """
        with self._lock:
            if name in self._components:
                self._components[name].update(data)
                self._components[name]["last_updated"] = time.time()
                self._components[name]["update_count"] += 1

    def get_component_data(self, name: str) -> Optional[Dict[str, Any]]:
        """Get component data

        Args:
            name: Component name

        Returns:
            Component data if found, None otherwise
        """
        with self._lock:
            return (
                self._components.get(name, {}).copy()
                if name in self._components
                else None
            )

    def get_all_components(self) -> Dict[str, Dict[str, Any]]:
        """Get all component data

        Returns:
            Copy of all component data
        """
        with self._lock:
            return {name: data.copy() for name, data in self._components.items()}

    def remove_component(self, name: str) -> bool:
        """Remove a component from tracking

        Args:
            name: Component name

        Returns:
            True if component was removed, False if not found
        """
        with self._lock:
            if name in self._components:
                del self._components[name]
                return True
            return False


class EventCounter:
    """Utility for counting events with thread-safe operations"""

    def __init__(self):
        self._counts: Dict[str, int] = {}
        self._lock = threading.RLock()

    def increment(self, event: str, amount: int = 1) -> int:
        """Increment event count

        Args:
            event: Event name
            amount: Amount to increment

        Returns:
            New count value
        """
        with self._lock:
            self._counts[event] = self._counts.get(event, 0) + amount
            return self._counts[event]

    def get_count(self, event: str) -> int:
        """Get event count

        Args:
            event: Event name

        Returns:
            Current count (0 if event not found)
        """
        with self._lock:
            return self._counts.get(event, 0)

    def reset_count(self, event: str) -> int:
        """Reset event count to zero

        Args:
            event: Event name

        Returns:
            Previous count value
        """
        with self._lock:
            previous = self._counts.get(event, 0)
            self._counts[event] = 0
            return previous

    def get_all_counts(self) -> Dict[str, int]:
        """Get all event counts

        Returns:
            Copy of all counts
        """
        with self._lock:
            return self._counts.copy()

    def clear_all(self) -> None:
        """Clear all counts"""
        with self._lock:
            self._counts.clear()


class SafeTimer:
    """Thread-safe wrapper for QTimer with error handling"""

    def __init__(self, parent: Optional[QObject] = None):
        self._timer = QTimer(parent)
        self._callback: Optional[Callable] = None
        self._error_callback: Optional[Callable[[Exception], None]] = None

    def set_callback(
        self,
        callback: Callable,
        error_callback: Optional[Callable[[Exception], None]] = None,
    ):
        """Set the timer callback with optional error handling

        Args:
            callback: Function to call on timer timeout
            error_callback: Function to call if callback raises an exception
        """
        self._callback = callback
        self._error_callback = error_callback
        self._timer.timeout.connect(self._safe_callback)

    def _safe_callback(self):
        """Internal callback wrapper with error handling"""
        try:
            if self._callback:
                self._callback()
        except Exception as e:
            if self._error_callback:
                try:
                    self._error_callback(e)
                except Exception as inner_e:
                    app_logger.log_error(inner_e, "safe_timer_error_callback")
            else:
                app_logger.log_error(e, "safe_timer_callback")

    def start(self, interval_ms: int) -> None:
        """Start the timer

        Args:
            interval_ms: Timer interval in milliseconds
        """
        self._timer.start(interval_ms)

    def stop(self) -> None:
        """Stop the timer"""
        self._timer.stop()

    def is_active(self) -> bool:
        """Check if timer is active

        Returns:
            True if timer is running
        """
        return self._timer.isActive()

    def set_single_shot(self, single_shot: bool) -> None:
        """Set whether timer fires only once

        Args:
            single_shot: True for single shot, False for repeating
        """
        self._timer.setSingleShot(single_shot)


class PerformanceTracker:
    """Utility for tracking performance metrics"""

    def __init__(self):
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    @contextmanager
    def measure(self, operation: str):
        """Context manager for measuring operation duration

        Args:
            operation: Operation name
        """
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.record_duration(operation, duration)

    def record_duration(self, operation: str, duration: float) -> None:
        """Record operation duration

        Args:
            operation: Operation name
            duration: Duration in seconds
        """
        with self._lock:
            if operation not in self._metrics:
                self._metrics[operation] = {
                    "count": 0,
                    "total_duration": 0.0,
                    "min_duration": float("inf"),
                    "max_duration": 0.0,
                    "last_duration": 0.0,
                }

            metrics = self._metrics[operation]
            metrics["count"] += 1
            metrics["total_duration"] += duration
            metrics["min_duration"] = min(metrics["min_duration"], duration)
            metrics["max_duration"] = max(metrics["max_duration"], duration)
            metrics["last_duration"] = duration

    def get_metrics(self, operation: str) -> Optional[Dict[str, Any]]:
        """Get metrics for an operation

        Args:
            operation: Operation name

        Returns:
            Metrics dictionary if found, None otherwise
        """
        with self._lock:
            if operation not in self._metrics:
                return None

            metrics = self._metrics[operation].copy()
            if metrics["count"] > 0:
                metrics["average_duration"] = (
                    metrics["total_duration"] / metrics["count"]
                )
            else:
                metrics["average_duration"] = 0.0

            return metrics

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get all performance metrics

        Returns:
            Dictionary of all metrics
        """
        with self._lock:
            result = {}
            for operation, metrics in self._metrics.items():
                result[operation] = metrics.copy()
                if metrics["count"] > 0:
                    result[operation]["average_duration"] = (
                        metrics["total_duration"] / metrics["count"]
                    )
                else:
                    result[operation]["average_duration"] = 0.0
            return result

    def reset_metrics(self, operation: Optional[str] = None) -> None:
        """Reset metrics for an operation or all operations

        Args:
            operation: Operation name (if None, resets all)
        """
        with self._lock:
            if operation:
                if operation in self._metrics:
                    del self._metrics[operation]
            else:
                self._metrics.clear()


def safe_file_operation(
    file_path: Path, operation: str, *args, **kwargs
) -> tuple[bool, Optional[str]]:
    """Safely perform file operations with consistent error handling

    Args:
        file_path: Path to file
        operation: Operation to perform ('read', 'write', 'delete', 'exists')
        *args: Additional arguments for the operation
        **kwargs: Additional keyword arguments for the operation

    Returns:
        Tuple of (success, error_message)
    """
    try:
        if operation == "read":
            if not file_path.exists():
                return False, "File does not exist"
            with open(file_path, "r", encoding="utf-8") as f:
                return True, f.read()

        elif operation == "write":
            content = args[0] if args else kwargs.get("content", "")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True, None

        elif operation == "delete":
            if file_path.exists():
                file_path.unlink()
            return True, None

        elif operation == "exists":
            return file_path.exists(), None

        else:
            return False, f"Unknown operation: {operation}"

    except Exception as e:
        return False, str(e)


def log_with_context(
    event_name: str, data: Optional[Dict[str, Any]] = None, component: str = "unknown"
) -> None:
    """Log event with consistent context information

    Args:
        event_name: Event name
        data: Additional event data
        component: Component name
    """
    event_data = {"component": component, "timestamp": time.time(), **(data or {})}
    app_logger.log_audio_event(event_name, event_data)
