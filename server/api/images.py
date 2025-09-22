from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageOps

from ..app import AppState, get_app_state
from ..inky import display as inky_display
from ..storage.files import describe_image, list_images_sorted

router = APIRouter(tags=["images"])


def _detail_text(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str):
        return detail
    return str(detail)


def _image_path(name: str, state: AppState) -> Path:
    safe_name = os.path.basename(unquote(name))
    path = state.image_dir / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return path


@router.get("/list")
async def list_images(state: AppState = Depends(get_app_state)) -> dict:
    items = []
    for path in list_images_sorted(state.image_dir):
        try:
            items.append(describe_image(path))
        except Exception:
            continue
    return {"ok": True, "items": items}


@router.get("/image/{name:path}")
async def image_endpoint(name: str, state: AppState = Depends(get_app_state)) -> Response:
    path = _image_path(name, state)
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    elif suffix == ".png":
        media_type = "image/png"
    else:
        media_type = "application/octet-stream"
    return Response(content=data, media_type=media_type)


@router.post("/display", response_class=JSONResponse)
async def display_image(
    file: Optional[str] = Query(None, alias="file"),
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    if not file:
        return JSONResponse({"ok": False, "error": "Missing ?file="}, status_code=status.HTTP_400_BAD_REQUEST)

    if not inky_display.is_ready():
        return JSONResponse(
            {"ok": False, "error": "Inky display not available"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        path = _image_path(file, state)
    except HTTPException as exc:
        return JSONResponse({"ok": False, "error": _detail_text(exc)}, status_code=exc.status_code)

    try:
        with path.open("rb") as handle:
            image = Image.open(handle)
            processed = ImageOps.exif_transpose(image).convert("RGB")
        inky_display.display_image(processed)
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    files = list(list_images_sorted(state.image_dir))
    index = next((i for i, candidate in enumerate(files) if candidate.name == path.name), -1)
    state.carousel.set_current(path.name if index >= 0 else None, index=index)
    state.last_rendered = path.name
    return JSONResponse({"ok": True})


@router.post("/delete", response_class=JSONResponse)
async def delete_image(
    file: Optional[str] = Query(None, alias="file"),
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    if not file:
        return JSONResponse({"ok": False, "error": "Missing ?file="}, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        path = _image_path(file, state)
    except HTTPException as exc:
        return JSONResponse({"ok": False, "error": _detail_text(exc)}, status_code=exc.status_code)

    files_before = list(list_images_sorted(state.image_dir))
    snapshot = state.carousel.snapshot(
        files_before,
        last_rendered=state.last_rendered,
        default_minutes=state.runtime_config.carousel_minutes,
    )

    try:
        path.unlink()
    except FileNotFoundError:
        return JSONResponse({"ok": False, "error": "Image not found"}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)

    if state.last_rendered == path.name:
        state.last_rendered = None

    remaining = [candidate for candidate in files_before if candidate.name != path.name]
    remaining_names = [candidate.name for candidate in remaining]

    if not remaining_names:
        state.carousel.set_current(None)
    else:
        current_index = snapshot.current_index
        current_file = snapshot.current_file
        if current_index < 0:
            state.carousel.set_current(None)
        else:
            if current_file not in remaining_names:
                new_index = min(max(current_index, 0), len(remaining_names) - 1)
                new_file = remaining_names[new_index]
            else:
                new_index = remaining_names.index(current_file)
                new_file = current_file
            state.carousel.set_current(new_file, index=new_index)

    return JSONResponse({"ok": True})


__all__ = ["router", "list_images", "image_endpoint", "display_image", "delete_image"]
