from __future__ import annotations

from typing import Any, Mapping, TYPE_CHECKING

from PIL import Image, ImageFont

from .base import Surface, WidgetBase, WidgetField

if TYPE_CHECKING:  # pragma: no cover
    from ..app import AppState


class MessageWidget(WidgetBase):
    slug = "message"
    name = "Vrije tekst"
    description = "Toont een korte tekst in het midden van het scherm."
    fields = (
        WidgetField(
            name="text",
            label="Tekst",
            field_type="string",
            required=True,
            description="Tekst die weergegeven moet worden.",
        ),
    )
    default_config = {"text": "Photoframe"}
    cache_ttl = 300.0
    cache_stale_ttl = 900.0

    async def _fetch(self, config: Mapping[str, Any], state: "AppState" | None = None) -> Mapping[str, Any]:
        text = str(config.get("text") or self.default_config["text"])
        return {"text": text}

    def render(self, surface: Surface, data: Mapping[str, Any]) -> Image.Image:
        text = data.get("text", "")
        font = ImageFont.load_default()
        bbox = surface.draw.textbbox((0, 0), text, font=font)
        if bbox is None:  # pragma: no cover - Pillow < 9 compatibility
            text_width = text_height = 0
        else:
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        position = ((surface.width - text_width) // 2, (surface.height - text_height) // 2)
        surface.draw.text(position, text, fill="black", font=font)
        return surface.image


__all__ = ["MessageWidget"]
