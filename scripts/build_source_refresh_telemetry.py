#!/usr/bin/env python3
"""Build deterministic reviewer telemetry from explicit refresh records."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.reviewer_telemetry import (  # noqa: E402
    build_baseline,
    build_telemetry,
    snapshot_source,
)


OPERATIONS = ROOT / "data" / "operations"
RUNS = OPERATIONS / "source_refresh_runs.json"
BASELINE = OPERATIONS / "source_refresh_baseline.json"
OUTPUT = OPERATIONS / "source_refresh_telemetry.json"

SOURCE_SPECS = [
    (
        "house-disclosure-index",
        ROOT / "data" / "disclosures" / "house_disclosure_index.json",
        "source_index_row_count",
    ),
    (
        "house-ptr-transactions",
        ROOT / "data" / "disclosures" / "house_ptr_transactions.json",
        "processed_document_count",
    ),
    (
        "judicial-disclosure-manifest",
        ROOT / "data" / "disclosures" / "judicial_disclosure_manifest.json",
        "indexed_document_count",
    ),
    (
        "presidential-oge-documents",
        ROOT / "data" / "disclosures" / "presidential_oge_documents.json",
        "document_count",
    ),
    (
        "senate-disclosure-index",
        ROOT / "data" / "disclosures" / "senate_disclosure_index.json",
        "document_count",
    ),
    (
        "senate-ptr-transactions",
        ROOT / "data" / "disclosures" / "senate_ptr_transactions.json",
        "processed_document_count",
    ),
]

FAILURE_SPECS = [
    (
        "house-ptr-transactions",
        ROOT / "data" / "disclosures" / "house_ptr_transactions.json",
        "latest_batch_error_count",
    ),
    (
        "presidential-oge-documents",
        ROOT / "data" / "disclosures" / "presidential_oge_documents.json",
        "fetch_failure_count",
    ),
]


def read_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def record_run(
    *,
    run_id: str,
    source_id: str,
    status: str,
    started_at: str,
    completed_at: str,
    failure_count: int,
) -> None:
    payload = read_json(RUNS, {"schema_version": "source-refresh-runs-v1", "runs": []})
    rows = [row for row in payload.get("runs", []) if row.get("run_id") != run_id]
    rows.append(
        {
            "run_id": run_id,
            "source_id": source_id,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "failure_count": max(0, failure_count),
        }
    )
    rows.sort(key=lambda row: (str(row.get("started_at") or ""), str(row.get("run_id") or "")))
    write_json(
        RUNS,
        {
            "schema_version": "source-refresh-runs-v1",
            "interpretation_boundary": (
                "Operational workflow timing only. Run history contains no disclosure evidence "
                "and makes no claim about officials, trades, or events."
            ),
            "runs": rows[-200:],
        },
    )


def current_snapshots() -> list[dict]:
    snapshots = []
    for source_id, path, count_metric in SOURCE_SPECS:
        if not path.exists():
            continue
        snapshots.append(
            snapshot_source(
                source_id=source_id,
                path=str(path.relative_to(ROOT)),
                payload=read_json(path, {}),
                count_metric=count_metric,
            )
        )
    return snapshots


def failure_observations() -> list[dict]:
    observations = []
    for source_id, path, metric in FAILURE_SPECS:
        payload = read_json(path, {"summary": {}})
        observations.append(
            {
                "source_id": source_id,
                "source_artifact": str(path.relative_to(ROOT)),
                "metric": metric,
                "failure_count": payload.get("summary", {}).get(metric, 0),
            }
        )
    return observations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-baseline", action="store_true")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--record-run-id")
    parser.add_argument("--source-id", default="scheduled-live-refresh")
    parser.add_argument("--status", choices=("success", "failed", "cancelled"), default="success")
    parser.add_argument("--started-at")
    parser.add_argument("--completed-at")
    parser.add_argument("--failure-count", type=int, default=0)
    args = parser.parse_args()

    if args.record_run_id:
        if not args.started_at or not args.completed_at:
            parser.error("--record-run-id requires --started-at and --completed-at")
        record_run(
            run_id=args.record_run_id,
            source_id=args.source_id,
            status=args.status,
            started_at=args.started_at,
            completed_at=args.completed_at,
            failure_count=args.failure_count,
        )

    snapshots = current_snapshots()
    if args.capture_baseline:
        write_json(
            BASELINE,
            build_baseline(snapshots, captured_at=args.as_of),
        )

    baseline = read_json(BASELINE, {"sources": []})
    run_log = read_json(RUNS, {"runs": []})
    result = build_telemetry(
        runs=run_log.get("runs", []),
        current_snapshots=snapshots,
        baseline=baseline,
        failure_observations=failure_observations(),
        generated_at=args.as_of,
    )
    write_json(OUTPUT, result)
    print(
        f"Wrote {OUTPUT} with {result['summary']['data_drift_count']} drift signal(s)"
    )


if __name__ == "__main__":
    main()
