from __future__ import annotations
from typing import Mapping

from .base import WidgetBase, WidgetField
from .surface import Surface

__all__ = ["MessageWidget"]


class MessageWidget(WidgetBase):
    def __init__(self) -> None:
        super().__init__(
            slug="message",
            name="Vrije tekst",
            description="Toont een korte tekst in het midden van het scherm.",
            fields=[
                WidgetField(
                    name="text",
                    label="Tekst",
                    field_type="string",
                    required=True,
                    default="Photoframe",
                    description="Tekst die weergegeven moet worden.",
                ),
            ],
            default_config={"text": "Photoframe"},
        )

    def fetch(self, config: Mapping[str, str]) -> str:
        text = str(config.get("text") or "Photoframe")
        return text.strip() or "Photoframe"

    def draw(self, surface: Surface, data: str, config: Mapping[str, str]) -> None:
        left, top, right, bottom = surface.content_box
        max_width = right - left
        max_height = bottom - top
        font = surface.fit_text(data, surface.fonts.sans, max_width, max_height, minimum_size=12)
        centre = ((left + right) / 2, (top + bottom) / 2)
        surface.draw_text(centre, data, font=font, fill=surface.theme.primary, anchor="mm")