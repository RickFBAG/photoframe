from __future__ import annotations

from .base import Surface, WidgetBase, WidgetError, WidgetField
from .clock import ClockWidget
from .message import MessageWidget
from .registry import WidgetRegistry

__all__ = [
    "Surface",
    "WidgetBase",
    "WidgetError",
    "WidgetField",
    "WidgetRegistry",
    "MessageWidget",
    "ClockWidget",
]
