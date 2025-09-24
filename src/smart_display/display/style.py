"""Shared palette and font helpers."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Tuple

from PIL import ImageFont


@dataclass(frozen=True)
class Palette:
    background: Tuple[int, int, int]
    primary: Tuple[int, int, int]
    secondary: Tuple[int, int, int]
    accent: Tuple[int, int, int]
    positive: Tuple[int, int, int]
    muted: Tuple[int, int, int]
    warning: Tuple[int, int, int]


DEFAULT_PALETTE = Palette(
    background=(240, 240, 236),  # warm white
    primary=(38, 38, 38),  # deep charcoal
    secondary=(88, 88, 88),
    accent=(220, 76, 70),  # inky red
    positive=(32, 142, 72),  # deep green
    muted=(120, 120, 120),
    warning=(255, 185, 0),  # amber highlight
)


def _font_candidates(bold: bool) -> Tuple[str, ...]:
    if bold:
        return (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        )
    return (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    )


@lru_cache(maxsize=16)
def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a truetype font with graceful fallback."""

    for path in _font_candidates(bold):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


__all__ = ["DEFAULT_PALETTE", "load_font", "Palette"]
