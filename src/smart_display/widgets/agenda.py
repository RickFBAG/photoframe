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
        card_area = context.area.inset(12, 12)
        draw.rounded_rectangle(
            [card_area.left, card_area.top, card_area.right, card_area.bottom],
            radius=28,
            fill=(255, 255, 255),
            outline=tuple(min(255, c + 20) for c in palette.muted),
            width=2,
        )

        area = card_area.inset(32, 32)
        header_font = load_font(40, bold=True)
        sub_font = load_font(22, bold=True)
        body_font = load_font(26)
        detail_font = load_font(21)

        header_y = area.top
        draw.text((area.left, header_y), "Today's Agenda", fill=palette.primary, font=header_font)
        y = header_y + _text_height(header_font) + 16
        draw.line([(area.left, y), (area.right, y)], fill=tuple(min(255, c + 40) for c in palette.muted), width=2)
        y += 20

        if not data:
            draw.text(
                (area.left, y),
                "No upcoming events",
                fill=palette.muted,
                font=body_font,
            )
            return

        current_day = None
        for event in data:
            event_day = event.start.date()
            if current_day != event_day:
                current_day = event_day
                day_label = event.start.strftime("%A, %d %B")
                draw.text((area.left, y), day_label, fill=palette.secondary, font=sub_font)
                y += _text_height(sub_font) + 12

            time_range = _format_time_range(event, context.now)
            badge_height = _text_height(body_font) + 18
            badge_width = _text_width(body_font, time_range) + 32
            badge_bottom = y + badge_height

            draw.rounded_rectangle(
                [area.left, y, area.left + badge_width, badge_bottom],
                radius=badge_height // 2,
                fill=palette.accent,
            )
            draw.text(
                (area.left + 16, y + (badge_height - _text_height(body_font)) // 2),
                time_range,
                fill=(255, 255, 255),
                font=body_font,
            )

            text_x = area.left + badge_width + 24
            draw.text(
                (text_x, y + 4),
                event.title,
                fill=palette.primary,
                font=body_font,
            )
            text_bottom = y + 4 + _text_height(body_font)
            if event.location:
                location_y = text_bottom + 6
                draw.text(
                    (text_x, location_y),
                    event.location,
                    fill=palette.secondary,
                    font=detail_font,
                )
                text_bottom = location_y + _text_height(detail_font)

            y = max(badge_bottom, text_bottom) + 20
            if y > area.bottom - _text_height(body_font):
                break


def _text_height(font) -> int:
    bbox = font.getbbox("Hg")
    return bbox[3] - bbox[1]


def _text_width(font, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


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
