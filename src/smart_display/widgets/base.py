"""Base classes and helpers for widgets."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Optional, TypeVar

from PIL import Image, ImageDraw

from ..display.layout import LayoutArea
from ..display.style import Palette

T = TypeVar("T")


@dataclass
class WidgetContext:
    """Context available during rendering."""

    area: LayoutArea
    palette: Palette
    now: datetime


class Widget(ABC, Generic[T]):
    """Abstract base class for all widgets."""

    def __init__(self, widget_id: str, enabled: bool = True) -> None:
        self.widget_id = widget_id
        self.enabled = enabled
        self._last_data: Optional[T] = None

    @abstractmethod
    def fetch(self) -> Optional[T]:
        """Retrieve the latest data for the widget."""

    @abstractmethod
    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, context: WidgetContext, data: T) -> None:
        """Render the widget into the provided drawing context."""

    def render(self, image: Image.Image, context: WidgetContext) -> None:
        """Fetch data and render the widget."""

        if not self.enabled:
            return
        data = self.fetch()
        if data is None:
            if self._last_data is not None:
                data = self._last_data
            else:
                self.draw_placeholder(image, context)
                return
        self._last_data = data
        draw = ImageDraw.Draw(image)
        self.draw(image, draw, context, data)

    def draw_placeholder(self, image: Image.Image, context: WidgetContext) -> None:
        """Render a neutral placeholder when data is unavailable."""

        draw = ImageDraw.Draw(image)
        area = context.area.inset(20, 20)
        draw.rectangle(
            [area.left, area.top, area.right, area.bottom],
            fill=(248, 248, 246),
            outline=context.palette.muted,
            width=2,
        )
        draw.text(
            (area.left + 10, area.top + 10),
            "No data",
            fill=context.palette.muted,
        )


__all__ = ["Widget", "WidgetContext"]
