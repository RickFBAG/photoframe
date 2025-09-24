"""Layout logic for arranging widgets on the canvas."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from PIL import Image

from ..config import DisplaySettings
from .style import DEFAULT_PALETTE


@dataclass(frozen=True)
class LayoutArea:
    """Represents a rectangular area on the canvas."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def inset(self, dx: int, dy: int) -> "LayoutArea":
        """Return a new area reduced by the provided insets."""

        return LayoutArea(
            self.left + dx,
            self.top + dy,
            self.right - dx,
            self.bottom - dy,
        )


class LayoutManager:
    """Compute layout regions for widgets based on display size."""

    def __init__(self, settings: DisplaySettings) -> None:
        self.settings = settings
        self._areas = self._build_default_layout()

    def _build_default_layout(self) -> Dict[str, LayoutArea]:
        width, height = self.settings.width, self.settings.height
        agenda_height = int(height * 0.58)
        news_width = int(width * 0.62)

        return {
            "agenda": LayoutArea(0, 0, width, agenda_height),
            "news": LayoutArea(0, agenda_height, news_width, height),
            "market": LayoutArea(news_width, agenda_height, width, height),
        }

    def area(self, widget_id: str) -> LayoutArea:
        """Return the layout area for a widget."""

        return self._areas[widget_id]

    def canvas(self) -> Image.Image:
        """Create a fresh canvas for rendering widgets."""

        return Image.new(
            "RGB",
            (self.settings.width, self.settings.height),
            color=DEFAULT_PALETTE.background,
        )

    @property
    def palette(self):  # pragma: no cover - simple proxy
        return DEFAULT_PALETTE


__all__ = ["LayoutArea", "LayoutManager"]
