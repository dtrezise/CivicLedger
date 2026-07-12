"""Deterministic reviewer telemetry derived from explicit operational records."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import math
from typing import Any


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _summary_hash(summary: dict[str, Any]) -> str:
    canonical = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def snapshot_source(
    *,
    source_id: str,
    path: str,
    payload: dict[str, Any],
    count_metric: str,
) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    count = summary.get(count_metric)
    return {
        "source_id": source_id,
        "path": path,
        "schema_version": payload.get("schema_version"),
        "count_metric": count_metric,
        "record_count": count if isinstance(count, int) else None,
        "summary_sha256": _summary_hash(summary),
    }


def build_baseline(
    snapshots: list[dict[str, Any]], *, captured_at: str
) -> dict[str, Any]:
    return {
        "schema_version": "source-refresh-baseline-v1",
        "captured_at": captured_at,
        "interpretation_boundary": (
            "Aggregate source-summary baseline for change detection only. It does not "
            "copy disclosure evidence or determine data correctness."
        ),
        "sources": sorted(snapshots, key=lambda row: row["source_id"]),
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def _duration_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        started_at = _parse_timestamp(run.get("started_at"))
        completed_at = _parse_timestamp(run.get("completed_at"))
        duration_seconds = None
        if started_at and completed_at:
            duration_seconds = round(
                max(0.0, (completed_at - started_at).total_seconds()), 3
            )
        rows.append(
            {
                "run_id": str(run.get("run_id") or ""),
                "source_id": str(run.get("source_id") or "unknown"),
                "status": str(run.get("status") or "unknown"),
                "started_at": run.get("started_at"),
                "completed_at": run.get("completed_at"),
                "duration_seconds": duration_seconds,
                "failure_count": int(run.get("failure_count") or 0),
            }
        )
    return sorted(rows, key=lambda row: (row["source_id"], row["run_id"]))


def build_telemetry(
    *,
    runs: list[dict[str, Any]],
    current_snapshots: list[dict[str, Any]],
    baseline: dict[str, Any],
    failure_observations: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    duration_runs = _duration_rows(runs)
    measured_durations = [
        row["duration_seconds"]
        for row in duration_runs
        if row["duration_seconds"] is not None
    ]

    source_failures = [
        {
            "source_id": str(observation["source_id"]),
            "source_artifact": str(observation["source_artifact"]),
            "metric": str(observation["metric"]),
            "failure_count": int(observation["failure_count"]),
        }
        for observation in failure_observations
        if int(observation.get("failure_count") or 0) > 0
    ]
    source_failures.extend(
        {
            "source_id": row["source_id"],
            "source_artifact": "source_refresh_runs.json",
            "metric": "recorded_run_failure_count",
            "failure_count": max(
                row["failure_count"], 1 if row["status"] == "failed" else 0
            ),
        }
        for row in duration_runs
        if row["status"] == "failed" or row["failure_count"] > 0
    )
    source_failures.sort(
        key=lambda row: (row["source_id"], row["source_artifact"], row["metric"])
    )

    baseline_by_source = {
        row["source_id"]: row for row in baseline.get("sources", [])
    }
    current_by_source = {row["source_id"]: row for row in current_snapshots}
    drift_rows = []
    for source_id in sorted(set(baseline_by_source) | set(current_by_source)):
        expected = baseline_by_source.get(source_id)
        current = current_by_source.get(source_id)
        if expected is None:
            drift_status = "baseline_missing"
        elif current is None:
            drift_status = "source_missing"
        elif (
            expected.get("schema_version") != current.get("schema_version")
            or expected.get("summary_sha256") != current.get("summary_sha256")
        ):
            drift_status = "changed"
        else:
            drift_status = "unchanged"
        drift_rows.append(
            {
                "source_id": source_id,
                "path": (current or expected or {}).get("path", ""),
                "status": drift_status,
                "baseline_schema_version": (
                    expected.get("schema_version") if expected else None
                ),
                "current_schema_version": (
                    current.get("schema_version") if current else None
                ),
                "count_metric": (current or expected or {}).get("count_metric", ""),
                "baseline_record_count": (
                    expected.get("record_count") if expected else None
                ),
                "current_record_count": (
                    current.get("record_count") if current else None
                ),
                "baseline_summary_sha256": (
                    expected.get("summary_sha256") if expected else None
                ),
                "current_summary_sha256": (
                    current.get("summary_sha256") if current else None
                ),
            }
        )

    drift_count = sum(row["status"] != "unchanged" for row in drift_rows)
    failure_count = sum(row["failure_count"] for row in source_failures)
    if failure_count or drift_count:
        status = "attention"
    elif not measured_durations:
        status = "instrumentation_pending"
    else:
        status = "healthy"

    return {
        "schema_version": "reviewer-source-telemetry-v1",
        "generated_at": generated_at,
        "status": status,
        "interpretation_boundary": (
            "Operational source-refresh signals only. Failures and aggregate drift are "
            "review queues, not evidence about an official, trade, or event."
        ),
        "summary": {
            "refresh_run_count": len(duration_runs),
            "measured_refresh_count": len(measured_durations),
            "failed_refresh_count": sum(
                row["status"] == "failed" for row in duration_runs
            ),
            "source_failure_count": failure_count,
            "data_drift_count": drift_count,
        },
        "refresh_duration": {
            "unit": "seconds",
            "p50": _percentile(measured_durations, 0.5),
            "p95": _percentile(measured_durations, 0.95),
            "maximum": max(measured_durations) if measured_durations else None,
            "runs": duration_runs,
        },
        "source_failures": source_failures,
        "data_drift": drift_rows,
    }
