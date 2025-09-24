"""Market overview widget."""
from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from ..config import MarketSettings
from ..data.market import MarketDataProvider, MarketSnapshot
from ..display.style import load_font
from .base import Widget, WidgetContext


class MarketWidget(Widget[MarketSnapshot]):
    def __init__(self, settings: MarketSettings) -> None:
        super().__init__("market", enabled=settings.enabled)
        self.provider = MarketDataProvider(settings)
        self.settings = settings

    def fetch(self) -> Optional[MarketSnapshot]:
        return self.provider.fetch()

    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, context: WidgetContext, data: MarketSnapshot) -> None:
        palette = context.palette
        area = context.area.inset(18, 18)
        draw.rectangle([area.left, area.top, area.right, area.bottom], fill=(253, 253, 251), outline=palette.muted, width=2)

        label_font = load_font(24, bold=True)
        symbol_font = load_font(22)
        price_font = load_font(42, bold=True)
        meta_font = load_font(18)

        draw.text((area.left + 8, area.top + 4), "Market", fill=palette.primary, font=label_font)
        y = area.top + 4 + _text_height(label_font)

        draw.text((area.left + 8, y + 6), data.symbol, fill=palette.secondary, font=symbol_font)
        y += 6 + _text_height(symbol_font)

        price_text = _format_price(data)
        draw.text((area.left + 8, y + 8), price_text, fill=palette.primary, font=price_font)

        change_text, change_colour = _format_change(data, palette)
        draw.text((area.left + 8, y + 16 + _text_height(price_font)), change_text, fill=change_colour, font=meta_font)

        if data.last_updated:
            timestamp = data.last_updated.strftime("Updated %H:%M")
            draw.text(
                (area.left + 8, area.bottom - _text_height(meta_font) - 8),
                timestamp,
                fill=palette.muted,
                font=meta_font,
            )

        spark_top = y + 20 + _text_height(price_font)
        spark_area = (area.left + 8, spark_top, area.right - 8, area.bottom - _text_height(meta_font) - 18)
        _draw_sparkline(draw, spark_area, data.history, palette)


def _draw_sparkline(draw: ImageDraw.ImageDraw, bounds, history, palette) -> None:
    if len(history) < 2:
        return
    left, top, right, bottom = bounds
    min_price = min(history)
    max_price = max(history)
    height = bottom - top
    width = right - left
    if height <= 0 or width <= 0:
        return
    if max_price == min_price:
        max_price += 1
    step = width / (len(history) - 1)
    points = []
    for idx, price in enumerate(history):
        normalised = (price - min_price) / (max_price - min_price)
        x = left + idx * step
        y = bottom - normalised * height
        points.append((x, y))
    draw.line(points, fill=palette.primary, width=3)
    draw.ellipse(
        [points[-1][0] - 4, points[-1][1] - 4, points[-1][0] + 4, points[-1][1] + 4],
        fill=palette.primary,
    )


def _format_price(snapshot: MarketSnapshot) -> str:
    if snapshot.price is None:
        return "--"
    currency = snapshot.currency or ""
    return f"{snapshot.price:,.2f} {currency}".strip()


def _format_change(snapshot: MarketSnapshot, palette) -> tuple[str, tuple[int, int, int]]:
    change = snapshot.change or 0.0
    percent = snapshot.change_percent or 0.0
    sign = "+" if change >= 0 else ""
    colour = palette.positive if change >= 0 else palette.accent
    return f"{sign}{change:.2f} ({sign}{percent:.2f}%)", colour


def _text_height(font) -> int:
    bbox = font.getbbox("Hg")
    return bbox[3] - bbox[1]


__all__ = ["MarketWidget"]
