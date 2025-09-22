"""Shared image helpers for upload processing."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

from .inky import display as inky_display


def open_image_first_frame(buf: io.BytesIO) -> Image.Image:
    buf.seek(0)
    img = Image.open(buf)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:  # pragma: no cover - defensive
        pass
    if getattr(img, "is_animated", False):
        try:
            img.seek(0)
        except Exception:  # pragma: no cover - defensive
            pass
    return img


def resize_fill_inky(img: Image.Image) -> Image.Image:
    target_width, target_height = inky_display.target_size()
    if img.width < img.height:
        img = img.transpose(Image.Transpose.ROTATE_90)

    target_ratio = target_width / target_height
    source_width, source_height = img.width, img.height
    source_ratio = source_width / source_height

    if source_ratio > target_ratio:
        new_width = int(source_height * target_ratio)
        left = (source_width - new_width) // 2
        img = img.crop((left, 0, left + new_width, source_height))
    else:
        new_height = int(source_width / target_ratio)
        top = (source_height - new_height) // 2
        img = img.crop((0, top, source_width, top + new_height))

    return img.convert("RGB").resize((target_width, target_height), Image.Resampling.LANCZOS)


__all__ = ["open_image_first_frame", "resize_fill_inky"]
