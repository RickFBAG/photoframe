from __future__ import annotations

from typing import Tuple

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..app import AppState, get_app_state
from ..inky import display as inky_display
from ..storage.files import list_images_sorted

router = APIRouter(tags=["status"])


class HealthResponse(BaseModel):
    ok: bool
    display_ready: bool
    target_size: Tuple[int, int]
    image_count: int


@router.get("/health", response_model=HealthResponse)
async def health(state: AppState = Depends(get_app_state)) -> HealthResponse:
    files = list(list_images_sorted(state.image_dir))
    return HealthResponse(
        ok=True,
        display_ready=inky_display.is_ready(),
        target_size=inky_display.target_size(),
        image_count=len(files),
    )

@router.get("/preview")
async def preview(state: AppState = Depends(get_app_state)) -> Response:
    latest = state.renderer.latest_output()
    if latest and latest.exists():
        headers = {"Cache-Control": "no-store"}
        return FileResponse(latest, media_type="image/png", filename=latest.name, headers=headers)
    return Response(status_code=status.HTTP_404_NOT_FOUND)
