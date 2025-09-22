from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from PIL import Image, ImageOps

from ..storage.files import safe_slug
from ..widgets import WidgetRegistry
from .layout import LayoutContent, get_layout
from .surface import FontManager, IconCache, Surface
from .theme import Theme, get_theme

Color = Tuple[int, int, int]
Palette = Iterable[Color]

EINK_PALETTES: Dict[str, Tuple[Color, ...]] = {
    "3": ((255, 255, 255), (0, 0, 0), (255, 0, 0)),
    "tri": ((255, 255, 255), (0, 0, 0), (255, 0, 0)),
    "4": ((255, 255, 255), (0, 0, 0), (255, 0, 0), (255, 255, 0)),
    "7": (
        (255, 255, 255),
        (0, 0, 0),
        (255, 0, 0),
        (255, 255, 0),
        (0, 128, 0),
        (0, 0, 200),
        (240, 128, 48),
    ),
    "8": (
        (255, 255, 255),
        (0, 0, 0),
        (255, 0, 0),
        (255, 255, 0),
        (0, 150, 0),
        (0, 0, 200),
        (240, 128, 48),
        (120, 0, 140),
    ),
}

ALIAS_PALETTES = {
    "inky3": "3",
    "inky4": "4",
    "inky7": "7",
    "inky8": "8",
}

FLOYD_STEINBERG = ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16))
ATKINSON = ((1, 0, 1 / 8), (2, 0, 1 / 8), (-1, 1, 1 / 8), (0, 1, 1 / 8), (1, 1, 1 / 8), (0, 2, 1 / 8))


@dataclass
class PipelineRequest:
    source: str
    identifier: str
    config: Mapping[str, Any] | None
    layout: str
    theme: str
    palette: str
    dither: str
    separators: bool = True


@dataclass
class PipelineResult:
    image: Image.Image
    output_path: Path
    cache_path: Path
    identifier: str
    source: str
    theme: Theme
    layout: str
    content: LayoutContent
    from_cache: bool


