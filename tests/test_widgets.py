from __future__ import annotations

import asyncio
import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "server" not in sys.modules:
    server_module = types.ModuleType("server")
    server_module.__path__ = [str(ROOT / "server")]
    server_module.__spec__ = ModuleSpec("server", loader=None, is_package=True)
    sys.modules["server"] = server_module

from server.cache import CacheStore
from server.widgets import Surface, WidgetRegistry, WidgetRenderContext
from server.widgets.message import MessageWidget


def test_registry_fetch_and_render() -> None:
    registry = WidgetRegistry()
    widgets = list(registry.list())
    slugs = {widget.slug for widget in widgets}
    assert {"message", "clock"}.issubset(slugs)

    async def run() -> None:
        for widget in widgets:
            context = await widget.fetch({}, state=None)
            assert isinstance(context, WidgetRenderContext)
            surface = Surface((400, 300), theme=context.theme)
            image = widget.render(surface, context)
            assert image.size == (400, 300)

    asyncio.run(run())


def test_registry_with_cache_discovers_builtin_widgets() -> None:
    cache = CacheStore()
    registry = WidgetRegistry(cache=cache)

    slugs = {widget.slug for widget in registry.list()}

    assert {"message", "clock"}.issubset(slugs)


def test_message_widget_uses_default_text() -> None:
    widget = MessageWidget()

    async def run() -> None:
        context = await widget.fetch({"text": "   "}, state=None)
        assert context.data == "Photoframe"

    asyncio.run(run())
