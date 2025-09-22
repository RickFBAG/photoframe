from __future__ import annotations

import io
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote, unquote

from PIL import Image, ImageOps

from ..app import FileResponse, HTTPError, JsonResponse, Request, ServerContext
from ..inky import display as inky_display
from ..storage.files import ALLOWED_EXT, describe_image, list_images_sorted, save_image

STATE_LOCK = threading.RLock()
CAROUSEL_RUNNING = False
CAROUSEL_MINUTES = 5
CAROUSEL_THREAD: threading.Thread | None = None
CAROUSEL_STOP_EVENT = threading.Event()
CURRENT_INDEX = -1
NEXT_SWITCH_AT: datetime | None = None
_CONTEXT: ServerContext | None = None


def register(router, context: ServerContext) -> None:
    global _CONTEXT
    _CONTEXT = context

    router.get("/status")(status_endpoint)
    router.get("/list")(list_endpoint)
    router.get("/image/<path:name>")(image_endpoint)
    router.post("/upload")(upload_endpoint)
    router.post("/display")(display_endpoint)
    router.post("/delete")(delete_endpoint)
    router.post("/carousel/start")(carousel_start_endpoint)
    router.post("/carousel/stop")(carousel_stop_endpoint)


def _require_context() -> ServerContext:
    if _CONTEXT is None:
        raise RuntimeError("Server context not initialised")
    return _CONTEXT


def _image_dir() -> Path:
    return _require_context().image_dir


