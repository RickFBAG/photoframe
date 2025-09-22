from __future__ import annotations

import hashlib
import os
import random
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..storage.files import ALLOWED_EXT
from . import WidgetDefinition, WidgetError, WidgetField

try:  # Optional dependency for real face detection
    import cv2  # type: ignore[import]
    import numpy as _np  # type: ignore[import]
except Exception:  # pragma: no cover - optional optimisation
    cv2 = None  # type: ignore[assignment]
    _np = None  # type: ignore[assignment]

if cv2 is not None:  # pragma: no cover - optional optimisation
    try:
        _CASCADE_PATH = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        _FACE_CASCADE = cv2.CascadeClassifier(str(_CASCADE_PATH))
        if _FACE_CASCADE.empty():  # pragma: no cover - defensive
            _FACE_CASCADE = None
    except Exception:  # pragma: no cover - defensive
        _FACE_CASCADE = None
else:
    _FACE_CASCADE = None


@dataclass
class _CachedList:
    timestamp: float
    files: list[Path]


@dataclass
class _CachedSelection:
    timestamp: float
    path: Path


@dataclass
class _CachedRender:
    timestamp: float
    png_path: Path
    source_mtime: float


class RenderSurface:
    """Simple drawing surface that supports post-processing hooks."""

    def __init__(self, size: tuple[int, int], background: str = "white") -> None:
        self.size = size
        self.image = Image.new("RGB", size, color=background)
        self._hooks: list[Callable[[Image.Image], Image.Image]] = []

    def add_hook(self, hook: Callable[[Image.Image], Image.Image]) -> None:
        self._hooks.append(hook)

    def apply(self) -> Image.Image:
        result = self.image
        for hook in self._hooks:
            result = hook(result)
        return result


