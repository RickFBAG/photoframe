from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
_TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


class DeviceConfig(BaseModel):
    """Settings that influence the hardware scheduler and display."""

    carousel_minutes: int = Field(
        5,
        ge=1,
        le=720,
        description="Interval in minutes between automatic renders",
    )
    auto_rotate: bool = Field(
        False,
        description="Rotate rendered images 180 degrees before display",
    )
    sleep_start: Optional[str] = Field(
        default=None,
        regex=_TIME_PATTERN,
        description="Optional 24u starttijd voor de nachtstand (HH:MM)",
    )
    sleep_end: Optional[str] = Field(
        default=None,
        regex=_TIME_PATTERN,
        description="Optionele 24u eindtijd voor de nachtstand (HH:MM)",
    )


class LayoutConfig(BaseModel):
    """Controls layout/renderer behaviour."""

    orientation: Literal["landscape", "portrait", "auto"] = Field(
        "auto",
        description="Geef weer of renders automatisch draaien of een vaste orientatie gebruiken",
    )
    margin: int = Field(
        24,
        ge=0,
        le=200,
        description="Witruimte in pixels rondom widgets bij renderen",
    )
    show_notes: bool = Field(
        True,
        description="Toon runtime notities op het dashboard",
    )


class ThemeConfig(BaseModel):
    """Visual appearance applied to renders and dashboard widgets."""

    name: str = Field("classic", description="Naam van het actieve kleurenthema")
    background: str = Field(
        "#FFFFFF",
        regex=_HEX_COLOR_PATTERN,
        description="Achtergrondkleur voor renders (hex)",
    )
    foreground: str = Field(
        "#000000",
        regex=_HEX_COLOR_PATTERN,
        description="Primaire tekstkleur (hex)",
    )
    accent: str = Field(
        "#D81B60",
        regex=_HEX_COLOR_PATTERN,
        description="Accentkleur voor belangrijke elementen (hex)",
    )


class WidgetOptions(BaseModel):
    """Widget voorkeuren en overrides."""

    default: Optional[str] = Field(
        default=None,
        description="Widget slug die getoond wordt wanneer er niets gepland is",
    )
    overrides: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Configuratie-overrides per widget (slug -> instellingen)",
    )


class RuntimeConfig(BaseModel):
    """Runtime configuration exposed via the API."""

    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optionele notities getoond in het dashboard",
    )
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    layout: LayoutConfig = Field(default_factory=LayoutConfig)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    widgets: WidgetOptions = Field(default_factory=WidgetOptions)


class DeviceConfigUpdate(BaseModel):
    carousel_minutes: Optional[int] = Field(None, ge=1, le=720)
    auto_rotate: Optional[bool] = None
    sleep_start: Optional[str] = Field(default=None, regex=_TIME_PATTERN)
    sleep_end: Optional[str] = Field(default=None, regex=_TIME_PATTERN)


class LayoutConfigUpdate(BaseModel):
    orientation: Optional[Literal["landscape", "portrait", "auto"]] = None
    margin: Optional[int] = Field(None, ge=0, le=200)
    show_notes: Optional[bool] = None


class ThemeConfigUpdate(BaseModel):
    name: Optional[str] = None
    background: Optional[str] = Field(default=None, regex=_HEX_COLOR_PATTERN)
    foreground: Optional[str] = Field(default=None, regex=_HEX_COLOR_PATTERN)
    accent: Optional[str] = Field(default=None, regex=_HEX_COLOR_PATTERN)


class WidgetOptionsUpdate(BaseModel):
    default: Optional[str] = Field(default=None)
    overrides: Optional[Dict[str, Dict[str, Any]]] = None


class RuntimeConfigUpdate(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)
    device: Optional[DeviceConfigUpdate] = None
    layout: Optional[LayoutConfigUpdate] = None
    theme: Optional[ThemeConfigUpdate] = None
    widgets: Optional[WidgetOptionsUpdate] = None


class ConfigResponse(BaseModel):
    config: RuntimeConfig
