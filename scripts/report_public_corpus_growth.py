#!/usr/bin/env python3
"""Record deterministic weekly static-asset and public-partition growth."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from public_corpus_metrics import (
    CorpusMetricsError,
    public_artifact_summary,
    read_manifest,
    static_asset_summary,
    validated_manifest_artifacts,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = ROOT / "pages-site"
DEFAULT_OUTPUT = ROOT / "docs" / "metrics" / "public_corpus_growth_history.json"
SCHEMA_VERSION = "civicledger-public-corpus-growth-v1"


def _snapshot_date(manifest: dict, explicit_date: str | None) -> date:
    value = explicit_date or manifest.get("generated_at")
    if not isinstance(value, str):
        raise CorpusMetricsError("Use --as-of when the public manifest has no generated_at date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise CorpusMetricsError(f"Invalid snapshot date: {value}") from exc


def build_snapshot(site: Path, manifest_path: Path, as_of: str | None = None) -> dict:
    manifest = read_manifest(manifest_path)
    artifacts = validated_manifest_artifacts(manifest, manifest_path)
    observed_on = _snapshot_date(manifest, as_of)
    iso_year, iso_week, _ = observed_on.isocalendar()
    return {
        "delta_from_previous_week": None,
        "iso_week": f"{iso_year}-W{iso_week:02d}",
        "observed_on": observed_on.isoformat(),
        "public_artifacts": public_artifact_summary(artifacts),
        "source": {
            "dataset_version": manifest.get("dataset_version"),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
        "static_assets": static_asset_summary(site),
    }


def _delta(current: dict, previous: dict | None) -> dict | None:
    if previous is None:
        return None
    return {
        "declared_artifact_count": (
            current["public_artifacts"]["declared_artifact_count"]
            - previous["public_artifacts"]["declared_artifact_count"]
        ),
        "public_artifact_bytes": (
            current["public_artifacts"]["total_bytes"]
            - previous["public_artifacts"]["total_bytes"]
        ),
        "query_partition_count": (
            current["public_artifacts"]["query_partition_count"]
            - previous["public_artifacts"]["query_partition_count"]
        ),
        "static_asset_count": current["static_assets"]["asset_count"] - previous["static_assets"]["asset_count"],
        "static_asset_bytes": current["static_assets"]["total_bytes"] - previous["static_assets"]["total_bytes"],
    }


def update_history(existing: dict | None, snapshot: dict) -> dict:
    if existing is None:
        snapshots = []
    else:
        if existing.get("schema_version") != SCHEMA_VERSION or not isinstance(existing.get("snapshots"), list):
            raise CorpusMetricsError("Existing growth history has an unsupported schema")
        snapshots = existing["snapshots"]

    by_week = {item["iso_week"]: item for item in snapshots}
    by_week[snapshot["iso_week"]] = snapshot
    ordered = sorted(by_week.values(), key=lambda item: (item["observed_on"], item["iso_week"]))
    previous = None
    for item in ordered:
        item["delta_from_previous_week"] = _delta(item, previous)
        previous = item

    return {
        "methodology": {
            "clock_independent": True,
            "partition_scope": (
                "All unique bootstrap artifacts and query partitions declared by "
                "pages-site/data/manifest.json."
            ),
            "static_scope": "All regular files beneath pages-site; symlinks are rejected.",
            "week_rule": "ISO week containing observed_on; reruns replace that week and recompute deltas.",
        },
        "schema_version": SCHEMA_VERSION,
        "snapshots": ordered,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--as-of", help="ISO date; defaults to manifest generated_at")
    parser.add_argument("--json", action="store_true", help="Print the updated report")
    args = parser.parse_args()

    site = args.site.resolve()
    manifest_path = (args.manifest or site / "data" / "manifest.json").resolve()
    output = args.output.resolve()
    try:
        existing = json.loads(output.read_text()) if output.exists() else None
        report = update_history(existing, build_snapshot(site, manifest_path, args.as_of))
        write_json(output, report)
    except (OSError, json.JSONDecodeError, CorpusMetricsError) as exc:
        raise SystemExit(f"Public corpus growth report failed: {exc}") from exc

    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        current = report["snapshots"][-1]
        print(
            "Recorded public corpus growth snapshot: "
            f"week={current['iso_week']}, assets={current['static_assets']['asset_count']}, "
            f"partitions={current['public_artifacts']['query_partition_count']}, "
            f"bytes={current['static_assets']['total_bytes']}"
        )


if __name__ == "__main__":
    main()
