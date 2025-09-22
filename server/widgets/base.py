from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

from PIL import Image

from .surface import Surface, Theme

__all__ = [
    "WidgetError",
    "WidgetField",
    "WidgetBase",
    "WidgetRegistry",
]


@dataclass
class WidgetField:
    name: str
    label: str
    field_type: str = "string"
    required: bool = False
    default: Any | None = None
    description: str | None = None


class WidgetError(RuntimeError):
    pass


class WidgetBase:
    """Base class for widgets exposing configuration metadata and rendering."""

    slug: str
    name: str
    description: str
    fields: Sequence[WidgetField]
    default_config: Mapping[str, Any]

    def __init__(
        self,
        *,
        slug: str,
        name: str,
        description: str,
        fields: Sequence[WidgetField] | None = None,
        default_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.slug = slug
        self.name = name
        self.description = description
        self.fields = tuple(fields or ())
        self.default_config = dict(default_config or {})

    # -- configuration -------------------------------------------------
    def resolve_config(self, config: Mapping[str, Any] | None) -> Dict[str, Any]:
        resolved: Dict[str, Any] = dict(self.default_config)
        if config:
            for key, value in config.items():
                if value is not None:
                    resolved[key] = value
        return resolved

    # -- theming -------------------------------------------------------
    def get_theme(self, config: Mapping[str, Any]) -> Theme:
        return Theme.default()

    # -- data lifecycle ------------------------------------------------
    def fetch(self, config: Mapping[str, Any]) -> Any:
        return None

    def draw(self, surface: Surface, data: Any, config: Mapping[str, Any]) -> None:
        raise NotImplementedError

    def render(self, config: Mapping[str, Any] | None, size: tuple[int, int]) -> Image.Image:
        resolved = self.resolve_config(config)
        data = self.fetch(resolved)
        theme = self.get_theme(resolved)
        surface = Surface(size=size, theme=theme)
        self.draw(surface, data, resolved)
        return surface.image


class WidgetRegistry:
    def __init__(self) -> None:
        self._items: MutableMapping[str, WidgetBase] = {}

    def register(self, widget: WidgetBase) -> None:
        self._items[widget.slug] = widget

    def get(self, slug: str) -> WidgetBase:
        try:
            return self._items[slug]
        except KeyError as exc:  # pragma: no cover - defensive
            raise WidgetError(f"Onbekende widget: {slug}") from exc

    def list(self) -> Iterable[WidgetBase]:
        return self._items.values()

    def __contains__(self, slug: str) -> bool:
        return slug in self._items
