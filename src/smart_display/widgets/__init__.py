"""Widget implementations for the Smart Display."""

from .agenda import AgendaWidget
from .market import MarketWidget
from .news import NewsWidget
from .base import WidgetContext, Widget

__all__ = [
    "AgendaWidget",
    "MarketWidget",
    "NewsWidget",
    "WidgetContext",
    "Widget",
]
