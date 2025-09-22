from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from ..app import AppState, get_app_state
from ..config import ConfigError, ConfigValidationError, deep_merge
from ..models import ConfigResponse, RuntimeConfig, RuntimeConfigUpdate
from .dependencies import admin_guard

router = APIRouter(tags=["config"])


def _model_dump(model: Any, **kwargs: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)  # type: ignore[no-any-return]
    return model.dict(**kwargs)  # type: ignore[no-any-return]


@router.get("/config", response_model=ConfigResponse, dependencies=[Depends(admin_guard)])
async def get_config(state: AppState = Depends(get_app_state)) -> ConfigResponse:
    return ConfigResponse(config=state.runtime_config)


@router.put("/config", response_model=ConfigResponse, dependencies=[Depends(admin_guard)])
async def update_config(
    payload: RuntimeConfigUpdate,
    state: AppState = Depends(get_app_state),
) -> ConfigResponse:
    current = state.runtime_config
    current_data = _model_dump(current)
    update_data = _model_dump(payload, exclude_unset=True)
    merged = deep_merge(current_data, update_data)

    try:
        new_config = RuntimeConfig(**merged)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc

    default_widget = new_config.widgets.default
    if default_widget and default_widget not in state.widget_registry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onbekende widget")

    try:
        state.set_runtime_config(new_config)
    except (ConfigError, ConfigValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return ConfigResponse(config=new_config)
