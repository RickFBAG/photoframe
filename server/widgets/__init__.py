from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

from PIL import Image, ImageDraw, ImageFont


@dataclass
class WidgetField:
    name: str
    label: str
    field_type: str = "string"
    required: bool = False
    default: Optional[Any] = None
    description: Optional[str] = None


class WidgetError(RuntimeError):
    pass


@dataclass
class WidgetDefinition:
    slug: str
    name: str
    description: str
    fields: List[WidgetField] = field(default_factory=list)

    def render(self, config: Mapping[str, Any], size: tuple[int, int]) -> Image.Image:
        raise NotImplementedError


class WidgetBase(WidgetDefinition):
    """Base class for widgets with shared helpers."""


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
                    description="Tekst die weergegeven moet worden.",
                ),
            ],
        )

    def render(self, config: Mapping[str, Any], size: tuple[int, int]) -> Image.Image:
        text = str(config.get("text") or "Photoframe")
        image = Image.new("RGB", size, color="white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        text_width, text_height = draw.textsize(text, font=font)
        position = ((size[0] - text_width) // 2, (size[1] - text_height) // 2)
        draw.text(position, text, fill="black", font=font)
        return image


class ClockWidget(WidgetBase):
    def __init__(self) -> None:
        super().__init__(
            slug="clock",
            name="Digitale klok",
            description="Toont de huidige tijd en datum.",
            fields=[
                WidgetField(
                    name="format",
                    label="Formaat",
                    field_type="string",
                    default="%H:%M",
                    description="Datum/tijd notatie conform strftime.",
                ),
            ],
        )

    def render(self, config: Mapping[str, Any], size: tuple[int, int]) -> Image.Image:
        fmt = str(config.get("format") or "%H:%M")
        now = _dt.datetime.now()
        text = now.strftime(fmt)
        date_text = now.strftime("%d %B %Y")

        image = Image.new("RGB", size, color="white")
        draw = ImageDraw.Draw(image)
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
        text_width, text_height = draw.textsize(text, font=font_large)
        date_width, date_height = draw.textsize(date_text, font=font_small)

        draw.text(((size[0] - text_width) // 2, size[1] // 2 - text_height), text, fill="black", font=font_large)
        draw.text(((size[0] - date_width) // 2, size[1] // 2 + 10), date_text, fill="black", font=font_small)
        return image


class WidgetRegistry:
    def __init__(self) -> None:
        self._items: Dict[str, WidgetDefinition] = {}

    def register(self, widget: WidgetDefinition) -> None:
        self._items[widget.slug] = widget

    def get(self, slug: str) -> WidgetDefinition:
        try:
            return self._items[slug]
        except KeyError as exc:  # pragma: no cover - defensive
            raise WidgetError(f"Onbekende widget: {slug}") from exc

    def list(self) -> Iterable[WidgetDefinition]:
        return self._items.values()

    def __contains__(self, slug: str) -> bool:
        return slug in self._items


def create_default_registry() -> WidgetRegistry:
    registry = WidgetRegistry()
    registry.register(MessageWidget())
    registry.register(ClockWidget())
    try:
        from .weather import WeatherWidget

        registry.register(WeatherWidget())
    except Exception:  # pragma: no cover - weather widget optional in minimal installs
        pass
    return registry


__all__ = [
    "WidgetField",
    "WidgetError",
    "WidgetDefinition",
    "WidgetBase",
    "MessageWidget",
    "ClockWidget",
    "WidgetRegistry",
    "create_default_registry",
]
