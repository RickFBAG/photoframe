from __future__ import annotations

from .base import WidgetBase, WidgetError, WidgetField, WidgetRegistry
from .clock import ClockWidget
from .message import MessageWidget
from .surface import Surface, Theme

__all__ = [
    "WidgetBase",
    "WidgetError",
    "WidgetField",
    "WidgetRegistry",
    "Surface",
    "Theme",
    "ClockWidget",
    "MessageWidget",
    "create_default_registry",
]


def create_default_registry() -> WidgetRegistry:
    registry = WidgetRegistry()
    registry.register(MessageWidget())
    registry.register(ClockWidget())
    return registry
