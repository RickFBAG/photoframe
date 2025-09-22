from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

Palette = Sequence[Tuple[int, int, int]]

ATKINSON_KERNEL = (
    (1, 0),
    (2, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
    (0, 2),
)


@dataclass
class ForecastEntry:
    label: str
    temp_min: float
    temp_max: float
    icon: str


def clamp(value: float, minimum: int = 0, maximum: int = 255) -> int:
    return max(minimum, min(int(round(value)), maximum))


def default_palette() -> Palette:
    return [
        (245, 245, 240),  # background
        (30, 30, 30),  # text
        (20, 80, 120),  # water / cool
        (200, 110, 50),  # warm accent
        (110, 160, 200),  # sky tint
        (240, 200, 120),  # sunlight
        (80, 120, 90),  # land
    ]


def create_canvas(size: Tuple[int, int], palette: Palette | None = None) -> Image.Image:
    palette = palette or default_palette()
    return Image.new("RGB", size, palette[0])


def _build_palette_image(palette: Palette) -> Image.Image:
    palette_image = Image.new("P", (1, 1))
    flat: List[int] = []
    for color in palette:
        flat.extend(color)
    # ensure the palette contains 256 * 3 values
    remainder = 256 - len(palette)
    if remainder > 0:
        flat.extend([0, 0, 0] * remainder)
    palette_image.putpalette(flat)
    return palette_image


def apply_floyd_steinberg_palette(image: Image.Image, palette: Palette | None = None) -> Image.Image:
    palette = palette or default_palette()
    palette_image = _build_palette_image(palette)
    quantized = image.convert("RGB").quantize(palette=palette_image, dither=Image.FLOYDSTEINBERG)
    return quantized.convert("RGB")


def _atkinson_luma(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    pixels = gray.load()
    width, height = gray.size
    for y in range(height):
        for x in range(width):
            old = pixels[x, y]
            new = 0 if old < 128 else 255
            error = old - new
            pixels[x, y] = new
            distributed = error / 8.0
            for dx, dy in ATKINSON_KERNEL:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    pixels[nx, ny] = clamp(pixels[nx, ny] + distributed)
    return Image.merge("RGB", (gray, gray, gray))


def apply_atkinson_texture(image: Image.Image, strength: float = 0.2) -> Image.Image:
    texture = _atkinson_luma(image)
    return Image.blend(image, texture, max(0.0, min(strength, 1.0)))


def draw_map(draw: ImageDraw.ImageDraw, size: Tuple[int, int], palette: Palette) -> None:
    width, height = size
    land_color = palette[6]
    water_color = palette[2]
    draw.rectangle((0, 0, width, height), fill=water_color)
    margin = int(min(width, height) * 0.08)
    body = [
        (margin, height - margin * 3),
        (margin * 3, margin),
        (width - margin * 2, margin * 2),
        (width - margin, height - margin),
        (width // 2, height - margin // 2),
    ]
    draw.polygon(body, fill=land_color, outline=palette[1])


def draw_location_marker(
    draw: ImageDraw.ImageDraw,
    size: Tuple[int, int],
    palette: Palette,
    latitude: float,
    longitude: float,
) -> Tuple[int, int]:
    width, height = size
    # Basic bounding box covering Western Europe
    min_lat, max_lat = 35.0, 70.0
    min_lon, max_lon = -10.0, 30.0
    norm_x = (longitude - min_lon) / (max_lon - min_lon)
    norm_y = 1 - (latitude - min_lat) / (max_lat - min_lat)
    cx = clamp(norm_x * width, 0, width - 1)
    cy = clamp(norm_y * height, 0, height - 1)
    radius = max(4, min(width, height) // 30)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=palette[3], outline=palette[1])
    draw.ellipse((cx - radius // 2, cy - radius // 2, cx + radius // 2, cy + radius // 2), fill=palette[5])
    return cx, cy


def draw_temperature_block(
    draw: ImageDraw.ImageDraw,
    top_left: Tuple[int, int],
    temperature: float,
    unit: str,
    palette: Palette,
    font_large: ImageFont.ImageFont,
    font_small: ImageFont.ImageFont,
    stale: bool = False,
) -> None:
    x, y = top_left
    temp_text = f"{temperature:.1f}°{unit.upper()[0]}"
    draw.text((x, y), temp_text, fill=palette[5], font=font_large)
    if stale:
        draw.text((x, y + font_large.size + 4), "verouderd", fill=palette[1], font=font_small)


def draw_forecast_panel(
    draw: ImageDraw.ImageDraw,
    area: Tuple[int, int, int, int],
    forecast: Iterable[ForecastEntry],
    palette: Palette,
    font_small: ImageFont.ImageFont,
    font_large: ImageFont.ImageFont,
) -> None:
    left, top, right, bottom = area
    draw.rectangle(area, outline=palette[1], width=2)
    forecast_list = list(forecast)
    column_width = (right - left) // max(1, len(forecast_list))
    for index, entry in enumerate(forecast_list):
        cx = left + index * column_width
        if index:
            draw.line((cx, top, cx, bottom), fill=palette[2])
        header_y = top + 6
        draw.text((cx + 8, header_y), entry.label, fill=palette[1], font=font_small)
        temp_text = f"{entry.temp_max:.0f}/{entry.temp_min:.0f}°"
        draw.text((cx + 8, header_y + font_small.size + 4), temp_text, fill=palette[3], font=font_large)
        draw_weather_icon(
            draw,
            (cx + column_width // 2, header_y + font_small.size * 2 + font_large.size + 16),
            entry.icon,
            palette,
            size=32,
        )


def draw_weather_icon(
    draw: ImageDraw.ImageDraw,
    center: Tuple[int, int],
    icon: str,
    palette: Palette,
    size: int = 48,
) -> None:
    cx, cy = center
    radius = size // 2
    base_color = palette[5]
    accent = palette[3]
    outline = palette[1]
    if icon == "sun":
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=base_color, outline=outline)
        for i in range(8):
            angle = math.pi / 4 * i
            dx = math.cos(angle) * (radius + 6)
            dy = math.sin(angle) * (radius + 6)
            draw.line((cx, cy, cx + dx, cy + dy), fill=accent, width=2)
    elif icon == "cloud":
        offsets = [(-radius, 0), (-radius // 3, -radius // 2), (radius // 2, 0)]
        for ox, oy in offsets:
            draw.ellipse(
                (cx + ox - radius // 1.5, cy + oy - radius // 1.5, cx + ox + radius // 1.5, cy + oy + radius // 1.5),
                fill=base_color,
                outline=outline,
            )
    elif icon == "rain":
        draw_weather_icon(draw, center, "cloud", palette, size)
        for i in range(-1, 2):
            draw.line((cx + i * 8, cy + radius // 2, cx + i * 8 - 4, cy + radius), fill=accent, width=2)
    elif icon == "storm":
        draw_weather_icon(draw, center, "cloud", palette, size)
        draw.line((cx - 6, cy + radius // 2, cx + 4, cy + radius), fill=accent, width=3)
        draw.line((cx + 4, cy + radius, cx - 2, cy + radius + 12), fill=accent, width=3)
    elif icon == "snow":
        draw_weather_icon(draw, center, "cloud", palette, size)
        for i in range(6):
            angle = math.pi / 3 * i
            dx = math.cos(angle) * (radius // 2)
            dy = math.sin(angle) * (radius // 2)
            draw.line((cx, cy + radius // 2, cx + dx, cy + radius // 2 + dy), fill=accent, width=2)
    else:  # fallback icon
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=base_color, outline=outline)


def draw_text_box(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: Tuple[int, int],
    palette: Palette,
    font: ImageFont.ImageFont,
) -> None:
    x, y = position
    draw.text((x, y), text, fill=palette[1], font=font)


def draw_stale_overlay(image: Image.Image, palette: Palette, text: str = "Verouderde data") -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, image.width, image.height), fill=(palette[3][0], palette[3][1], palette[3][2], 60))
    font = ImageFont.load_default()
    text_width, text_height = draw.textsize(text, font=font)
    draw.text(
        ((image.width - text_width) // 2, image.height - text_height - 10),
        text,
        fill=(palette[1][0], palette[1][1], palette[1][2], 220),
        font=font,
    )
    image.alpha_composite(overlay)
