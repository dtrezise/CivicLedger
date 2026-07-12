import json
from pathlib import Path

from app.services.fred_context import (
    CONTEXT_SOURCE_PRIORITIES,
    FRED_CONTEXT_SERIES,
    FRED_RELEASES,
    parse_observations,
    parse_release_dates,
)


FIXTURES = Path(__file__).parent / "fixtures" / "fred"


def test_parse_fred_observations_handles_missing_values():
    payload = json.loads((FIXTURES / "series_observations.json").read_text())
    observations = parse_observations(payload)

    assert observations[0].date == "2024-01-01"
    assert observations[0].value == 5.33
    assert observations[1].value is None


def test_parse_cpi_release_dates_as_context_events():
    payload = json.loads((FIXTURES / "release_dates.json").read_text())
    events = parse_release_dates(
        payload,
        label="Consumer Price Index Release",
        category="inflation_release",
    )

    assert events == [
        {
            "date": "2024-01-11",
            "label": "Consumer Price Index Release",
            "event_type": "macro_release",
            "category": "inflation_release",
            "release_id": 10,
            "source": "FRED",
            "context_note": "Context only - no inference of causation, intent, legality, ethics, or investment performance.",
        }
    ]


def test_context_source_priority_keeps_fred_active_and_defers_campaign_spending():
    by_source = {item["source"]: item for item in CONTEXT_SOURCE_PRIORITIES}

    assert by_source["FRED"]["status"] == "active"
    assert by_source["FEC"]["status"] == "deferred"
    assert by_source["USAspending"]["status"] == "deferred"
    assert {"FEDFUNDS", "CPIAUCSL", "DGS10", "DGS2", "UNRATE", "USREC"} <= set(FRED_CONTEXT_SERIES)
    assert {
        "cpi": 10,
        "employment_situation": 50,
        "gdp": 53,
        "fomc": 101,
    } == {key: value["release_id"] for key, value in FRED_RELEASES.items()}
