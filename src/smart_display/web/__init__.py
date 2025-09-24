"""Web configuration server package."""

from .server import create_app, launch_config_server

__all__ = ["create_app", "launch_config_server"]
