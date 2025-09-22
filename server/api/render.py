from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, root_validator
from PIL import Image, ImageOps

from ..app import AppState, get_app_state
from ..inky import display as inky_display
from ..widgets import Surface, WidgetError
from .dependencies import admin_guard

router = APIRouter(tags=["render"])


class RenderNowRequest(BaseModel):
    image: Optional[str] = Field(default=None, description="Naam van de afbeelding in de galerij")
    widget: Optional[str] = Field(default=None, description="Widget slug die gerenderd moet worden")
    config: Dict[str, Any] = Field(default_factory=dict, description="Configuratie voor de gekozen widget")
    dry_run: bool = Field(False, description="Voer geen daadwerkelijke render uit")

    @root_validator
    def _validate_choice(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        image = values.get("image")
        widget = values.get("widget")
        if not image and not widget:
            raise ValueError("Geef een afbeelding of widget op")
        if image and widget:
            raise ValueError("Kies óf een afbeelding óf een widget")
        return values


class RenderNowResponse(BaseModel):
    ok: bool
    source: str
    identifier: str
    dry_run: bool


def _resolve_image(name: str, state: AppState) -> Path:
    safe_name = os.path.basename(unquote(name))
    path = state.image_dir / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Afbeelding niet gevonden")
    return path


def _load_image(path: Path) -> Image.Image:
    with open(path, "rb") as handle:
        image = Image.open(handle)
        image = ImageOps.exif_transpose(image).convert("RGB")
    return image


@router.post("/render/now", response_model=RenderNowResponse, dependencies=[Depends(admin_guard)])
async def render_now(
    payload: RenderNowRequest,
    state: AppState = Depends(get_app_state),
) -> RenderNowResponse:
    if not payload.dry_run and not inky_display.is_ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Display niet beschikbaar")

    try:
        if payload.image:
            path = _resolve_image(payload.image, state)
            image = _load_image(path)
            identifier = path.name
            source = "image"
        else:
            widget = state.widget_registry.get(payload.widget or "")
            target_size = inky_display.target_size()
            data = await widget.fetch(payload.config or {}, state=state)
            surface = Surface(target_size)
            image = widget.render(surface, data)
            identifier = widget.slug
            source = "widget"
    except WidgetError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not payload.dry_run:
        inky_display.display_image(image)
        state.last_rendered = identifier

    return RenderNowResponse(ok=True, source=source, identifier=identifier, dry_run=payload.dry_run)
