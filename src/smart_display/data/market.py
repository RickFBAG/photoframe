"""Market data provider for index snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import requests
from dateutil import tz

from ..config import MarketSettings


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    price: Optional[float]
    change: Optional[float]
    change_percent: Optional[float]
    currency: Optional[str]
    last_updated: Optional[datetime]
    history: List[float]


class MarketDataProvider:
    """Retrieve the latest market information for a ticker."""

    QUOTE_ENDPOINT = "https://query1.finance.yahoo.com/v7/finance/quote"
    CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def __init__(self, settings: MarketSettings) -> None:
        self.settings = settings

    def fetch(self) -> Optional[MarketSnapshot]:
        quote = self._fetch_quote()
        if quote is None:
            return None
        history = self._fetch_history()
        return MarketSnapshot(
            symbol=self.settings.symbol,
            price=quote.get("regularMarketPrice"),
            change=quote.get("regularMarketChange"),
            change_percent=quote.get("regularMarketChangePercent"),
            currency=quote.get("currency"),
            last_updated=self._parse_timestamp(quote.get("regularMarketTime")),
            history=history,
        )

    def _fetch_quote(self) -> Optional[dict]:
        try:
            response = requests.get(
                self.QUOTE_ENDPOINT,
                params={"symbols": self.settings.symbol},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException:
            return None

        payload = response.json().get("quoteResponse", {}).get("result", [])
        if not payload:
            return None
        return payload[0]

    def _fetch_history(self) -> List[float]:
        params = {
            "range": f"{max(self.settings.history_days, 1)}d",
            "interval": "1d",
            "includePrePost": "false",
        }
        try:
            response = requests.get(
                self.CHART_ENDPOINT.format(symbol=self.settings.symbol),
                params=params,
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException:
            return []

        try:
            result = response.json()["chart"]["result"][0]
            closes = result["indicators"]["quote"][0]["close"]
        except Exception:
            return []

        return [price for price in closes if isinstance(price, (int, float))]

    @staticmethod
    def _parse_timestamp(value: Optional[int]) -> Optional[datetime]:
        if value is None:
            return None
        return datetime.fromtimestamp(value, tz=tz.tzlocal())


__all__ = ["MarketDataProvider", "MarketSnapshot"]
