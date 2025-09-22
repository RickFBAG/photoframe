"""Upload endpoint for processing images via FastAPI."""

from __future__ import annotations

import io
import os
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from ..app import AppState, get_app_state
from ..storage.files import ALLOWED_EXT, save_image
from ..image_processing import open_image_first_frame, resize_fill_inky

router = APIRouter(tags=["uploads"])

_MAX_TOTAL_BYTES = 200 * 1024 * 1024


def _json_response(
    *,
    ok: bool,
    saved: list[dict[str, Any]],
    errors: list[dict[str, str]],
    status_code: int,
    message: str | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {"ok": ok, "saved": saved, "errors": errors}
    if message:
        payload["error"] = message
    return JSONResponse(payload, status_code=status_code)


def _collect_uploads(form_data: Any) -> list[UploadFile]:
    if hasattr(form_data, "getlist"):
        candidates = form_data.getlist("file")
    else:  # pragma: no cover - defensive
        candidates = []
    return [item for item in candidates if isinstance(item, UploadFile)]


@router.post("/upload", response_class=JSONResponse)
async def upload_images(
    request: Request,
    state: AppState = Depends(get_app_state),
) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        message = "Content-Type must be multipart/form-data"
        return _json_response(
            ok=False,
            saved=[],
            errors=[{"file": "", "error": message}],
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message,
        )

    try:
        form_data = await request.form()
    except Exception:
        message = "Invalid multipart payload"
        return _json_response(
            ok=False,
            saved=[],
            errors=[{"file": "", "error": message}],
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message,
        )

    uploads = _collect_uploads(form_data)
    if not uploads:
        message = "No files were provided"
        return _json_response(
            ok=False,
            saved=[],
            errors=[{"file": "", "error": message}],
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message,
        )

    saved: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    total_bytes = 0

    for upload in uploads:
        filename = upload.filename or "upload"
        try:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXT:
                raise ValueError(f"Unsupported file type: {ext}")

            data = await upload.read()
            total_bytes += len(data)
            if total_bytes > _MAX_TOTAL_BYTES:
                raise ValueError("Files too large in total")

            buffer = io.BytesIO(data)
            image = open_image_first_frame(buffer)
            processed = resize_fill_inky(image)
            out_path = save_image(processed, filename, state.image_dir)
            saved.append({"file": out_path.name, "url": f"/image/{quote(out_path.name)}"})
        except Exception as exc:  # pragma: no cover - error path tested separately
            errors.append({"file": filename, "error": str(exc)})
        finally:
            await upload.close()

    ok = bool(saved) and not errors
    status_code = status.HTTP_200_OK if ok else (
        status.HTTP_207_MULTI_STATUS if saved else status.HTTP_400_BAD_REQUEST
    )
    message = None if ok else (errors[0]["error"] if errors else "Upload error")
    return _json_response(
        ok=ok,
        saved=saved,
        errors=errors,
        status_code=status_code,
        message=message,
    )


__all__ = ["router", "upload_images"]
