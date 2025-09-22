"""API routers for the photoframe FastAPI application."""

from . import config, images, logs, render, status, uploads, weather, widgets

__all__ = [
    "config",
    "images",
    "logs",
    "render",
    "status",
    "uploads",
    "weather",
    "widgets",
]
