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
    background=(12, 17, 26),  # deep navy
    primary=(231, 238, 247),  # soft white
    secondary=(148, 163, 184),  # slate
    accent=(94, 234, 212),  # aqua accent
    positive=(129, 230, 217),
    muted=(71, 85, 105),
    warning=(250, 204, 21),
)


def lighten(color: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    """Return a colour blended towards white by ``amount``."""

    amount = max(0.0, min(1.0, amount))
    return tuple(int(channel + (255 - channel) * amount) for channel in color)


def darken(color: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    """Return a colour blended towards black by ``amount``."""

    amount = max(0.0, min(1.0, amount))
    return tuple(int(channel * (1 - amount)) for channel in color)


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


__all__ = ["DEFAULT_PALETTE", "load_font", "Palette", "lighten", "darken"]
