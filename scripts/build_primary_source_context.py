#!/usr/bin/env python3
"""Compile deterministic official agency, court, Congress, and issuer context."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.historical_news import build_primary_source_context  # noqa: E402


FEDERAL_EVENTS = ROOT / "data" / "context" / "federal_events.json"
SEC_FILING_EVENTS = ROOT / "data" / "context" / "sec_filing_events.json"
OUTPUT = ROOT / "data" / "context" / "primary_source_context.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(source_id: str, path: Path, payload: dict) -> dict:
    return {
        "source_id": source_id,
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "artifact_date": payload.get("artifact_date"),
        "source_tier": "official",
    }


def build_dataset(
    *,
    federal_events_path: Path = FEDERAL_EVENTS,
    sec_filing_events_path: Path = SEC_FILING_EVENTS,
    artifact_date: str,
) -> dict:
    federal_events = _read_json(federal_events_path)
    sec_filing_events = _read_json(sec_filing_events_path)
    return build_primary_source_context(
        federal_events=federal_events,
        sec_filing_events=sec_filing_events,
        artifact_date=artifact_date,
        source_snapshots=[
            _snapshot("federal_events", federal_events_path, federal_events),
            _snapshot("sec_filing_events", sec_filing_events_path, sec_filing_events),
        ],
    )


def write_artifact(payload: dict, output: Path = OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-date", default=date.today().isoformat())
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    dataset = build_dataset(artifact_date=args.artifact_date)
    write_artifact(dataset, args.output)
    print(json.dumps({"output": str(args.output), **dataset["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
