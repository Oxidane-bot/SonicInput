"""Compatibility exports for the dynamic event bus implementation."""

from .dynamic_event_system import (
    DynamicEventSystem,
    EventMetadata,
)
from .events import Events

EventBus = DynamicEventSystem

__all__ = [
    "EventBus",
    "DynamicEventSystem",
    "EventMetadata",
    "Events",
]
