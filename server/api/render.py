from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from PIL import Image, ImageOps

from ..app import AppState, get_app_state
from ..config import deep_merge
from ..inky import display as inky_display
from ..widgets import WidgetError
from .dependencies import admin_guard

router = APIRouter(tags=["render"])


def _model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[no-any-return]
    return model.dict()  # type: ignore[no-any-return]


class RenderNowRequest(BaseModel):
    image: Optional[str] = Field(default=None, description="Naam van de afbeelding in de galerij")
    widget: Optional[str] = Field(default=None, description="Widget slug die gerenderd moet worden")
    config: Dict[str, Any] = Field(default_factory=dict, description="Configuratie voor de gekozen widget")
    dry_run: bool = Field(False, description="Voer geen daadwerkelijke render uit")


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
        if payload.image and payload.widget:
            raise ValueError("Kies óf een afbeelding óf een widget")

        if payload.image:
            path = _resolve_image(payload.image, state)
            image = _load_image(path)
            identifier = path.name
            source = "image"
        else:
            slug = payload.widget or state.runtime_config.widgets.default
            if not slug:
                raise ValueError("Geef een afbeelding of widget op")
            widget = state.widget_registry.get(slug)
            target_size = inky_display.target_size()
            runtime_overrides = state.runtime_config.widgets.overrides.get(widget.slug, {})
            base_overrides = dict(runtime_overrides) if isinstance(runtime_overrides, dict) else dict(runtime_overrides or {})
            widget_config = deep_merge(base_overrides, payload.config or {})
            widget_config["theme"] = _model_dump(state.runtime_config.theme)
            widget_config["layout"] = _model_dump(state.runtime_config.layout)
            image = widget.render(widget_config, target_size)
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
