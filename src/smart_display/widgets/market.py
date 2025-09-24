"""Market overview widget."""
from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from ..config import MarketSettings
from ..data.market import MarketDataProvider, MarketSnapshot
from ..display.style import darken, lighten, load_font
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
        card_area = context.area.inset(10, 10)
        card_fill = lighten(palette.background, 0.12)
        border_colour = lighten(palette.muted, 0.25)
        draw.rounded_rectangle(
            [card_area.left, card_area.top, card_area.right, card_area.bottom],
            radius=26,
            fill=card_fill,
            outline=border_colour,
            width=2,
        )

        accent_line = [card_area.left, card_area.top, card_area.right, card_area.top + 6]
        draw.rectangle(accent_line, fill=lighten(palette.accent, 0.05))

        area = card_area.inset(26, 30)
        label_font = load_font(28, bold=True)
        symbol_font = load_font(22)
        price_font = load_font(46, bold=True)
        meta_font = load_font(20)

        y = area.top
        draw.text((area.left, y), "MARKET OVERVIEW", fill=palette.primary, font=label_font)
        y += _text_height(label_font) + 12
        draw.line([(area.left, y), (area.right, y)], fill=lighten(palette.muted, 0.1), width=2)
        y += 16

        draw.text((area.left, y), data.symbol, fill=palette.secondary, font=symbol_font)
        y += _text_height(symbol_font) + 10

        price_text = _format_price(data)
        draw.text((area.left, y), price_text, fill=palette.primary, font=price_font)
        y += _text_height(price_font) + 6

        change_text, change_colour = _format_change(data, palette)
        draw.text((area.left, y), change_text, fill=change_colour, font=meta_font)
        y += _text_height(meta_font) + 20

        timestamp_height = _text_height(meta_font) + 12 if data.last_updated else 0
        spark_area = (area.left, y, area.right, area.bottom - timestamp_height)
        _draw_sparkline(draw, spark_area, data.history, palette)

        if data.last_updated:
            timestamp = data.last_updated.strftime("Updated %H:%M")
            draw.text(
                (area.left, area.bottom - _text_height(meta_font)),
                timestamp,
                fill=lighten(palette.muted, 0.15),
                font=meta_font,
            )


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
    inner_padding = 18
    inner_bounds = (
        left + inner_padding,
        top + inner_padding,
        right - inner_padding,
        bottom - inner_padding,
    )
    if inner_bounds[2] <= inner_bounds[0] or inner_bounds[3] <= inner_bounds[1]:
        return

    bg_colour = palette.background
    outline_colour = lighten(palette.muted, 0.2)
    draw.rounded_rectangle(inner_bounds, radius=18, fill=lighten(bg_colour, 0.08), outline=outline_colour, width=1)

    inner_left, inner_top, inner_right, inner_bottom = inner_bounds
    inner_height = inner_bottom - inner_top
    inner_width = inner_right - inner_left

    grid_colour = darken(palette.secondary, 0.25)
    for fraction in (0.25, 0.5, 0.75):
        y = inner_top + inner_height * fraction
        draw.line([(inner_left + 8, y), (inner_right - 8, y)], fill=grid_colour, width=1)

    step = inner_width / (len(history) - 1)
    points = []
    for idx, price in enumerate(history):
        normalised = (price - min_price) / (max_price - min_price)
        x = inner_left + idx * step
        y = inner_bottom - normalised * inner_height
        points.append((x, y))
    line_colour = lighten(palette.accent, 0.1)
    draw.line(points, fill=line_colour, width=4)
    draw.ellipse(
        [points[-1][0] - 5, points[-1][1] - 5, points[-1][0] + 5, points[-1][1] + 5],
        fill=line_colour,
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
