#!/usr/bin/env python3
"""Build immutable normalized snapshot metadata for contextual event sources."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.source_snapshots import build_snapshot_index  # noqa: E402


INPUTS = [
    ("federal_events", ROOT / "data" / "context" / "federal_events.json", "official"),
    ("sec_filing_events", ROOT / "data" / "context" / "sec_filing_events.json", "official"),
    ("historical_news_context", ROOT / "data" / "context" / "historical_news_context.json", "discovery"),
]
OUTPUT = ROOT / "data" / "context" / "source_snapshots.json"


def main() -> None:
    datasets = []
    for source_dataset, path, source_tier in INPUTS:
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        datasets.append(
            {
                "source_dataset": source_dataset,
                "source_tier": source_tier,
                "generated_at": payload.get("generated_at") or payload.get("artifact_date"),
                "events": payload.get("events", []),
            }
        )
    result = build_snapshot_index(datasets, as_of=date.today())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT} with {result['summary']['snapshot_count']} snapshots")


if __name__ == "__main__":
    main()
