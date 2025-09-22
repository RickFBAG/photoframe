from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Dict, Iterable, Optional

from importlib import metadata

from ..cache import CacheStore
from .base import WidgetBase, WidgetError

LOGGER = logging.getLogger(__name__)

__all__ = ["WidgetRegistry"]


class WidgetRegistry:
    """Registry that auto-discovers widget implementations."""

    ENTRY_POINT_GROUP = "photoframe.widgets"

    def __init__(
        self,
        *,
        cache: CacheStore | None = None,
        auto_load: bool = True,
        entry_point_group: Optional[str] = None,
    ) -> None:
        self._widgets: Dict[str, WidgetBase] = {}
        self._cache = cache
        self.entry_point_group = entry_point_group or self.ENTRY_POINT_GROUP
        if auto_load:
            self._load_builtin_modules()
            self._load_entry_points()

    @property
    def cache(self) -> CacheStore | None:
        return self._cache

    def set_cache(self, cache: CacheStore | None) -> None:
        self._cache = cache
        for widget in self._widgets.values():
            widget.set_cache(cache)

    def register(self, widget: WidgetBase) -> None:
        if widget.slug in self._widgets:
            raise WidgetError(f"Widget '{widget.slug}' is already registered")
        widget.set_cache(self._cache)
        self._widgets[widget.slug] = widget

    def get(self, slug: str) -> WidgetBase:
        try:
            return self._widgets[slug]
        except KeyError as exc:  # pragma: no cover - defensive
            raise WidgetError(f"Onbekende widget: {slug}") from exc

    def list(self) -> Iterable[WidgetBase]:
        return self._widgets.values()

    def __contains__(self, slug: str) -> bool:
        return slug in self._widgets

    # Discovery helpers -------------------------------------------------

    def _load_builtin_modules(self) -> None:
        package_name = __name__.rsplit(".", 1)[0]
        package = importlib.import_module(package_name)
        if not hasattr(package, "__path__"):
            return
        for module_info in pkgutil.iter_modules(package.__path__):
            if module_info.ispkg:
                continue
            if module_info.name in {"base", "registry", "__init__"}:
                continue
            if module_info.name.startswith("_"):
                continue
            module_name = f"{package_name}.{module_info.name}"
            self._load_from_module(module_name)

    def _load_from_module(self, module_name: str) -> None:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to import widget module '%s'", module_name)
            return
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, WidgetBase) or obj is WidgetBase:
                continue
            try:
                widget = obj()
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Failed to initialise widget '%s'", obj.__name__)
                continue
            try:
                self.register(widget)
            except WidgetError:
                LOGGER.warning("Skipping duplicate widget '%s'", widget.slug)

    def _load_entry_points(self) -> None:
        try:
            entry_points = metadata.entry_points()
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("Unable to load widget entry points")
            return

        group = self.entry_point_group
        if hasattr(entry_points, "select"):
            candidates = entry_points.select(group=group)
        else:  # pragma: no cover - legacy API
            candidates = entry_points.get(group, [])  # type: ignore[assignment]

        for entry_point in candidates:
            try:
                loaded = entry_point.load()
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Failed to load widget from entry point '%s'", entry_point.name)
                continue
            widget: Optional[WidgetBase] = None
            if inspect.isclass(loaded) and issubclass(loaded, WidgetBase):
                try:
                    widget = loaded()
                except Exception:  # pragma: no cover - defensive logging
                    LOGGER.exception("Failed to initialise widget '%s'", loaded.__name__)
                    continue
            elif isinstance(loaded, WidgetBase):
                widget = loaded
            elif callable(loaded):
                try:
                    candidate = loaded()
                except Exception:  # pragma: no cover - defensive logging
                    LOGGER.exception("Entry point '%s' callable raised", entry_point.name)
                    continue
                if isinstance(candidate, WidgetBase):
                    widget = candidate
            if widget is None:
                LOGGER.warning("Entry point '%s' did not provide a WidgetBase", entry_point.name)
                continue
            try:
                self.register(widget)
            except WidgetError:
                LOGGER.warning("Skipping duplicate widget '%s'", widget.slug)
