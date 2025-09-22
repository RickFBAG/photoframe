from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover - defensive import guard
    print("ERROR: Pillow (PIL) is required:", exc, file=sys.stderr)
    raise SystemExit(1) from exc

try:
    from inky.auto import auto
except Exception as exc:  # pragma: no cover - defensive import guard
    print("ERROR: inky library is required and the display must be connected:", exc, file=sys.stderr)
    raise SystemExit(1) from exc

from ..device.driver import FrameDriver, InkyDriver

try:
    _inky_display = auto()
except Exception as exc:  # pragma: no cover - defensive import guard
    print("ERROR: Could not initialize Inky display:", exc, file=sys.stderr)
    raise SystemExit(1) from exc

_ROTATE_180_ON_DISPLAY = False
_DRIVER: Optional[FrameDriver] = None
_HARDWARE_READY = False

try:
    DISP_W, DISP_H = _inky_display.width, _inky_display.height
    if DISP_W < DISP_H:
        DISP_W, DISP_H = DISP_H, DISP_W
    _HARDWARE_READY = True
    DISPLAY_READY = True
    _DRIVER = InkyDriver(_inky_display)
except Exception as exc:  # pragma: no cover - hardware specific
    print("ERROR: Could not determine Inky display dimensions:", exc, file=sys.stderr)
    _HARDWARE_READY = False
    DISPLAY_READY = False
    DISP_W, DISP_H = 800, 480
    _DRIVER = None

_FRAME_DIR = Path(os.environ.get("PHOTOFRAME_FRAME_DIR", tempfile.gettempdir())) / "photoframe"
_FRAME_BASENAME = "last-frame.png"
_FRAME_DIR.mkdir(parents=True, exist_ok=True)
_LAST_FRAME_PATH: Optional[Path] = None

_DEFAULT_PALETTE = [
    255, 255, 255,
    0, 0, 0,
    255, 0, 0,
    255, 255, 0,
]


def _palette_image() -> Image.Image:
    palette_data = getattr(_inky_display, "palette", None)
    if palette_data is not None:
        palette = list(palette_data)[: 256 * 3]
    else:
        palette = []
    if not palette or not any(palette):
        palette = list(_DEFAULT_PALETTE)
    if len(palette) < 256 * 3:
        palette.extend([0] * (256 * 3 - len(palette)))
    palette_image = Image.new("P", (1, 1))
    palette_image.putpalette(palette[: 256 * 3])
    return palette_image


def _default_frame_path() -> Path:
    return _FRAME_DIR / _FRAME_BASENAME


def _ensure_driver() -> FrameDriver:
    global _DRIVER
    if _DRIVER is None:
        if not _HARDWARE_READY:
            raise RuntimeError("Inky display not available")
        _DRIVER = InkyDriver(_inky_display)
    return _DRIVER


def _prepare_frame(image: Image.Image) -> Image.Image:
    need_w, need_h = _inky_display.width, _inky_display.height
    rgb = image.convert("RGB")
    if rgb.size != (need_w, need_h):
        rgb = rgb.resize((need_w, need_h), Image.Resampling.LANCZOS)
    if _ROTATE_180_ON_DISPLAY:
        rgb = rgb.transpose(Image.Transpose.ROTATE_180)
    palette_image = _palette_image()
    try:
        palettized = rgb.quantize(palette=palette_image, dither=Image.Dither.NONE)
    except AttributeError:  # pragma: no cover - Pillow < 10 compatibility
        palettized = rgb.quantize(palette=palette_image, dither=Image.NONE)
    return palettized


def is_ready() -> bool:
    return DISPLAY_READY and _DRIVER is not None


def target_size() -> Tuple[int, int]:
    return DISP_W, DISP_H


def panel_size() -> Tuple[int, int]:
    return _inky_display.width, _inky_display.height


def set_rotation(enabled: bool) -> None:
    global _ROTATE_180_ON_DISPLAY
    _ROTATE_180_ON_DISPLAY = enabled


def set_driver(driver: Optional[FrameDriver], *, ready: Optional[bool] = None) -> None:
    global _DRIVER, DISPLAY_READY
    _DRIVER = driver
    if ready is not None:
        DISPLAY_READY = ready
    else:
        DISPLAY_READY = _HARDWARE_READY if driver is None else True


def last_frame_path() -> Optional[Path]:
    return _LAST_FRAME_PATH


def push_frame(image: Image.Image, *, frame_path: Optional[Path] = None) -> Path:
    if not DISPLAY_READY:
        raise RuntimeError("Inky display not available")

    driver = _ensure_driver()
    palettized = _prepare_frame(image)

    output_path = frame_path or _default_frame_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    palettized.save(output_path, format="PNG")

    driver.push_frame(output_path)

    global _LAST_FRAME_PATH
    _LAST_FRAME_PATH = output_path
    return output_path


__all__ = [
    "is_ready",
    "target_size",
    "panel_size",
    "set_rotation",
    "set_driver",
    "last_frame_path",
    "push_frame",
]
