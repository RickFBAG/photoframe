from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence, TYPE_CHECKING

from PIL import Image

from ..cache import CacheStore
from .surface import Surface, Theme

if TYPE_CHECKING:  # pragma: no cover
    from ..app import AppState

__all__ = ["WidgetError", "WidgetField", "WidgetRenderContext", "WidgetBase"]


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


@dataclass(slots=True)
class WidgetRenderContext:
    """Container describing the data required to render a widget."""

    data: Any
    config: Mapping[str, Any]
    theme: Theme


class WidgetBase:
    """Base class for widgets exposing configuration metadata and rendering."""

    def __init__(
        self,
        *,
        slug: str,
        name: str,
        description: str,
        fields: Sequence[WidgetField] | None = None,
        default_config: Mapping[str, Any] | None = None,
        cache_ttl: float = 30.0,
        cache_stale_ttl: float | None = None,
    ) -> None:
        if not slug:
            raise WidgetError(f"Widget {self.__class__.__name__} must define a slug")
        self.slug = slug
        self.name = name
        self.description = description
        self.fields = tuple(fields or ())
        self.default_config = dict(default_config or {})
        self.cache_ttl = float(cache_ttl)
        self.cache_stale_ttl = cache_stale_ttl
        self._cache: CacheStore | None = None

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

    # -- caching -------------------------------------------------------
    def set_cache(self, cache: CacheStore | None) -> None:
        self._cache = cache

    def cache_key(self, config: Mapping[str, Any]) -> str:
        return json.dumps(config, sort_keys=True, default=str, ensure_ascii=False)

    def cache_namespace(self) -> str:
        return self.slug

    # -- data lifecycle ------------------------------------------------
    async def fetch(
        self,
        config: Mapping[str, Any] | None,
        *,
        state: "AppState" | None = None,
    ) -> WidgetRenderContext:
        resolved = self.resolve_config(config)
        theme = self.get_theme(resolved)

        async def loader() -> WidgetRenderContext:
            data = await self._fetch(resolved, state=state)
            return WidgetRenderContext(data=data, config=resolved, theme=theme)

        if self._cache is None:
            return await loader()

        ttl = max(self.cache_ttl, 0.0)
        stale_ttl = self.cache_stale_ttl
        if stale_ttl is None:
            stale_ttl = ttl * 2
        stale_ttl = max(stale_ttl, ttl)

        return await self._cache.get_or_load(
            self.cache_namespace(),
            self.cache_key(resolved),
            loader,
            float(ttl),
            float(stale_ttl),
        )

    async def _fetch(
        self,
        config: Mapping[str, Any],
        *,
        state: "AppState" | None = None,
    ) -> Any:
        return None

    def draw(self, surface: Surface, data: Any, config: Mapping[str, Any]) -> None:
        raise NotImplementedError

    def render(self, surface: Surface, result: WidgetRenderContext | Any) -> Image.Image:
        if isinstance(result, WidgetRenderContext):
            context = result
        else:  # pragma: no cover - backwards compatibility
            context = WidgetRenderContext(
                data=result,
                config=self.default_config,
                theme=surface.theme,
            )

        self.draw(surface, context.data, context.config)
        return surface.image
