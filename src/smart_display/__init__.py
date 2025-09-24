"""Smart Display package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from .app import SmartDisplayApp as _SmartDisplayApp

__all__ = ["SmartDisplayApp"]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin re-export shim
    if name == "SmartDisplayApp":
        from .app import SmartDisplayApp

        return SmartDisplayApp
    raise AttributeError(name)


def __dir__() -> list[str]:  # pragma: no cover - thin re-export shim
    return sorted(__all__)
