"""Web configuration server package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover - imported only for typing
    from ..config import ConfigManager, WebSettings

__all__ = ["create_app", "launch_config_server"]


def create_app(
    config_manager: "ConfigManager",
    refresh_callback: Optional[Callable[[], None]] = None,
):
    from .server import create_app as _create_app

    return _create_app(config_manager, refresh_callback=refresh_callback)


def launch_config_server(
    settings: "WebSettings",
    config_manager: "ConfigManager",
    refresh_callback: Optional[Callable[[], None]] = None,
):
    from .server import launch_config_server as _launch_config_server

    return _launch_config_server(
        settings, config_manager, refresh_callback=refresh_callback
    )
