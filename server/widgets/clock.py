from __future__ import annotations

import datetime as _dt
import locale
from contextlib import contextmanager
from typing import Any, Mapping

from .base import WidgetBase, WidgetField
from .surface import Surface

__all__ = ["ClockWidget"]


@contextmanager
def _temporary_locale(name: str | None) -> Any:
    try:
        current = locale.setlocale(locale.LC_TIME)
    except locale.Error:
        current = None
    applied = False
    try:
        if name:
            try:
                locale.setlocale(locale.LC_TIME, name)
                applied = True
            except locale.Error:
                applied = False
        yield applied
    finally:
        if current:
            try:
                locale.setlocale(locale.LC_TIME, current)
            except locale.Error:
                pass


class ClockWidget(WidgetBase):
    def __init__(self) -> None:
        super().__init__(
            slug="clock",
            name="Digitale klok",
            description=(
                "Toont de huidige tijd en datum. Kies voor 24-uurs- of 12-uursweergave en stel"
                " de locale in voor datumformattering."
            ),
            fields=[
                WidgetField(
                    name="use_24h",
                    label="24-uurs notatie",
                    field_type="boolean",
                    default=True,
                    description="Schakel uit voor 12-uurs notatie met AM/PM-indicatie.",
                ),
                WidgetField(
                    name="locale",
                    label="Locale",
                    field_type="string",
                    default="nl_NL",
                    description="Locale code voor datum en weeknummer (bijv. nl_NL of en_GB).",
                ),
            ],
            default_config={"use_24h": True, "locale": "nl_NL"},
        )

    def fetch(self, config: Mapping[str, Any]) -> _dt.datetime:
        return _dt.datetime.now()

    def draw(self, surface: Surface, data: _dt.datetime, config: Mapping[str, Any]) -> None:
        now = data
        use_24h = bool(config.get("use_24h", True))
        locale_name = str(config.get("locale") or "")

        time_format = "%H:%M" if use_24h else "%I:%M"
        time_text = now.strftime(time_format)

        with _temporary_locale(locale_name):
            date_text = now.strftime("%A %d %B %Y")
            week_number = now.strftime("%V")
            meridiem = None if use_24h else now.strftime("%p")

        if date_text:
            date_text = date_text[0].upper() + date_text[1:]

        secondary_parts = [date_text, f"week {week_number}"]
        if meridiem:
            secondary_parts.append(meridiem)
        secondary_text = " · ".join(part for part in secondary_parts if part)

        left, top, right, bottom = surface.content_box
        content_width = right - left
        content_height = bottom - top

        time_font = surface.fit_text(
            time_text,
            surface.fonts.monospace,
            content_width,
            max(content_height * 0.7, 48),
            minimum_size=36,
        )
        _, time_height = surface.text_size(time_text, time_font)

        secondary_font = None
        secondary_height = 0
        if secondary_text:
            secondary_font = surface.fit_text(
                secondary_text,
                surface.fonts.sans,
                content_width,
                max(content_height - time_height - surface.theme.grid, content_height * 0.2, 24),
                minimum_size=14,
            )
            _, secondary_height = surface.text_size(secondary_text, secondary_font)

        spacing = surface.theme.grid if secondary_text else 0
        total_height = time_height + spacing + secondary_height
        top_offset = (content_height - total_height) / 2

        centre_x = (left + right) / 2
        time_centre_y = top + top_offset + time_height / 2
        surface.draw_text(
            (centre_x, time_centre_y),
            time_text,
            font=time_font,
            fill=surface.theme.primary,
            anchor="mm",
        )

        if secondary_text and secondary_font:
            secondary_centre_y = time_centre_y + time_height / 2 + spacing + secondary_height / 2
            surface.draw_text(
                (centre_x, secondary_centre_y),
                secondary_text,
                font=secondary_font,
                fill=surface.theme.secondary,
                anchor="mm",
            )
