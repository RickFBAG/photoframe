from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RuntimeConfig(BaseModel):
    """Runtime configuration exposed via the API."""

    carousel_minutes: int = Field(5, ge=1, le=720, description="Interval in minutes between automatic renders")
    auto_rotate: bool = Field(False, description="Rotate rendered images 180 degrees before display")
    notes: Optional[str] = Field(default=None, max_length=500, description="Optional notes shown in the dashboard")
    default_widget: Optional[str] = Field(default=None, description="Widget slug rendered when no image is scheduled")


class RuntimeConfigUpdate(BaseModel):
    carousel_minutes: Optional[int] = Field(None, ge=1, le=720)
    auto_rotate: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    default_widget: Optional[str] = Field(default=None)


class ConfigResponse(BaseModel):
    config: RuntimeConfig
