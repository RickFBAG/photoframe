from __future__ import annotations

from .base import (
    ClockWidget,
    MessageWidget,
    WidgetDefinition,
    WidgetError,
    WidgetField,
    WidgetRegistry,
    create_default_registry,
)

try:  # pragma: no cover - optional calendar dependencies
    from .calendar import CalendarWidget
except ImportError:  # pragma: no cover - degraded environment
    CalendarWidget = None  # type: ignore[assignment]

__all__ = [
    "ClockWidget",
    "MessageWidget",
    "WidgetDefinition",
    "WidgetError",
    "WidgetField",
    "WidgetRegistry",
    "create_default_registry",
]

if CalendarWidget is not None:
    __all__.append("CalendarWidget")
