"""News widget showing concise headlines."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from PIL import Image, ImageDraw

from ..config import NewsSettings
from ..data.news import NewsDataProvider, NewsHeadline
from ..display.style import load_font
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
        area = context.area.inset(16, 16)
        draw.rectangle([area.left, area.top, area.right, area.bottom], fill=(245, 245, 243), outline=palette.muted, width=2)

        header_font = load_font(28, bold=True)
        body_font = load_font(20)
        meta_font = load_font(16)

        draw.text((area.left + 8, area.top + 6), "Top Headlines", fill=palette.primary, font=header_font)
        y = area.top + 6 + _text_height(header_font)

        if not data:
            draw.text(
                (area.left + 8, y + 12),
                "News feed unavailable",
                fill=palette.muted,
                font=body_font,
            )
            return

        for headline in data:
            y += 12
            draw.ellipse(
                [area.left + 8, y + 6, area.left + 18, y + 16],
                fill=palette.accent,
            )
            draw.text(
                (area.left + 28, y),
                headline.title,
                fill=palette.primary,
                font=body_font,
            )
            y += _text_height(body_font)
            meta = _format_metadata(headline, context.now)
            if meta:
                draw.text(
                    (area.left + 28, y),
                    meta,
                    fill=palette.secondary,
                    font=meta_font,
                )
                y += _text_height(meta_font)
            if y + _text_height(body_font) > area.bottom - 12:
                break


def _text_height(font) -> int:
    bbox = font.getbbox("Hg")
    return bbox[3] - bbox[1]


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
