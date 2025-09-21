from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List
from urllib.parse import quote

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover - defensive import guard
    print("ERROR: Pillow (PIL) is required:", exc, file=sys.stderr)
    raise SystemExit(1) from exc

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def ensure_image_dir(image_dir: Path) -> None:
    try:
        image_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"ERROR: Cannot create {image_dir}. Check permissions.", file=sys.stderr)
        raise


def list_images_sorted(image_dir: Path, allowed_ext: Iterable[str] | None = None) -> List[Path]:
    exts = set(ext.lower() for ext in (allowed_ext or ALLOWED_EXT))
    files = []
    if image_dir.exists():
        for path in image_dir.iterdir():
            if path.is_file() and path.suffix.lower() in exts.union({".jpg"}):
                files.append(path)
    return sorted(files, key=lambda p: p.name.lower())


def safe_slug(name: str) -> str:
    base = os.path.basename(name)
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"[^A-Za-z0-9._-]", "", base)
    return base or "image"


def save_image(image: Image.Image, original_name: str, image_dir: Path) -> Path:
    slug = safe_slug(original_name)
    stem, _ = os.path.splitext(slug)
    final_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{stem}.jpg"
    out_path = image_dir / final_name
    image.save(out_path, "JPEG", quality=90, optimize=True)
    return out_path


def describe_image(path: Path) -> dict:
    stats = path.stat()
    return {
        "name": path.name,
        "size": stats.st_size,
        "created_at": datetime.fromtimestamp(stats.st_mtime).isoformat(timespec="seconds"),
        "url": f"/image/{quote(path.name)}",
    }