class RendererPipeline:
    def __init__(self, image_dir: Path, static_dir: Path, target_size: Tuple[int, int]) -> None:
        self.image_dir = image_dir
        self.cache_dir = image_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir = static_dir
        self.target_size = target_size
        self.font_manager = FontManager(self._font_search_paths())
        self.icon_cache = IconCache(self._icon_search_paths())
        self._cache: Dict[str, Path] = {}
        self._last_output: Optional[Path] = None

    def _font_search_paths(self) -> Iterable[Path]:
        paths = []
        candidate = self.static_dir / "fonts"
        if candidate.exists():
            paths.append(candidate)
        for extra in (Path("/usr/share/fonts"), Path("/usr/local/share/fonts")):
            if extra.exists():
                paths.append(extra)
        return paths

    def _icon_search_paths(self) -> Iterable[Path]:
        candidate = self.static_dir / "icons"
        return [candidate] if candidate.exists() else []

    def render(self, request: PipelineRequest, registry: WidgetRegistry) -> PipelineResult:
        base_image, content, version_token = self._fetch_source(request, registry)
        cache_key = self._cache_key(request, version_token)
        cache_path = self.cache_dir / f"{cache_key}.png"

        theme = get_theme(request.theme)
        from_cache = False
        if cache_path.exists():
            with Image.open(cache_path) as cached:
                final_image = cached.convert("RGB")
            from_cache = True
        else:
            surface = Surface.create(self.target_size, theme.background, fonts=self.font_manager, icons=self.icon_cache)
            layout_fn = get_layout(request.layout)
            composed = layout_fn(surface, base_image, theme, content, request.separators)
            final_image = apply_palette(composed, request.palette, request.dither)
            final_image.save(cache_path, format="PNG", optimize=True)
        final_image = final_image.copy()

        output_path = self._store_output(final_image, request, theme)
        self._cache[cache_key] = cache_path
        self._last_output = output_path
        return PipelineResult(
            image=final_image,
            output_path=output_path,
            cache_path=cache_path,
            identifier=request.identifier,
            source=request.source,
            theme=theme,
            layout=request.layout,
            content=content,
            from_cache=from_cache,
        )

    def latest_output(self) -> Optional[Path]:
        if self._last_output and self._last_output.exists():
            return self._last_output
        candidates = sorted(self.image_dir.glob("*.png"))
        return candidates[-1] if candidates else None

    def _store_output(self, image: Image.Image, request: PipelineRequest, theme: Theme) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = safe_slug(request.identifier or "render")
        base_name = f"{timestamp}_{slug}_{request.layout}_{theme.name}"
        candidate = self.image_dir / f"{base_name}.png"
        counter = 1
        while candidate.exists():
            candidate = self.image_dir / f"{base_name}_{counter}.png"
            counter += 1
        image.save(candidate, format="PNG", optimize=True)
        return candidate

    def _fetch_source(self, request: PipelineRequest, registry: WidgetRegistry):
        if request.source == "image":
            path = self._resolve_image(request.identifier)
            with Image.open(path) as handle:
                base = ImageOps.exif_transpose(handle).convert("RGB")
            stats = path.stat()
            created = datetime.fromtimestamp(stats.st_mtime).strftime("%d-%m-%Y %H:%M")
            title = Path(request.identifier).stem.replace("_", " ") or "Afbeelding"
            content = LayoutContent(
                title=title,
                subtitle="Fotogalerij",
                details=[f"Bestand: {path.name}", f"Laatst bijgewerkt: {created}"],
                footer="Inky Photoframe",
            )
            version = f"{stats.st_mtime_ns}:{stats.st_size}"
            return base, content, version
        widget = registry.get(request.identifier)
        rendered = widget.render(request.config or {}, self.target_size)
        details = [f"{key}: {value}" for key, value in sorted((request.config or {}).items())] or ["Geen configuratie"]
        content = LayoutContent(
            title=widget.name,
            subtitle=widget.description,
            details=details,
            footer="Widget",
        )
        version = self._hash_config(request.config or {})
        return rendered, content, version

    def _resolve_image(self, name: str) -> Path:
        safe_name = os.path.basename(name)
        path = self.image_dir / safe_name
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Afbeelding niet gevonden: {name}")
        return path

    def _hash_config(self, config: Mapping[str, Any]) -> str:
        payload = json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()

    def _cache_key(self, request: PipelineRequest, version_token: str) -> str:
        payload = "|".join(
            [
                request.source,
                request.identifier,
                version_token,
                request.layout,
                request.theme,
                request.palette,
                request.dither,
                "1" if request.separators else "0",
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _resolve_palette(name: str) -> Tuple[Color, ...]:
    key = ALIAS_PALETTES.get(name.lower(), name.lower())
    return EINK_PALETTES.get(key, EINK_PALETTES["7"])


def _nearest_color(color: Tuple[float, float, float], palette: Palette) -> Tuple[int, int, int]:
    r, g, b = color
    best: Optional[Tuple[int, int, int]] = None
    best_dist = float("inf")
    for pr, pg, pb in palette:
        dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if dist < best_dist:
            best_dist = dist
            best = (pr, pg, pb)
    if best is None:
        best = (0, 0, 0)
    return best


def _clamp(value: float) -> float:
    return min(255.0, max(0.0, value))


def _map_palette(image: Image.Image, palette: Palette) -> Image.Image:
    src = image.convert("RGB")
    width, height = src.size
    out = Image.new("RGB", (width, height))
    src_pixels = src.load()
    out_pixels = out.load()
    for y in range(height):
        for x in range(width):
            out_pixels[x, y] = _nearest_color(src_pixels[x, y], palette)
    return out


def _error_diffuse(image: Image.Image, palette: Palette, matrix) -> Image.Image:
    width, height = image.size
    working = image.convert("RGB")
    buffer = [[[float(channel) for channel in working.getpixel((x, y))] for x in range(width)] for y in range(height)]
    out = Image.new("RGB", (width, height))
    out_pixels = out.load()
    for y in range(height):
        for x in range(width):
            old = [
                _clamp(buffer[y][x][0]),
                _clamp(buffer[y][x][1]),
                _clamp(buffer[y][x][2]),
            ]
            new_color = _nearest_color(tuple(old), palette)
            out_pixels[x, y] = new_color
            error = [old[0] - new_color[0], old[1] - new_color[1], old[2] - new_color[2]]
            for dx, dy, ratio in matrix:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    for channel in range(3):
                        buffer[ny][nx][channel] += error[channel] * ratio
    return out


def apply_palette(image: Image.Image, palette_name: str, dither: str) -> Image.Image:
    palette = _resolve_palette(palette_name)
    mode = dither.lower()
    if mode in ("none", "off", "false"):
        return _map_palette(image, palette)
    if mode.startswith("atk"):
        return _error_diffuse(image, palette, ATKINSON)
    return _error_diffuse(image, palette, FLOYD_STEINBERG)


__all__ = ["RendererPipeline", "PipelineRequest", "PipelineResult", "apply_palette"]
