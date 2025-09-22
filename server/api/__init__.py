"""API routers for the photoframe FastAPI application."""

from . import config, logs, render, status, uploads, weather, widgets

__all__ = [
    "config",
    "logs",
    "render",
    "status",
    "uploads",
    "weather",
    "widgets",
]
