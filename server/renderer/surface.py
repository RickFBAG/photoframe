from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT_NAMES: Sequence[str] = (
    "DejaVuSans.ttf",
    "DejaVuSansDisplay.ttf",
    "Arial.ttf",
    "LiberationSans-Regular.ttf",
)


@lru_cache(maxsize=128)
def _load_font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size=size)
    except OSError:
        return ImageFont.load_default()


class FontManager:
    """Utility for loading fonts with caching and fallbacks."""

    def __init__(self, search_paths: Iterable[Path] | None = None, fallback: str | None = None) -> None:
        self._search_paths = [Path(p) for p in (search_paths or [])]
        self._fallback = fallback or DEFAULT_FONT_NAMES[0]

    def _resolve(self, name: str | None) -> str:
        candidates: list[str] = []
        if name:
            candidates.append(name)
        candidates.extend(DEFAULT_FONT_NAMES)
        candidates.append(self._fallback)

        for candidate in candidates:
            if os.path.isabs(candidate) and Path(candidate).exists():
                return candidate
            for base in self._search_paths:
                path = base / candidate
                if path.exists():
                    return str(path)
        return candidates[0]

    def get(self, size: int, name: str | None = None) -> ImageFont.ImageFont:
        path = self._resolve(name)
        return _load_font(path, size)


class IconCache:
    """Lazy cache for bitmap icons."""

    def __init__(self, search_paths: Iterable[Path] | None = None) -> None:
        self._search_paths = [Path(p) for p in (search_paths or [])]
        self._cache: dict[tuple[str, Optional[int]], Image.Image] = {}

    def _resolve(self, name: str) -> Path:
        possible = [name]
        if "." not in name:
            possible.extend([f"{name}.png", f"{name}.jpg", f"{name}.jpeg"])
        for candidate in possible:
            for base in self._search_paths:
                path = base / candidate
                if path.exists():
                    return path
        raise FileNotFoundError(f"Icon not found: {name}")

    def get(self, name: str, size: Optional[int] = None) -> Image.Image:
        key = (name, size)
        if key in self._cache:
            return self._cache[key].copy()

        path = self._resolve(name)
        with Image.open(path) as handle:
            icon = handle.convert("RGBA")
        if size:
            icon = icon.resize((size, size), Image.Resampling.LANCZOS)
        self._cache[key] = icon
        return icon.copy()


@dataclass
class Surface:
    image: Image.Image
    draw: ImageDraw.ImageDraw
    fonts: FontManager
    icons: IconCache

    @classmethod
    def create(
        cls,
        size: Tuple[int, int],
        background: Tuple[int, int, int],
        *,
        fonts: FontManager,
        icons: IconCache,
    ) -> "Surface":
        img = Image.new("RGB", size, color=background)
        draw = ImageDraw.Draw(img)
        return cls(image=img, draw=draw, fonts=fonts, icons=icons)

    def text(
        self,
        position: Tuple[int, int],
        text: str,
        *,
        font: Optional[ImageFont.ImageFont] = None,
        fill: Tuple[int, int, int] | str = "black",
        anchor: Optional[str] = None,
    ) -> None:
        font = font or self.fonts.get(size=16)
        self.draw.text(position, text, fill=fill, font=font, anchor=anchor)

    def multiline_text(
        self,
        position: Tuple[int, int],
        lines: Iterable[str],
        *,
        font: Optional[ImageFont.ImageFont] = None,
        fill: Tuple[int, int, int] | str = "black",
        line_spacing: int = 4,
    ) -> int:
        font = font or self.fonts.get(size=16)
        x, y = position
        height = 0
        for line in lines:
            self.draw.text((x, y + height), line, fill=fill, font=font)
            _, line_h = self.text_size(line, font=font)
            height += line_h + line_spacing
        return height

    def rectangle(
        self,
        box: Tuple[int, int, int, int],
        *,
        fill: Tuple[int, int, int] | str,
        outline: Tuple[int, int, int] | str | None = None,
        width: int = 1,
    ) -> None:
        self.draw.rectangle(box, fill=fill, outline=outline, width=width)

    def line(
        self,
        points: Sequence[Tuple[int, int]],
        *,
        fill: Tuple[int, int, int] | str,
        width: int = 1,
    ) -> None:
        self.draw.line(points, fill=fill, width=width)

    def paste(self, img: Image.Image, box: Tuple[int, int], *, mask: Optional[Image.Image] = None) -> None:
        self.image.paste(img, box, mask=mask)

    def text_size(self, text: str, *, font: Optional[ImageFont.ImageFont] = None) -> Tuple[int, int]:
        font = font or self.fonts.get(size=16)
        return self.draw.textsize(text, font=font)


__all__ = ["FontManager", "IconCache", "Surface", "DEFAULT_FONT_NAMES"]
