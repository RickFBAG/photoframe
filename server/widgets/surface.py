from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from PIL import Image, ImageDraw, ImageFont

__all__ = ["Theme", "Surface"]


@dataclass(frozen=True)
class Theme:
    """Simple colour and spacing definition for widget surfaces."""

    background: str = "#ffffff"
    primary: str = "#111111"
    secondary: str = "#444444"
    accent: str = "#cc3333"
    margin: int = 24
    grid: int = 8

    @classmethod
    def default(cls) -> "Theme":
        return cls()


class _FontLibrary:
    """Cache for truetype fonts used by widget surfaces."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

    def _load_from_paths(
        self, key: str, size: int, paths: Sequence[str]
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        cache_key = (key, size)
        if cache_key in self._cache:
            return self._cache[cache_key]

        for path in paths:
            if Path(path).exists():
                font = ImageFont.truetype(path, size=size)
                self._cache[cache_key] = font
                return font

        font = ImageFont.load_default()
        self._cache[cache_key] = font
        return font

    def monospace(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        return self._load_from_paths(
            "monospace",
            size,
            (
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            ),
        )

    def sans(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        return self._load_from_paths(
            "sans",
            size,
            (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ),
        )


_FONT_LIBRARY = _FontLibrary()


class Surface:
    """Helper around :mod:`PIL` drawing primitives following design guidelines."""

    def __init__(self, size: tuple[int, int], theme: Theme | None = None) -> None:
        self.theme = theme or Theme.default()
        self.width, self.height = size
        self.image = Image.new("RGB", size, color=self.theme.background)
        self.draw = ImageDraw.Draw(self.image)
        self.fonts = _FONT_LIBRARY

    @property
    def content_box(self) -> tuple[float, float, float, float]:
        margin = float(self.theme.margin)
        return (margin, margin, float(self.width) - margin, float(self.height) - margin)

    def text_size(self, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
        bbox = self.draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return width, height

    def draw_text(
        self,
        position: tuple[float, float],
        text: str,
        *,
        font: ImageFont.ImageFont,
        fill: str,
        anchor: str = "la",
    ) -> None:
        self.draw.text(position, text, font=font, fill=fill, anchor=anchor)

    def fit_text(
        self,
        text: str,
        factory: Callable[[int], ImageFont.ImageFont],
        max_width: float,
        max_height: float,
        *,
        minimum_size: int = 8,
    ) -> ImageFont.ImageFont:
        size = int(min(max_width, max_height))
        size = max(size, minimum_size)
        while size > minimum_size:
            font = factory(size)
            width, height = self.text_size(text, font)
            if width <= max_width and height <= max_height:
                return font
            size -= 2
        return factory(minimum_size)
