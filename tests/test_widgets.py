from datetime import datetime

from PIL import Image

from smart_display.config import AppConfig
from smart_display.display.layout import LayoutArea
from smart_display.display.style import DEFAULT_PALETTE
from smart_display.widgets.base import Widget, WidgetContext
from smart_display.widgets.factory import build_widgets


class DummyWidget(Widget[None]):
    def fetch(self):
        return None

    def draw(self, image, draw, context, data):  # pragma: no cover - never called
        raise AssertionError("draw should not be called when fetch returns None")


def test_placeholder_rendering_changes_canvas():
    widget = DummyWidget("dummy")
    image = Image.new("RGB", (100, 100), "white")
    context = WidgetContext(
        area=LayoutArea(0, 0, 100, 100),
        palette=DEFAULT_PALETTE,
        now=datetime.now(),
    )
    widget.render(image, context)
    assert image.getpixel((25, 25)) != (255, 255, 255)


def test_build_widgets_respects_disabled():
    config = AppConfig()
    config.news.enabled = False
    widgets = build_widgets(config)
    assert "news" not in widgets
    assert "agenda" in widgets
