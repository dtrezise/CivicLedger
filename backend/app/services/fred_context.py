from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings


FRED_BASE_URL = "https://api.stlouisfed.org/fred"
USER_AGENT = "CivicLedger data refresh"

FRED_CONTEXT_SERIES = {
    "FEDFUNDS": {
        "label": "Effective Federal Funds Rate",
        "category": "fed_policy",
        "units": "Percent",
        "context_use": "Rate backdrop for broad market conditions around trade and report dates.",
    },
    "CPIAUCSL": {
        "label": "Consumer Price Index for All Urban Consumers",
        "category": "inflation",
        "units": "Index 1982-1984=100",
        "context_use": "Inflation backdrop and CPI release-event context.",
    },
    "DGS10": {
        "label": "10-Year Treasury Constant Maturity Rate",
        "category": "treasury_yield",
        "units": "Percent",
        "context_use": "Interest-rate backdrop for equity valuation and sector-sensitive trades.",
    },
    "DGS2": {
        "label": "2-Year Treasury Constant Maturity Rate",
        "category": "treasury_yield",
        "units": "Percent",
        "context_use": "Shorter-term rate backdrop for market context.",
    },
    "UNRATE": {
        "label": "Unemployment Rate",
        "category": "labor",
        "units": "Percent",
        "context_use": "Labor-market backdrop around market-moving macro releases.",
    },
    "USREC": {
        "label": "NBER Recession Indicator",
        "category": "recession",
        "units": "0 or 1",
        "context_use": "Recession-regime context only.",
    },
}

FRED_RELEASES = {
    "cpi": {
        "release_id": 10,
        "label": "Consumer Price Index Release",
        "category": "inflation_release",
        "context_use": "CPI publication date near reported trades.",
    },
}

CONTEXT_SOURCE_PRIORITIES = [
    {
        "source": "FRED",
        "status": "active",
        "priority": 1,
        "reason": "Directly supports neutral macro, rates, inflation, and recession context for stock-market trade timelines.",
    },
    {
        "source": "Treasury Fiscal Data",
        "status": "watchlist",
        "priority": 2,
        "reason": "Potentially useful for rates and fiscal events, but FRED covers the first-pass market context need.",
    },
    {
        "source": "BLS",
        "status": "watchlist",
        "priority": 3,
        "reason": "Useful for labor and inflation release validation after the FRED macro layer is working.",
    },
    {
        "source": "FEC",
        "status": "deferred",
        "priority": 4,
        "reason": "Campaign finance is politically relevant but not directly tied to public officials' stock trades.",
    },
    {
        "source": "USAspending",
        "status": "deferred",
        "priority": 5,
        "reason": "Potentially valuable after ticker-to-company-to-award-recipient entity matching exists.",
    },
]


@dataclass(frozen=True)
class FredObservation:
    date: str
    value: float | None
    realtime_start: str | None = None
    realtime_end: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def parse_fred_value(value: str | None) -> float | None:
    if value in {None, "."}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_observations(payload: dict) -> list[FredObservation]:
    return [
        FredObservation(
            date=row["date"],
            value=parse_fred_value(row.get("value")),
            realtime_start=row.get("realtime_start"),
            realtime_end=row.get("realtime_end"),
        )
        for row in payload.get("observations", [])
    ]


def parse_release_dates(payload: dict, *, label: str, category: str) -> list[dict]:
    return [
        {
            "date": row["date"],
            "label": label,
            "event_type": "macro_release",
            "category": category,
            "release_id": row.get("release_id"),
            "source": "FRED",
            "context_note": "Context only - no inference of causation, intent, legality, ethics, or investment performance.",
        }
        for row in payload.get("release_dates", [])
    ]


class FredClient:
    def __init__(self, api_key: str | None = None, base_url: str = FRED_BASE_URL) -> None:
        self.api_key = api_key or settings.FRED_API_KEY
        self.base_url = base_url.rstrip("/")

    def _get_json(self, endpoint: str, params: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("FRED_API_KEY is required for live FRED context refreshes")
        query = urlencode({**params, "api_key": self.api_key, "file_type": "json"})
        request = Request(f"{self.base_url}/{endpoint}?{query}", headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=45) as response:
            import json

            return json.loads(response.read().decode("utf-8"))

    def series_observations(
        self,
        series_id: str,
        *,
        observation_start: str,
        observation_end: str,
        limit: int = 100000,
    ) -> list[FredObservation]:
        payload = self._get_json(
            "series/observations",
            {
                "series_id": series_id,
                "observation_start": observation_start,
                "observation_end": observation_end,
                "limit": limit,
            },
        )
        return parse_observations(payload)

    def release_dates(
        self,
        release_id: int,
        *,
        realtime_start: str,
        realtime_end: str,
        limit: int = 1000,
    ) -> list[dict]:
        return self._get_json(
            "release/dates",
            {
                "release_id": release_id,
                "realtime_start": realtime_start,
                "realtime_end": realtime_end,
                "limit": limit,
            },
        ).get("release_dates", [])
