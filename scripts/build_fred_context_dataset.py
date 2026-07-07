#!/usr/bin/env python3
"""Build FRED macro context for trade-timeline overlays."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.fred_context import (  # noqa: E402
    CONTEXT_SOURCE_PRIORITIES,
    FRED_CONTEXT_SERIES,
    FRED_RELEASES,
    FredClient,
    parse_release_dates,
)


OUTPUT = ROOT / "data" / "context" / "fred_market_context.json"
DEFAULT_START = "2023-01-01"


def build_dataset(api_key: str | None, start: str, end: str) -> dict:
    client = FredClient(api_key=api_key)
    series = {}
    for series_id, metadata in FRED_CONTEXT_SERIES.items():
        observations = client.series_observations(
            series_id,
            observation_start=start,
            observation_end=end,
        )
        series[series_id] = {
            **metadata,
            "series_id": series_id,
            "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
            "observations": [observation.as_dict() for observation in observations],
        }

    release_events = []
    for release_key, release in FRED_RELEASES.items():
        payload = {
            "release_dates": client.release_dates(
                release["release_id"],
                realtime_start=start,
                realtime_end=end,
            )
        }
        events = parse_release_dates(
            payload,
            label=release["label"],
            category=release["category"],
        )
        for event in events:
            event["release_key"] = release_key
            event["context_use"] = release["context_use"]
            event["source_url"] = (
                "https://fred.stlouisfed.org/releases/calendar?rid="
                f"{release['release_id']}"
            )
        release_events.extend(events)

    return {
        "generated_at": date.today().isoformat(),
        "source": {
            "id": "fred",
            "name": "Federal Reserve Economic Data",
            "url": "https://fred.stlouisfed.org/docs/api/fred/",
            "source_tier": "official",
        },
        "scope": {
            "description": (
                "Macroeconomic context for public-official stock-trade timelines. "
                "These overlays are contextual only and do not imply causation, "
                "intent, legality, ethics, or investment performance."
            ),
            "observation_start": start,
            "observation_end": end,
        },
        "summary": {
            "series_count": len(series),
            "observation_count": sum(len(item["observations"]) for item in series.values()),
            "release_event_count": len(release_events),
            "active_context_source": "FRED",
            "deferred_sources": [
                item["source"] for item in CONTEXT_SOURCE_PRIORITIES if item["status"] == "deferred"
            ],
        },
        "series": series,
        "release_events": sorted(release_events, key=lambda event: event["date"]),
        "source_priorities": CONTEXT_SOURCE_PRIORITIES,
        "context_label": "Context only - no inference of causation, intent, legality, ethics, or investment performance.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.environ.get("FRED_API_KEY"))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=date.today().isoformat())
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("Set FRED_API_KEY or pass --api-key to refresh FRED context data.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(args.api_key, args.start, args.end), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