def parse_multipart_files(request: Request, max_bytes: int = 200 * 1024 * 1024) -> List[Tuple[str, io.BytesIO]]:
    ctype = request.headers.get("Content-Type", "")
    if "multipart/form-data" not in ctype:
        raise HTTPError(400, "Content-Type must be multipart/form-data")
    boundary_marker = "boundary="
    if boundary_marker not in ctype:
        raise HTTPError(400, "No multipart boundary")
    boundary = ctype.split(boundary_marker, 1)[1].strip()
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]
    boundary_bytes = boundary.encode()

    try:
        content_len = int(request.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise HTTPError(400, "Invalid Content-Length") from exc
    if content_len <= 0:
        raise HTTPError(400, "Empty request body")
    if content_len > max_bytes:
        raise HTTPError(400, "Body too large")

    data = request.rfile.read(content_len)
    delimiter = b"--" + boundary_bytes
    parts = data.split(delimiter)

    files: List[Tuple[str, io.BytesIO]] = []
    total_size = 0
    for part in parts:
        if not part or part in (b"--\r\n", b"--"):
            continue
        try:
            header_blob, body = part.split(b"\r\n\r\n", 1)
        except ValueError:
            continue
        if body.endswith(b"\r\n"):
            body = body[:-2]
        if body.endswith(b"--"):
            body = body[:-2]
        headers_lines = header_blob.split(b"\r\n")
        dispo = b""
        for line in headers_lines:
            if line.lower().startswith(b"content-disposition"):
                dispo = line
                break
        if not dispo:
            continue
        disp_text = dispo.decode(errors="ignore")
        if 'name="file"' not in disp_text:
            continue
        start = disp_text.find('filename="')
        if start == -1:
            continue
        end = disp_text.find('"', start + 10)
        if end == -1:
            continue
        filename = disp_text[start + 10 : end]
        total_size += len(body)
        if total_size > max_bytes:
            raise HTTPError(400, "Files too large in total")
        files.append((filename, io.BytesIO(body)))

    if not files:
        raise HTTPError(400, "No files found in 'file' field")
    return files


def open_image_first_frame(buf: io.BytesIO) -> Image.Image:
    buf.seek(0)
    img = Image.open(buf)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if getattr(img, "is_animated", False):
        try:
            img.seek(0)
        except Exception:
            pass
    return img


def resize_fill_inky(img: Image.Image) -> Image.Image:
    tw, th = inky_display.target_size()
    if img.width < img.height:
        img = img.transpose(Image.Transpose.ROTATE_90)

    target_ratio = tw / th
    w, h = img.width, img.height
    src_ratio = w / h

    if src_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    return img.convert("RGB").resize((tw, th), Image.Resampling.LANCZOS)


def _get_image_path(name: str) -> Path:
    safe_name = os.path.basename(unquote(name))
    path = _image_dir() / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPError(404, "Image not found")
    return path


def _carousel_worker() -> None:
    global CURRENT_INDEX, NEXT_SWITCH_AT
    while not CAROUSEL_STOP_EVENT.is_set():
        with STATE_LOCK:
            files = list_images_sorted(_image_dir())
            if not files or not CAROUSEL_RUNNING:
                NEXT_SWITCH_AT = None
                break
            if CURRENT_INDEX < 0 or CURRENT_INDEX >= len(files) - 1:
                CURRENT_INDEX = 0
            else:
                CURRENT_INDEX += 1
            path = files[CURRENT_INDEX]
        try:
            with open(path, "rb") as fh:
                img = Image.open(fh)
                img = ImageOps.exif_transpose(img).convert("RGB")
            inky_display.push_frame(img)
        except Exception as exc:
            print(f"Display error for {path.name}: {exc}", file=sys.stderr)
        minutes = max(1, int(CAROUSEL_MINUTES))
        NEXT_SWITCH_AT = datetime.now() + timedelta(minutes=minutes)
        for _ in range(minutes * 60):
            if CAROUSEL_STOP_EVENT.is_set() or not CAROUSEL_RUNNING:
                return
            time.sleep(1)


def start_carousel(minutes: int) -> None:
    global CAROUSEL_THREAD, CAROUSEL_RUNNING, CAROUSEL_MINUTES
    with STATE_LOCK:
        files = list_images_sorted(_image_dir())
        if not files:
            raise RuntimeError("No images in /image")
        CAROUSEL_MINUTES = max(1, int(minutes))
        if CAROUSEL_RUNNING:
            stop_carousel()
        CAROUSEL_RUNNING = True
        CAROUSEL_STOP_EVENT.clear()
        CAROUSEL_THREAD = threading.Thread(target=_carousel_worker, daemon=True)
        CAROUSEL_THREAD.start()


def stop_carousel() -> None:
    global CAROUSEL_RUNNING, NEXT_SWITCH_AT
    with STATE_LOCK:
        CAROUSEL_RUNNING = False
        CAROUSEL_STOP_EVENT.set()
        NEXT_SWITCH_AT = None


def status_endpoint(request: Request, params: Dict[str, str]) -> JsonResponse:
    with STATE_LOCK:
        files = list_images_sorted(request.context.image_dir)
        current_name = files[CURRENT_INDEX].name if (0 <= CURRENT_INDEX < len(files)) else None
        payload = {
            "ok": True,
            "display_ready": inky_display.is_ready(),
            "target_size": list(inky_display.target_size()),
            "carousel": {
                "running": CAROUSEL_RUNNING,
                "minutes": CAROUSEL_MINUTES,
                "current_index": CURRENT_INDEX,
                "current_file": current_name,
                "next_switch_at": NEXT_SWITCH_AT.isoformat(timespec="seconds") if NEXT_SWITCH_AT else None,
            },
        }
    return JsonResponse(payload)


def list_endpoint(request: Request, params: Dict[str, str]) -> JsonResponse:
    items = []
    for path in list_images_sorted(request.context.image_dir):
        try:
            items.append(describe_image(path))
        except Exception:
            continue
    return JsonResponse({"ok": True, "items": items})


def image_endpoint(request: Request, params: Dict[str, str]) -> FileResponse:
    name = params.get("name", "")
    path = _get_image_path(name)
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        content_type = "image/jpeg"
    elif suffix == ".png":
        content_type = "image/png"
    else:
        content_type = "application/octet-stream"
    return FileResponse(data, content_type)


def upload_endpoint(request: Request, params: Dict[str, str]) -> JsonResponse:
    try:
        files = parse_multipart_files(request)
        results = []
        errors = []
        for filename, buf in files:
            try:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ALLOWED_EXT:
                    raise ValueError(f"Unsupported file type: {ext}")
                img = open_image_first_frame(buf)
                processed = resize_fill_inky(img)
                out = save_image(processed, filename, request.context.image_dir)
                results.append({"file": out.name, "url": f"/image/{quote(out.name)}"})
            except Exception as exc:
                errors.append({"file": filename, "error": str(exc)})

        ok = len(results) > 0 and len(errors) == 0
        status = 200 if ok else (207 if results else 400)
        return JsonResponse({"ok": ok, "saved": results, "errors": errors}, status=status)
    except HTTPError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


def display_endpoint(request: Request, params: Dict[str, str]) -> JsonResponse:
    try:
        if not inky_display.is_ready():
            raise RuntimeError("Inky display not available")
        file_param = request.get_query("file")
        if not file_param:
            raise ValueError("Missing ?file=")
        path = _get_image_path(file_param)
        with open(path, "rb") as fh:
            img = Image.open(fh)
            img = ImageOps.exif_transpose(img).convert("RGB")
        inky_display.push_frame(img)
        with STATE_LOCK:
            files = list_images_sorted(request.context.image_dir)
            global CURRENT_INDEX
            CURRENT_INDEX = next((i for i, candidate in enumerate(files) if candidate.name == path.name), -1)
        return JsonResponse({"ok": True})
    except HTTPError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=503)


def delete_endpoint(request: Request, params: Dict[str, str]) -> JsonResponse:
    try:
        file_param = request.get_query("file")
        if not file_param:
            raise ValueError("Missing ?file=")
        path = _get_image_path(file_param)
        path.unlink()
        with STATE_LOCK:
            files = list_images_sorted(request.context.image_dir)
            global CURRENT_INDEX
            if CURRENT_INDEX >= len(files):
                CURRENT_INDEX = len(files) - 1
        return JsonResponse({"ok": True})
    except HTTPError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


def carousel_start_endpoint(request: Request, params: Dict[str, str]) -> JsonResponse:
    try:
        minutes_raw = request.get_query("minutes")
        if not minutes_raw:
            raise ValueError("Minutes must be provided")
        minutes = int(minutes_raw)
        if minutes < 1:
            raise ValueError("Minutes must be >= 1")
        if not inky_display.is_ready():
            raise RuntimeError("Inky display not available")
        start_carousel(minutes)
        return JsonResponse({"ok": True})
    except HTTPError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=exc.status)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


def carousel_stop_endpoint(request: Request, params: Dict[str, str]) -> JsonResponse:
    try:
        stop_carousel()
        return JsonResponse({"ok": True})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


__all__ = [
    "register",
    "start_carousel",
    "stop_carousel",
]
