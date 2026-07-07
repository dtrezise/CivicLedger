from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings


TIINGO_BASE_URL = "https://api.tiingo.com/tiingo/daily"
USER_AGENT = "CivicLedger data refresh"

MARKET_PRICE_SYMBOLS = ["SPY", "QQQ", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI"]


@dataclass(frozen=True)
class MarketPricePoint:
    symbol: str
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    adj_open: float | None
    adj_high: float | None
    adj_low: float | None
    adj_close: float | None
    adj_volume: int | None
    div_cash: float | None
    split_factor: float | None
    source: str = "tiingo"

    def as_dict(self) -> dict:
        return asdict(self)


def parse_tiingo_price_row(symbol: str, row: dict) -> MarketPricePoint:
    return MarketPricePoint(
        symbol=symbol.upper(),
        date=row["date"][:10],
        open=row.get("open"),
        high=row.get("high"),
        low=row.get("low"),
        close=row.get("close"),
        volume=row.get("volume"),
        adj_open=row.get("adjOpen"),
        adj_high=row.get("adjHigh"),
        adj_low=row.get("adjLow"),
        adj_close=row.get("adjClose"),
        adj_volume=row.get("adjVolume"),
        div_cash=row.get("divCash"),
        split_factor=row.get("splitFactor"),
    )


def parse_tiingo_prices(symbol: str, payload: list[dict]) -> list[MarketPricePoint]:
    return [parse_tiingo_price_row(symbol, row) for row in payload]


class TiingoClient:
    def __init__(self, api_key: str | None = None, base_url: str = TIINGO_BASE_URL) -> None:
        self.api_key = api_key or settings.TIINGO_API_KEY
        self.base_url = base_url.rstrip("/")

    def historical_prices(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[MarketPricePoint]:
        if not self.api_key:
            raise RuntimeError("TIINGO_API_KEY is required for live market price refreshes")
        query = urlencode(
            {
                "startDate": start_date,
                "endDate": end_date,
                "token": self.api_key,
            }
        )
        request = Request(
            f"{self.base_url}/{symbol.lower()}/prices?{query}",
            headers={"User-Agent": USER_AGENT},
        )
        with urlopen(request, timeout=45) as response:
            import json

            return parse_tiingo_prices(symbol, json.loads(response.read().decode("utf-8")))
