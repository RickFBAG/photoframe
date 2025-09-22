from __future__ import annotations

import datetime as _dt
from typing import Any, Mapping, TYPE_CHECKING

from PIL import Image, ImageFont

from .base import Surface, WidgetBase, WidgetField

if TYPE_CHECKING:  # pragma: no cover
    from ..app import AppState


class ClockWidget(WidgetBase):
    slug = "clock"
    name = "Digitale klok"
    description = "Toont de huidige tijd en datum."
    fields = (
        WidgetField(
            name="format",
            label="Formaat",
            field_type="string",
            default="%H:%M",
            description="Datum/tijd notatie conform strftime.",
        ),
    )
    default_config = {"format": "%H:%M"}
    cache_ttl = 30.0
    cache_stale_ttl = 120.0

    async def _fetch(self, config: Mapping[str, Any], state: "AppState" | None = None) -> Mapping[str, Any]:
        fmt = str(config.get("format") or self.default_config["format"])
        now = _dt.datetime.now()
        return {
            "time": now.strftime(fmt),
            "date": now.strftime("%d %B %Y"),
            "format": fmt,
        }

    def render(self, surface: Surface, data: Mapping[str, Any]) -> Image.Image:
        time_text = data.get("time", "")
        date_text = data.get("date", "")

        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

        time_bbox = surface.draw.textbbox((0, 0), time_text, font=font_large)
        date_bbox = surface.draw.textbbox((0, 0), date_text, font=font_small)

        if time_bbox is None:  # pragma: no cover - Pillow < 9 fallback
            time_width = time_height = 0
        else:
            time_width = time_bbox[2] - time_bbox[0]
            time_height = time_bbox[3] - time_bbox[1]

        if date_bbox is None:  # pragma: no cover - Pillow < 9 fallback
            date_width = date_height = 0
        else:
            date_width = date_bbox[2] - date_bbox[0]
            date_height = date_bbox[3] - date_bbox[1]

        time_pos = ((surface.width - time_width) // 2, surface.height // 2 - time_height)
        date_pos = ((surface.width - date_width) // 2, surface.height // 2 + 10)

        surface.draw.text(time_pos, time_text, fill="black", font=font_large)
        surface.draw.text(date_pos, date_text, fill="black", font=font_small)
        return surface.image


__all__ = ["ClockWidget"]
