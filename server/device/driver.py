from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Iterable, Optional, Protocol, runtime_checkable

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover - defensive import guard
    print("ERROR: Pillow (PIL) is required:", exc, file=sys.stderr)
    raise SystemExit(1) from exc


@runtime_checkable
class FrameDriver(Protocol):
    """Protocol describing the interface for pushing frames to a device."""

    def push_frame(self, image_path: Path) -> None:
        """Push the PNG frame stored at *image_path* to the device."""


def _normalise_palette(raw_palette: Iterable[int]) -> set[tuple[int, int, int]]:
    values = list(raw_palette)
    colours: set[tuple[int, int, int]] = set()
    for index in range(0, len(values), 3):
        triplet = values[index : index + 3]
        if len(triplet) < 3:
            break
        colours.add((int(triplet[0]), int(triplet[1]), int(triplet[2])))
    return colours


class InkyDriver:
    """Driver implementation for an attached Inky display."""

    def __init__(self, inky_display: object) -> None:
        self._inky_display = inky_display
        self._lock = threading.Lock()
        palette = getattr(inky_display, "palette", None)
        self._allowed_palette: Optional[set[tuple[int, int, int]]] = None
        if palette is not None:
            try:
                self._allowed_palette = _normalise_palette(palette)
            except Exception:
                self._allowed_palette = None

    def push_frame(self, image_path: Path) -> None:
        if not image_path.exists() or not image_path.is_file():
            raise FileNotFoundError(f"Frame not found: {image_path}")

        with Image.open(image_path) as image:
            image.load()
            if image.format != "PNG":
                raise ValueError("Frame driver requires PNG input")
            if image.mode != "P":
                raise ValueError("Expected palettized PNG frame for Inky display")
            palette = image.getpalette()
            if palette is None:
                raise ValueError("PNG frame does not contain a palette")

            allowed = self._allowed_palette
            if allowed:
                used_entries = {index for _, index in (image.getcolors() or [])}
                for entry in used_entries:
                    offset = entry * 3
                    colour = tuple(palette[offset : offset + 3])
                    if colour not in allowed:
                        raise ValueError(f"Unsupported colour for Inky display: {colour}")

            rgb_image = image.convert("RGB")

        with self._lock:
            self._inky_display.set_image(rgb_image)
            self._inky_display.show()


__all__ = ["FrameDriver", "InkyDriver"]