class PhotosWidget(WidgetDefinition):
    """Widget that renders photos from a directory with smart cropping and caching."""

    INDEX_TTL = 30.0
    SELECTION_TTL = 90.0
    RENDER_TTL = 300.0

    def __init__(self) -> None:
        super().__init__(
            slug="photos",
            name="Foto galerij",
            description=(
                "Toont een foto uit een map met slimme selectie, gezichtsdetectie en optionele captions."
            ),
            fields=[
                WidgetField(
                    name="path",
                    label="Map met foto's",
                    field_type="string",
                    required=True,
                    description="Pad naar de map met foto's die getoond mogen worden.",
                ),
                WidgetField(
                    name="shuffle",
                    label="Shuffle",
                    field_type="boolean",
                    default=True,
                    description="Kies een willekeurige foto bij elke render.",
                ),
                WidgetField(
                    name="face_detection",
                    label="Gezichtsdetectie",
                    field_type="boolean",
                    default=True,
                    description="Centreer de uitsnede rond gezichten (vereist opencv, anders heuristiek).",
                ),
                WidgetField(
                    name="horizon_crop",
                    label="Horizon-crop",
                    field_type="boolean",
                    default=False,
                    description="Plaats de horizon iets lager bij staande foto's.",
                ),
                WidgetField(
                    name="show_caption",
                    label="Toon bestandsnaam als caption",
                    field_type="boolean",
                    default=False,
                    description="Toon een onderschrift met de bestandsnaam.",
                ),
                WidgetField(
                    name="caption_template",
                    label="Caption template",
                    field_type="string",
                    default="{name}",
                    description="Optioneel template voor captions (beschikbare velden: name, stem, filename, parent).",
                ),
                WidgetField(
                    name="auto_contrast",
                    label="Automatisch contrast",
                    field_type="boolean",
                    default=False,
                    description="Pas automatisch contrast toe op de uiteindelijke afbeelding.",
                ),
            ],
        )
        self._lock = threading.RLock()
        self._index_cache: dict[Path, _CachedList] = {}
        self._selection_cache: dict[str, _CachedSelection] = {}
        self._sequence_index: dict[str, int] = {}
        self._render_cache: dict[str, _CachedRender] = {}
        cache_dir = Path(tempfile.gettempdir()) / "photoframe-cache" / "photos"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir = cache_dir

    # ------------------------------------------------------------------
    # Helpers for configuration
    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "ja"}
        return bool(value)

    # ------------------------------------------------------------------
    # File discovery and selection
    def _list_images(self, directory: Path) -> list[Path]:
        now = time.monotonic()
        cached = self._index_cache.get(directory)
        if cached and now - cached.timestamp < self.INDEX_TTL:
            files = [path for path in cached.files if path.exists()]
            if files:
                return files

        files: list[Path] = []
        if directory.exists() and directory.is_dir():
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in ALLOWED_EXT:
                    files.append(path)
        if files:
            file_stats: list[tuple[float, Path]] = []
            for path in files:
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                file_stats.append((mtime, path))
            files = [item[1] for item in sorted(file_stats, key=lambda pair: pair[0], reverse=True)]
        self._index_cache[directory] = _CachedList(timestamp=now, files=files)
        return files

    def _selection_key(self, directory: Path, shuffle: bool) -> str:
        return f"{directory.resolve()}|shuffle={int(shuffle)}"

    def fetch(self, directory: Path, shuffle: bool) -> Path:
        key = self._selection_key(directory, shuffle)
        now = time.monotonic()
        with self._lock:
            cached = self._selection_cache.get(key)
            if cached and now - cached.timestamp < self.SELECTION_TTL and cached.path.exists():
                return cached.path

            files = self._list_images(directory)
            if not files:
                raise WidgetError("Geen foto's gevonden in de opgegeven map")

            if shuffle:
                previous = cached.path if cached else None
                candidates = [p for p in files if p != previous] or files
                chosen = random.choice(candidates)
            else:
                index = self._sequence_index.get(key, 0)
                chosen = files[index % len(files)]
                self._sequence_index[key] = (index + 1) % len(files)

            self._selection_cache[key] = _CachedSelection(timestamp=now, path=chosen)
            return chosen

    # ------------------------------------------------------------------
    # Rendering helpers
    def _render_cache_key(
        self,
        image_path: Path,
        source_mtime: float,
        size: tuple[int, int],
        face_detection: bool,
        horizon_crop: bool,
        caption: Optional[str],
        auto_contrast: bool,
    ) -> str:
        payload = "|".join(
            [
                str(image_path.resolve()),
                str(source_mtime),
                f"{size[0]}x{size[1]}",
                f"faces={int(face_detection)}",
                f"horizon={int(horizon_crop)}",
                f"caption={caption or ''}",
                f"contrast={int(auto_contrast)}",
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load_from_render_cache(
        self,
        key: str,
        source_mtime: float,
    ) -> Optional[Image.Image]:
        entry = self._render_cache.get(key)
        if not entry or not entry.png_path.exists():
            return None
        if entry.source_mtime < source_mtime:
            return None
        if time.monotonic() - entry.timestamp > self.RENDER_TTL:
            return None
        with Image.open(entry.png_path) as cached:
            return cached.convert("RGB")

    def _store_in_render_cache(
        self,
        key: str,
        image: Image.Image,
        source_mtime: float,
    ) -> None:
        cache_file = self._cache_dir / f"{key}.png"
        image.save(cache_file, format="PNG")
        self._render_cache[key] = _CachedRender(
            timestamp=time.monotonic(),
            png_path=cache_file,
            source_mtime=source_mtime,
        )
        self._cleanup_render_cache()

    def _cleanup_render_cache(self) -> None:
        # Keep cache directory tidy by removing expired files lazily
        expired_keys = [
            key
            for key, entry in self._render_cache.items()
            if not entry.png_path.exists() or time.monotonic() - entry.timestamp > self.RENDER_TTL
        ]
        for key in expired_keys:
            entry = self._render_cache.pop(key)
            try:
                entry.png_path.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Focus helpers
    def _detect_faces(self, image: Image.Image) -> list[tuple[int, int, int, int]]:
        if _FACE_CASCADE is None or cv2 is None or _np is None:  # pragma: no cover - optional
            return []
        array = _np.array(image.convert("RGB"))
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
        detections = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        result: list[tuple[int, int, int, int]] = []
        for (x, y, w, h) in detections:
            result.append((int(x), int(y), int(w), int(h)))
        return result

    def _heuristic_focus(self, image: Image.Image) -> tuple[float, float]:
        sample = image.convert("L").resize((64, 64), Image.Resampling.BILINEAR)
        pixels = list(sample.getdata())
        width, height = sample.size
        sum_w = 0.0
        sum_x = 0.0
        sum_y = 0.0
        for index, value in enumerate(pixels):
            weight = (value + 1) ** 1.2
            x = ((index % width) + 0.5) / width
            y = ((index // width) + 0.5) / height
            sum_w += weight
            sum_x += x * weight
            sum_y += y * weight
        if sum_w <= 0:
            return 0.5, 0.5
        return sum_x / sum_w, sum_y / sum_w

    def _focus_point(
        self,
        image: Image.Image,
        enable_faces: bool,
        horizon_crop: bool,
    ) -> tuple[float, float]:
        cx = cy = 0.5
        if enable_faces:
            faces = self._detect_faces(image)
            if faces:
                # use the largest detected face
                x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
                cx = (x + w / 2) / image.width
                cy = (y + h / 2) / image.height
        if not enable_faces or (cx == 0.5 and cy == 0.5):
            cx, cy = self._heuristic_focus(image)
        if horizon_crop:
            cy = max(cy, 0.58)
        return (min(max(cx, 0.2), 0.8), min(max(cy, 0.25), 0.85))

    # ------------------------------------------------------------------
    # Caption helpers
    def _caption_text(self, image_path: Path, template: str) -> Optional[str]:
        try:
            name = image_path.stem.replace("_", " ").strip()
            parent = image_path.parent.name
            values = {
                "name": name or image_path.stem,
                "stem": image_path.stem,
                "filename": image_path.name,
                "parent": parent,
            }
            text = template.format(**values).strip()
        except Exception:
            text = image_path.stem
        return text or None

    # ------------------------------------------------------------------
    def render(self, config: Mapping[str, Any], size: tuple[int, int]) -> Image.Image:
        if not size or size[0] <= 0 or size[1] <= 0:
            raise WidgetError("Ongeldige doelresolutie opgegeven")

        raw_path = str(config.get("path") or "").strip()
        if not raw_path:
            raise WidgetError("Configuratie mist het pad naar de fotomap")
        directory = Path(os.path.expanduser(raw_path))

        shuffle = self._to_bool(config.get("shuffle"), True)
        face_detection = self._to_bool(config.get("face_detection"), True)
        horizon_crop = self._to_bool(config.get("horizon_crop"), False)
        show_caption = self._to_bool(config.get("show_caption"), False)
        caption_template = str(config.get("caption_template") or "{name}")
        auto_contrast = self._to_bool(config.get("auto_contrast"), False)

        image_path = self.fetch(directory, shuffle)

        try:
            source_mtime = image_path.stat().st_mtime
        except OSError as exc:
            raise WidgetError(f"Foto niet toegankelijk: {image_path}") from exc

        caption_text = self._caption_text(image_path, caption_template) if show_caption else None
        cache_key = self._render_cache_key(
            image_path,
            source_mtime,
            size,
            face_detection,
            horizon_crop,
            caption_text,
            auto_contrast,
        )

        with self._lock:
            cached = self._load_from_render_cache(cache_key, source_mtime)
            if cached is not None:
                return cached

        try:
            with Image.open(image_path) as handle:
                original = ImageOps.exif_transpose(handle.convert("RGB"))
        except FileNotFoundError as exc:
            raise WidgetError(f"Foto niet gevonden: {image_path}") from exc

        focus = self._focus_point(original, face_detection, horizon_crop)

        caption_height = 0
        if caption_text:
            caption_height = max(size[1] // 8, 28)
            caption_height = min(caption_height, size[1] // 3)

        photo_height = max(1, size[1] - caption_height)
        centering = (focus[0], focus[1])
        photo = ImageOps.fit(
            original,
            (size[0], photo_height),
            method=Image.Resampling.LANCZOS,
            centering=centering,
        )

        surface = RenderSurface(size)
        surface.add_hook(self._ensure_rgb)
        if auto_contrast:
            surface.add_hook(lambda img: ImageOps.autocontrast(img))

        surface.image.paste(photo, (0, 0))

        if caption_text:
            draw = ImageDraw.Draw(surface.image)
            draw.rectangle(
                [(0, photo_height), (size[0], size[1])],
                fill=(255, 255, 255),
            )
            font = ImageFont.load_default()
            text_width, text_height = draw.textsize(caption_text, font=font)
            position = (
                max(8, (size[0] - text_width) // 2),
                photo_height + max(4, (caption_height - text_height) // 2),
            )
            draw.text(position, caption_text, fill="black", font=font)

        result = surface.apply()

        with self._lock:
            self._store_in_render_cache(cache_key, result, source_mtime)

        return result

    @staticmethod
    def _ensure_rgb(image: Image.Image) -> Image.Image:
        return image.convert("RGB")


__all__ = ["PhotosWidget", "RenderSurface"]
