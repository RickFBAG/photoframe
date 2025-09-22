from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..inky import display as inky_display
from ..storage.files import describe_image, list_images_sorted

_LOGGER = logging.getLogger(__name__)


Palette = Tuple[int, int, int]


def _parse_hex_color(value: str) -> Palette:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f"Invalid hex colour: {value}")
    return tuple(int(value[i : i + 2], 16) for i in range(0, 6, 2))  # type: ignore[return-value]


def _normalise_param(value: Optional[str], default: str) -> str:
    candidate = (value or "").strip().lower()
    return candidate or default


def _theme_palette(theme: str) -> Tuple[Palette, Palette]:
    if theme == "dark":
        return _parse_hex_color("#0b0b0b"), _parse_hex_color("#f5f5f2")
    if theme in {"paper", "ink", "light"}:
        return _parse_hex_color("#f2f1ec"), _parse_hex_color("#111111")
    return _parse_hex_color("#ffffff"), _parse_hex_color("#111111")


@dataclass
class PreviewResult:
    """Result of a preview render operation."""

    key: Tuple[str, str]
    image_bytes: bytes
    generated_at: datetime
    stale: bool
    source_meta: Optional[Dict[str, object]]
    source_mtime: Optional[float]
    layout: str
    theme: str
    cache_hit: bool = False

    def iso_timestamp(self) -> str:
        return self.generated_at.isoformat(timespec="seconds")


class PreviewRenderer:
    """Renderer that produces cached preview images for the dashboard."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, str], PreviewResult] = {}
        self._lock = threading.Lock()

    def render(
        self,
        image_dir: Path,
        layout: Optional[str] = None,
        theme: Optional[str] = None,
    ) -> PreviewResult:
        layout_key = _normalise_param(layout, "default")
        theme_key = _normalise_param(theme, "ink")
        cache_key = (layout_key, theme_key)

        latest_path = self._latest_image(image_dir)
        latest_mtime = latest_path.stat().st_mtime if latest_path else None

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and cached.source_mtime == latest_mtime and not cached.stale:
                cached.cache_hit = True
                return cached

        try:
            if latest_path is not None:
                image = self._load_image(latest_path)
                meta: Optional[Dict[str, object]] = describe_image(latest_path)
                stale = False
            else:
                image = self._render_placeholder(layout_key, theme_key)
                meta = None
                stale = False

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            result = PreviewResult(
                key=cache_key,
                image_bytes=buffer.getvalue(),
                generated_at=datetime.now(),
                stale=stale,
                source_meta=meta,
                source_mtime=latest_mtime,
                layout=layout_key,
                theme=theme_key,
                cache_hit=False,
            )
        except Exception as exc:  # pragma: no cover - defensive catch
            _LOGGER.exception("Preview render failed: %s", exc)
            with self._lock:
                cached = self._cache.get(cache_key)
                if cached:
                    cached.stale = True
                    cached.cache_hit = True
                    cached.generated_at = datetime.now()
                    return cached
            raise

        with self._lock:
            self._cache[cache_key] = result
        return result

    @staticmethod
    def _latest_image(image_dir: Path) -> Optional[Path]:
        candidates = list(list_images_sorted(image_dir))
        if not candidates:
            return None
        return candidates[-1]

    @staticmethod
    def _load_image(path: Path) -> Image.Image:
        with path.open("rb") as handle:
            image = Image.open(handle)
            image = ImageOps.exif_transpose(image).convert("RGB")
        target = inky_display.target_size()
        if image.size != target:
            image = image.resize(target, Image.Resampling.LANCZOS)
        return image

    def _render_placeholder(self, layout: str, theme: str) -> Image.Image:
        bg, fg = _theme_palette(theme)
        size = inky_display.target_size()
        image = Image.new("RGB", size, color=bg)
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        lines = [
            "Geen voorbeeld beschikbaar",
            f"Layout: {layout}",
            f"Theme: {theme}",
        ]
        line_height = font.getbbox("Hg")[3] - font.getbbox("Hg")[1]
        total_height = line_height * len(lines) + 10 * (len(lines) - 1)
        y = (size[1] - total_height) // 2
        for line in lines:
            width = draw.textlength(line, font=font)
            x = (size[0] - int(width)) // 2
            draw.text((x, y), line, fill=fg, font=font)
            y += line_height + 10
        return image


__all__ = ["PreviewRenderer", "PreviewResult"]
