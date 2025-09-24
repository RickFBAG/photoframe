"""Agenda widget rendering today's and upcoming events."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from PIL import Image, ImageDraw

from ..config import AgendaSettings
from ..data.agenda import AgendaDataProvider, AgendaEvent
from ..display.style import load_font
from .base import Widget, WidgetContext


class AgendaWidget(Widget[List[AgendaEvent]]):
    def __init__(self, settings: AgendaSettings) -> None:
        super().__init__("agenda", enabled=settings.enabled)
        self.settings = settings
        self.provider = AgendaDataProvider(settings)

    def fetch(self) -> Optional[List[AgendaEvent]]:
        events = self.provider.fetch()
        return events

    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, context: WidgetContext, data: List[AgendaEvent]) -> None:
        palette = context.palette
        area = context.area.inset(24, 24)
        draw.rectangle([area.left, area.top, area.right, area.bottom], fill=(255, 255, 255), outline=palette.muted, width=3)

        header_font = load_font(36, bold=True)
        sub_font = load_font(20)
        body_font = load_font(24)

        draw.text((area.left + 12, area.top + 8), "Agenda", fill=palette.primary, font=header_font)
        y = area.top + 8 + _text_height(header_font)

        if not data:
            draw.text(
                (area.left + 12, y + 16),
                "No upcoming events",
                fill=palette.muted,
                font=body_font,
            )
            return

        day = None
        for event in data:
            event_day = event.start.date()
            if day != event_day:
                day = event_day
                day_label = event.start.strftime("%A %d %b")
                draw.text((area.left + 12, y + 20), day_label, fill=palette.secondary, font=sub_font)
                y += 20 + _text_height(sub_font)

            time_range = _format_time_range(event, context.now)
            draw.text((area.left + 12, y + 12), time_range, fill=palette.accent, font=body_font)
            draw.text(
                (area.left + 160, y + 12),
                event.title,
                fill=palette.primary,
                font=body_font,
            )
            y += 12 + _text_height(body_font)
            if event.location:
                draw.text(
                    (area.left + 160, y + 4),
                    event.location,
                    fill=palette.secondary,
                    font=sub_font,
                )
                y += 4 + _text_height(sub_font)
            y += 8


def _text_height(font) -> int:
    bbox = font.getbbox("Hg")
    return bbox[3] - bbox[1]


def _format_time_range(event: AgendaEvent, now: datetime) -> str:
    start_fmt = event.start.strftime("%H:%M")
    if event.start.date() != event.end.date():
        end_fmt = event.end.strftime("%d %b %H:%M")
    else:
        end_fmt = event.end.strftime("%H:%M")
    if event.end <= event.start:
        return start_fmt
    if event.start.date() == now.date():
        return f"{start_fmt} - {end_fmt}"
    day = event.start.strftime("%d %b")
    return f"{day} {start_fmt}"


__all__ = ["AgendaWidget"]
