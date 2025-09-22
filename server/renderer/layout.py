from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Tuple

from PIL import Image, ImageOps

from .surface import Surface
from .theme import Theme


@dataclass
class LayoutContent:
    title: str = ""
    subtitle: str = ""
    details: List[str] = field(default_factory=list)
    footer: str = ""


LayoutFunc = Callable[[Surface, Image.Image, Theme, LayoutContent, bool], Image.Image]


GUTTER_RATIO = 0.05
TEXT_LINE_SPACING = 6


def _scaled_font(surface: Surface, factor: float) -> int:
    width, height = surface.image.size
    base = min(width, height)
    return max(16, int(base * factor))


def _render_single(surface: Surface, content: Image.Image, theme: Theme, meta: LayoutContent, separators: bool) -> Image.Image:
    target_size = surface.image.size
    scaled = ImageOps.contain(content, target_size, Image.Resampling.LANCZOS)
    offset = ((target_size[0] - scaled.width) // 2, (target_size[1] - scaled.height) // 2)
    surface.paste(scaled, offset)

    if meta.title or meta.subtitle or meta.footer:
        width, height = target_size
        panel_height = max(int(height * 0.22), 96)
        panel_top = height - panel_height
        surface.rectangle((0, panel_top, width, height), fill=theme.background)
        padding = int(width * GUTTER_RATIO)
        if separators:
            surface.line(((padding, panel_top), (width - padding, panel_top)), fill=theme.separator, width=2)
        cursor_y = panel_top + int(panel_height * 0.18)
        title_font = surface.fonts.get(size=_scaled_font(surface, 0.09))
        subtitle_font = surface.fonts.get(size=_scaled_font(surface, 0.05))
        footer_font = surface.fonts.get(size=_scaled_font(surface, 0.045))
        if meta.title:
            surface.text((padding, cursor_y), meta.title, font=title_font, fill=theme.foreground)
            _, title_h = surface.text_size(meta.title, font=title_font)
            cursor_y += title_h + TEXT_LINE_SPACING
        if meta.subtitle:
            surface.text((padding, cursor_y), meta.subtitle, font=subtitle_font, fill=theme.muted)
            _, sub_h = surface.text_size(meta.subtitle, font=subtitle_font)
            cursor_y += sub_h + TEXT_LINE_SPACING
        if meta.footer:
            footer_y = height - padding - surface.text_size(meta.footer, font=footer_font)[1]
            surface.text((padding, footer_y), meta.footer, font=footer_font, fill=theme.accent)

    return surface.image


def _render_two_column(surface: Surface, content: Image.Image, theme: Theme, meta: LayoutContent, separators: bool) -> Image.Image:
    width, height = surface.image.size
    gutter = int(width * GUTTER_RATIO)
    left_width = int(width * 0.58)
    image_height = height - 2 * gutter
    scaled = ImageOps.fit(content, (left_width, image_height), Image.Resampling.LANCZOS)
    surface.paste(scaled, (gutter, gutter))

    column_x = gutter + left_width + gutter
    if separators:
        surface.line(((column_x - gutter // 2, gutter), (column_x - gutter // 2, height - gutter)), fill=theme.separator, width=3)

    title_font = surface.fonts.get(size=_scaled_font(surface, 0.09))
    body_font = surface.fonts.get(size=_scaled_font(surface, 0.05))
    footer_font = surface.fonts.get(size=_scaled_font(surface, 0.045))

    cursor_y = gutter
    if meta.title:
        surface.text((column_x, cursor_y), meta.title, font=title_font, fill=theme.foreground)
        _, title_h = surface.text_size(meta.title, font=title_font)
        cursor_y += title_h + TEXT_LINE_SPACING
    if meta.subtitle:
        surface.text((column_x, cursor_y), meta.subtitle, font=body_font, fill=theme.accent)
        _, sub_h = surface.text_size(meta.subtitle, font=body_font)
        cursor_y += sub_h + TEXT_LINE_SPACING
    if meta.details:
        cursor_y += surface.multiline_text((column_x, cursor_y), meta.details, font=body_font, fill=theme.muted, line_spacing=TEXT_LINE_SPACING)
    if meta.footer:
        footer_y = height - gutter - surface.text_size(meta.footer, font=footer_font)[1]
        surface.text((column_x, footer_y), meta.footer, font=footer_font, fill=theme.separator)

    return surface.image


def _render_hero(surface: Surface, content: Image.Image, theme: Theme, meta: LayoutContent, separators: bool) -> Image.Image:
    width, height = surface.image.size
    hero_height = int(height * 0.65)
    scaled = ImageOps.fit(content, (width, hero_height), Image.Resampling.LANCZOS)
    surface.paste(scaled, (0, 0))

    overlay_height = height - hero_height
    base_y = hero_height
    surface.rectangle((0, base_y, width, height), fill=theme.background)
    padding = int(width * GUTTER_RATIO)
    if separators:
        surface.line(((padding, base_y), (width - padding, base_y)), fill=theme.separator, width=2)

    title_font = surface.fonts.get(size=_scaled_font(surface, 0.1))
    subtitle_font = surface.fonts.get(size=_scaled_font(surface, 0.055))
    body_font = surface.fonts.get(size=_scaled_font(surface, 0.048))

    cursor_y = base_y + int(overlay_height * 0.2)
    if meta.title:
        surface.text((padding, cursor_y), meta.title, font=title_font, fill=theme.foreground)
        _, title_h = surface.text_size(meta.title, font=title_font)
        cursor_y += title_h + TEXT_LINE_SPACING
    if meta.subtitle:
        surface.text((padding, cursor_y), meta.subtitle, font=subtitle_font, fill=theme.accent)
        _, sub_h = surface.text_size(meta.subtitle, font=subtitle_font)
        cursor_y += sub_h + TEXT_LINE_SPACING
    if meta.details:
        surface.multiline_text((padding, cursor_y), meta.details, font=body_font, fill=theme.muted, line_spacing=TEXT_LINE_SPACING)

    return surface.image


_LAYOUTS: Dict[str, LayoutFunc] = {
    "single": _render_single,
    "2col": _render_two_column,
    "two_column": _render_two_column,
    "hero": _render_hero,
}


def get_layout(name: str) -> LayoutFunc:
    return _LAYOUTS.get(name.lower(), _LAYOUTS["single"])


def list_layouts() -> Iterable[str]:
    return _LAYOUTS.keys()


__all__ = ["LayoutContent", "LayoutFunc", "get_layout", "list_layouts"]
