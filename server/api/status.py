from __future__ import annotations

from typing import Optional, Tuple

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..app import AppState, get_app_state
from ..inky import display as inky_display
from ..storage.files import describe_image, list_images_sorted

router = APIRouter(tags=["status"])


class HealthResponse(BaseModel):
    ok: bool
    display_ready: bool
    target_size: Tuple[int, int]
    image_count: int


class PreviewResponse(BaseModel):
    available: bool
    file: Optional[str] = None
    url: Optional[str] = None
    size: Optional[int] = None
    created_at: Optional[str] = None


@router.get("/health", response_model=HealthResponse)
async def health(state: AppState = Depends(get_app_state)) -> HealthResponse:
    files = list(list_images_sorted(state.image_dir))
    return HealthResponse(
        ok=True,
        display_ready=inky_display.is_ready(),
        target_size=inky_display.target_size(),
        image_count=len(files),
    )


@router.get("/preview", response_model=PreviewResponse)
async def preview(state: AppState = Depends(get_app_state)) -> PreviewResponse:
    files = list(list_images_sorted(state.image_dir))
    if not files:
        return PreviewResponse(available=False)
    latest = files[-1]
    description = describe_image(latest)
    return PreviewResponse(
        available=True,
        file=description["name"],
        url=description["url"],
        size=description["size"],
        created_at=description["created_at"],
    )
