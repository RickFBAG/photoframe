from __future__ import annotations


from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

from PIL import Image

from .surface import Surface, Theme
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, TYPE_CHECKING

from PIL import Image, ImageDraw

from ..cache import CacheStore

if TYPE_CHECKING:  # pragma: no cover
    from ..app import AppState

__all__ = [
    "WidgetError",
    "WidgetField",
    "WidgetBase",
    "WidgetRegistry",
]


@dataclass
=======
    "Surface",
    "WidgetBase",
]


class WidgetError(RuntimeError):
    """Raised when widgets fail to load or render."""


@dataclass(slots=True)
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
    default: Optional[Any] = None
    description: Optional[str] = None


class Surface:
    """Simple drawing surface backed by a Pillow image."""

    def __init__(self, size: tuple[int, int], mode: str = "RGB", background: Any = "white") -> None:
        self.size = size
        self.mode = mode
        self.background = background
        self.image = Image.new(mode, size, color=background)
        self.draw = ImageDraw.Draw(self.image)

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    def clear(self, color: Any | None = None) -> None:
        color = self.background if color is None else color
        self.image.paste(color, [0, 0, self.width, self.height])


class WidgetBase:
    """Base class for widgets that can render onto a :class:`Surface`."""

    slug: str = ""
    name: str = ""
    description: str = ""
    fields: Sequence[WidgetField] = ()
    default_config: Mapping[str, Any] = {}
    cache_ttl: float = 30.0
    cache_stale_ttl: Optional[float] = None

    def __init__(self) -> None:
        if not self.slug:
            raise WidgetError(f"Widget {self.__class__.__name__} must define a slug")
        self.fields = list(self.fields)
        self.default_config = dict(self.default_config)
        self._cache: CacheStore | None = None

    def set_cache(self, cache: CacheStore | None) -> None:
        self._cache = cache

    def build_config(self, config: Mapping[str, Any] | None) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(self.default_config)
        if config:
            merged.update(config)
        return merged

    def cache_key(self, config: Mapping[str, Any]) -> str:
        return json.dumps(config, sort_keys=True, default=str, ensure_ascii=False)

    def cache_namespace(self) -> str:
        return self.slug

    async def fetch(
        self,
        config: Mapping[str, Any] | None,
        *,
        state: "AppState" | None = None,
    ) -> Any:
        merged_config = self.build_config(config)

        async def loader() -> Any:
            return await self._fetch(merged_config, state=state)

        if self._cache is None:
            return await loader()

        ttl = float(max(self.cache_ttl, 0.0))
        stale_ttl = float(max(self.cache_stale_ttl or ttl * 2, ttl))
        return await self._cache.get_or_load(
            self.cache_namespace(),
            self.cache_key(merged_config),
            loader,
            ttl,
            stale_ttl,
        )

    async def _fetch(self, config: Mapping[str, Any], state: "AppState" | None = None) -> Any:
        return config

    def render(self, surface: Surface, data: Any) -> Image.Image:
        raise NotImplementedError
