from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, root_validator

from ..app import AppState, get_app_state
from ..inky import display as inky_display
from ..widgets import WidgetError
from .dependencies import admin_guard
from ..renderer import PipelineRequest

router = APIRouter(tags=["render"])


class RenderNowRequest(BaseModel):
    image: Optional[str] = Field(default=None, description="Naam van de afbeelding in de galerij")
    widget: Optional[str] = Field(default=None, description="Widget slug die gerenderd moet worden")
    config: Dict[str, Any] = Field(default_factory=dict, description="Configuratie voor de gekozen widget")
    dry_run: bool = Field(False, description="Voer geen daadwerkelijke render uit")
    layout: str = Field("single", description="Naam van de lay-out preset")
    theme: str = Field("light", description="Naam van het kleurenthema")
    palette: str = Field("7", description="E-ink palet (3/4/7/8 kleuren)")
    dither: str = Field("floyd-steinberg", description="Dither methode (atkinson/floyd-steinberg/none)")
    separators: bool = Field(True, description="Toon scheidingslijnen in de lay-out")

    @root_validator
    def _validate_choice(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        image = values.get("image")
        widget = values.get("widget")
        if not image and not widget:
            raise ValueError("Geef een afbeelding of widget op")
        if image and widget:
            raise ValueError("Kies óf een afbeelding óf een widget")
        return values


def _resolve_image(name: str, state: AppState) -> Path:
    safe_name = os.path.basename(unquote(name))
    path = state.image_dir / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Afbeelding niet gevonden")
    return path


@router.post("/render/now", dependencies=[Depends(admin_guard)])
async def render_now(
    payload: RenderNowRequest,
    state: AppState = Depends(get_app_state),
) -> FileResponse:
    if not payload.dry_run and not inky_display.is_ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Display niet beschikbaar")

    try:
        if payload.image:
            _resolve_image(payload.image, state)
            source = "image"
            identifier = payload.image
        else:
            identifier = payload.widget or ""
            state.widget_registry.get(identifier)
            source = "widget"

        request = PipelineRequest(
            source=source,
            identifier=identifier,
            config=payload.config,
            layout=payload.layout,
            theme=payload.theme,
            palette=payload.palette,
            dither=payload.dither,
            separators=payload.separators,
        )
        result = state.renderer.render(request, state.widget_registry)
    except WidgetError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not payload.dry_run:
        inky_display.display_image(result.image)
        state.last_rendered = result.output_path.name

    headers = {
        "X-Render-Source": source,
        "X-Render-Identifier": identifier,
        "X-Render-Layout": payload.layout,
        "X-Render-Theme": result.theme.name,
        "X-Render-Cache": "hit" if result.from_cache else "miss",
        "X-Render-Dry-Run": "1" if payload.dry_run else "0",
        "Cache-Control": "no-store",
    }

    return FileResponse(
        path=str(result.output_path),
        media_type="image/png",
        filename=result.output_path.name,
        headers=headers,
    )
