from __future__ import annotations

import io
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
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


class PreviewInfoResponse(BaseModel):
    available: bool
    file: Optional[str] = None
    url: Optional[str] = None
    size: Optional[int] = None
    created_at: Optional[str] = None
    generated_at: Optional[str] = None
    stale: bool = False
    cache: str = "miss"
    layout: str = "default"
    theme: str = "ink"


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
async def preview(
    layout: Optional[str] = Query(None, description="Layout naam voor de renderer"),
    theme: Optional[str] = Query(None, description="Thema voor de renderer"),
    state: AppState = Depends(get_app_state),
) -> StreamingResponse:
    result = state.preview_renderer.render(state.image_dir, layout=layout, theme=theme)
    headers = {
        "Cache-Control": "no-store",
        "X-Preview-Generated-At": result.iso_timestamp(),
        "X-Preview-Stale": "true" if result.stale else "false",
        "X-Preview-Cache": "hit" if result.cache_hit else "miss",
        "X-Preview-Layout": result.layout,
        "X-Preview-Theme": result.theme,
    }
    if result.source_meta and result.source_meta.get("name"):
        headers["X-Preview-Source"] = str(result.source_meta["name"])
    stream = io.BytesIO(result.image_bytes)
    stream.seek(0)
    return StreamingResponse(stream, media_type="image/png", headers=headers)


@router.get("/preview/meta", response_model=PreviewInfoResponse)
async def preview_meta(
    response: Response,
    layout: Optional[str] = Query(None, description="Layout naam voor de renderer"),
    theme: Optional[str] = Query(None, description="Thema voor de renderer"),
    state: AppState = Depends(get_app_state),
) -> PreviewInfoResponse:
    result = state.preview_renderer.render(state.image_dir, layout=layout, theme=theme)
    response.headers["Cache-Control"] = "no-store"
    meta = result.source_meta or {}
    return PreviewInfoResponse(
        available=bool(meta),
        file=str(meta.get("name")) if meta.get("name") else None,
        url=str(meta.get("url")) if meta.get("url") else None,
        size=int(meta.get("size")) if meta.get("size") is not None else None,
        created_at=str(meta.get("created_at")) if meta.get("created_at") else None,
        generated_at=result.iso_timestamp(),
        stale=result.stale,
        cache="hit" if result.cache_hit else "miss",
        layout=result.layout,
        theme=result.theme,
    )
