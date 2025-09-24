"""News widget showing concise headlines."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from PIL import Image, ImageDraw

from ..config import NewsSettings
from ..data.news import NewsDataProvider, NewsHeadline
from ..display.style import darken, lighten, load_font
from .base import Widget, WidgetContext


class NewsWidget(Widget[List[NewsHeadline]]):
    def __init__(self, settings: NewsSettings) -> None:
        super().__init__("news", enabled=settings.enabled)
        self.provider = NewsDataProvider(settings)
        self.settings = settings

    def fetch(self) -> Optional[List[NewsHeadline]]:
        return self.provider.fetch()

    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, context: WidgetContext, data: List[NewsHeadline]) -> None:
        palette = context.palette
        card_area = context.area.inset(10, 10)
        card_fill = lighten(palette.background, 0.1)
        border_colour = lighten(palette.muted, 0.25)
        draw.rounded_rectangle(
            [card_area.left, card_area.top, card_area.right, card_area.bottom],
            radius=26,
            fill=card_fill,
            outline=border_colour,
            width=2,
        )

        accent_strip = [card_area.left, card_area.top, card_area.right, card_area.top + 8]
        draw.rectangle(accent_strip, fill=darken(palette.accent, 0.25))

        area = card_area.inset(26, 30)
        header_font = load_font(30, bold=True)
        body_font = load_font(22)
        meta_font = load_font(18)
        kicker_font = load_font(18, bold=True)

        y = area.top
        draw.text((area.left, y), "TOP STORIES", fill=palette.primary, font=header_font)
        y += _text_height(header_font) + 10
        draw.line([(area.left, y), (area.right, y)], fill=lighten(palette.muted, 0.1), width=2)
        y += 14

        if not data:
            draw.text((area.left, y), "FEED UNAVAILABLE", fill=palette.secondary, font=kicker_font)
            return

        for idx, headline in enumerate(data):
            item_top = y
            item_bottom = item_top

            kicker = headline.source.upper() if headline.source else None
            if kicker:
                kicker_bg = darken(palette.accent, 0.2)
                kicker_height = _text_height(kicker_font) + 10
                kicker_width = _text_width(kicker_font, kicker) + 18
                draw.rounded_rectangle(
                    [area.left, item_bottom, area.left + kicker_width, item_bottom + kicker_height],
                    radius=8,
                    fill=kicker_bg,
                )
                draw.text(
                    (area.left + 9, item_bottom + (kicker_height - _text_height(kicker_font)) // 2),
                    kicker,
                    fill=palette.primary,
                    font=kicker_font,
                )
                item_bottom += kicker_height + 6

            draw.text(
                (area.left, item_bottom),
                headline.title,
                fill=palette.primary,
                font=body_font,
            )
            item_bottom += _text_height(body_font)

            meta = _format_metadata(headline, context.now)
            if meta:
                badge_width = _text_width(meta_font, meta) + 20
                badge_height = _text_height(meta_font) + 12
                draw.rounded_rectangle(
                    [area.left, item_bottom + 6, area.left + badge_width, item_bottom + 6 + badge_height],
                    radius=badge_height // 2,
                    fill=darken(palette.secondary, 0.35),
                )
                draw.text(
                    (area.left + 10, item_bottom + 6 + (badge_height - _text_height(meta_font)) // 2),
                    meta,
                    fill=(255, 255, 255),
                    font=meta_font,
                )
                item_bottom += badge_height + 12

            y = item_bottom + 18
            if idx < len(data) - 1 and y < area.bottom - _text_height(body_font):
                draw.line([(area.left, y - 8), (area.right, y - 8)], fill=tuple(min(255, c + 45) for c in palette.muted), width=1)
            if y > area.bottom - _text_height(body_font):
                break


def _text_height(font) -> int:
    bbox = font.getbbox("Hg")
    return bbox[3] - bbox[1]


def _text_width(font, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _format_metadata(headline: NewsHeadline, now: datetime) -> str:
    bits: List[str] = []
    if headline.source:
        bits.append(headline.source)
    if headline.published:
        delta = now - headline.published
        hours = int(delta.total_seconds() // 3600)
        if hours <= 0:
            bits.append("Just now")
        elif hours == 1:
            bits.append("1 hour ago")
        else:
            bits.append(f"{hours}h ago")
    return " • ".join(bits)


__all__ = ["NewsWidget"]
