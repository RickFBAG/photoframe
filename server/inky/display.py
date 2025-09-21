from __future__ import annotations

import sys
import threading
from typing import Tuple

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

try:
    inky_display = auto()
except Exception as exc:  # pragma: no cover - defensive import guard
    print("ERROR: Could not initialize Inky display:", exc, file=sys.stderr)
    raise SystemExit(1) from exc

INKY_LOCK = threading.Lock()
ROTATE_180_ON_DISPLAY = False

try:
    DISP_W, DISP_H = inky_display.width, inky_display.height
    if DISP_W < DISP_H:
        DISP_W, DISP_H = DISP_H, DISP_W
    DISPLAY_READY = True
except Exception as exc:  # pragma: no cover - hardware specific
    print("ERROR: Could not determine Inky display dimensions:", exc, file=sys.stderr)
    DISPLAY_READY = False
    DISP_W, DISP_H = 800, 480


def is_ready() -> bool:
    return DISPLAY_READY


def target_size() -> Tuple[int, int]:
    return DISP_W, DISP_H


def panel_size() -> Tuple[int, int]:
    return inky_display.width, inky_display.height


def set_rotation(enabled: bool) -> None:
    global ROTATE_180_ON_DISPLAY
    ROTATE_180_ON_DISPLAY = enabled


def display_image(img: Image.Image) -> None:
    if not DISPLAY_READY:
        raise RuntimeError("Inky display not available")

    need_w, need_h = inky_display.width, inky_display.height
    rgb = img.convert("RGB")
    if rgb.size != (need_w, need_h):
        rgb = rgb.resize((need_w, need_h), Image.Resampling.LANCZOS)

    if ROTATE_180_ON_DISPLAY:
        rgb = rgb.transpose(Image.Transpose.ROTATE_180)

    with INKY_LOCK:
        inky_display.set_image(rgb)
        inky_display.show()
