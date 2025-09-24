"""Layout logic for arranging widgets on the canvas."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from PIL import Image, ImageDraw

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

        outer_margin = int(min(width, height) * 0.06)
        gutter = int(min(width, height) * 0.04)

        usable_width = width - 2 * outer_margin
        usable_height = height - 2 * outer_margin

        agenda_height = int(usable_height * 0.58)
        bottom_top = outer_margin + agenda_height + gutter
        bottom_height = height - outer_margin - bottom_top

        news_width = int((usable_width - gutter) * 0.6)
        market_left = outer_margin + news_width + gutter

        return {
            "agenda": LayoutArea(
                outer_margin,
                outer_margin,
                outer_margin + usable_width,
                outer_margin + agenda_height,
            ),
            "news": LayoutArea(
                outer_margin,
                bottom_top,
                outer_margin + news_width,
                bottom_top + bottom_height,
            ),
            "market": LayoutArea(
                market_left,
                bottom_top,
                market_left + (usable_width - news_width - gutter),
                bottom_top + bottom_height,
            ),
        }

    def area(self, widget_id: str) -> LayoutArea:
        """Return the layout area for a widget."""

        return self._areas[widget_id]

    def canvas(self) -> Image.Image:
        """Create a fresh canvas for rendering widgets."""

        width, height = self.settings.width, self.settings.height
        base = Image.new(
            "RGB",
            (width, height),
            color=DEFAULT_PALETTE.background,
        )
        draw = ImageDraw.Draw(base)

        top_colour = DEFAULT_PALETTE.background
        bottom_colour = tuple(
            min(255, int(channel * 1.05)) for channel in DEFAULT_PALETTE.background
        )

        for y in range(height):
            blend = y / max(height - 1, 1)
            colour = tuple(
                int(top_colour[i] * (1 - blend) + bottom_colour[i] * blend)
                for i in range(3)
            )
            draw.line([(0, y), (width, y)], fill=colour)

        return base

    @property
    def palette(self):  # pragma: no cover - simple proxy
        return DEFAULT_PALETTE


__all__ = ["LayoutArea", "LayoutManager"]
