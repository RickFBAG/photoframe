"""Factory helpers for creating widgets from configuration."""
from __future__ import annotations

from typing import Dict

from ..config import AppConfig
from .agenda import AgendaWidget
from .market import MarketWidget
from .news import NewsWidget
from .base import Widget


def build_widgets(config: AppConfig) -> Dict[str, Widget]:
    """Instantiate widgets for the supplied configuration."""

    widgets: Dict[str, Widget] = {
        "agenda": AgendaWidget(config.agenda),
        "news": NewsWidget(config.news),
        "market": MarketWidget(config.market),
    }
    return {key: widget for key, widget in widgets.items() if widget.enabled}


__all__ = ["build_widgets"]
