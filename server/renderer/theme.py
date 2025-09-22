from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    """Represents a named colour theme with semantic roles."""

    name: str
    background: Color
    foreground: Color
    accent: Color
    muted: Color
    separator: Color


_THEMES: Dict[str, Theme] = {
    "light": Theme(
        name="light",
        background=(245, 245, 245),
        foreground=(34, 34, 34),
        accent=(220, 60, 60),
        muted=(120, 120, 120),
        separator=(200, 200, 200),
    ),
    "dark": Theme(
        name="dark",
        background=(20, 20, 20),
        foreground=(235, 235, 235),
        accent=(255, 120, 80),
        muted=(140, 140, 140),
        separator=(70, 70, 70),
    ),
    "warm": Theme(
        name="warm",
        background=(250, 244, 232),
        foreground=(60, 40, 20),
        accent=(208, 94, 54),
        muted=(160, 132, 96),
        separator=(214, 198, 176),
    ),
    "cool": Theme(
        name="cool",
        background=(235, 242, 248),
        foreground=(24, 48, 72),
        accent=(64, 132, 214),
        muted=(104, 140, 168),
        separator=(180, 204, 220),
    ),
}


def get_theme(name: str) -> Theme:
    return _THEMES.get(name.lower(), _THEMES["light"])


def list_themes() -> Iterable[str]:
    return _THEMES.keys()


__all__ = ["Theme", "get_theme", "list_themes"]
