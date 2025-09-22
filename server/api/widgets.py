from __future__ import annotations

import base64
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from ..app import AppState, get_app_state
from ..inky import display as inky_display
from ..widgets import Surface, WidgetBase, WidgetError, WidgetField
from .dependencies import admin_guard

router = APIRouter(tags=["widgets"])


class WidgetFieldModel(BaseModel):
    name: str
    label: str
    field_type: str
    required: bool
    default: Any = None
    description: str | None = None

    @classmethod
    def from_definition(cls, field: WidgetField) -> "WidgetFieldModel":
        return cls(
            name=field.name,
            label=field.label,
            field_type=field.field_type,
            required=field.required,
            default=field.default,
            description=field.description,
        )


class WidgetInfo(BaseModel):
    slug: str
    name: str
    description: str
    fields: List[WidgetFieldModel]

    @classmethod
    def from_widget(cls, widget: WidgetBase) -> "WidgetInfo":
        field_models = [WidgetFieldModel.from_definition(field) for field in widget.fields]
        return cls(slug=widget.slug, name=widget.name, description=widget.description, fields=field_models)


class WidgetListResponse(BaseModel):
    widgets: List[WidgetInfo]


class WidgetTestRequest(BaseModel):
    config: Dict[str, Any] = Field(default_factory=dict)


class WidgetTestResponse(BaseModel):
    ok: bool
    preview: str
    content_type: str
    width: int
    height: int


@router.get("/widgets", response_model=WidgetListResponse)
async def list_widgets(state: AppState = Depends(get_app_state)) -> WidgetListResponse:
    widgets = [WidgetInfo.from_widget(widget) for widget in state.widget_registry.list()]
    return WidgetListResponse(widgets=widgets)


@router.post(
    "/widgets/{slug}/test",
    response_model=WidgetTestResponse,
    dependencies=[Depends(admin_guard)],
)
async def test_widget(
    slug: str = Path(..., description="Widget slug"),
    payload: Optional[WidgetTestRequest] = None,
    state: AppState = Depends(get_app_state),
) -> WidgetTestResponse:
    payload = payload or WidgetTestRequest()
    try:
        widget = state.widget_registry.get(slug)
    except WidgetError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    config = payload.config or {}
    data = await widget.fetch(config, state=state)
    surface = Surface(inky_display.target_size())
    image = widget.render(surface, data)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    preview = base64.b64encode(buffer.getvalue()).decode("ascii")

    return WidgetTestResponse(
        ok=True,
        preview=preview,
        content_type="image/png",
        width=image.width,
        height=image.height,
    )
