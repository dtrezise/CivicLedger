#!/usr/bin/env python3
"""Simulate which public query partitions would merit R2 without using R2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from public_corpus_metrics import (
    CorpusMetricsError,
    read_manifest,
    static_asset_summary,
    validated_manifest_artifacts,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = ROOT / "pages-site"
DEFAULT_OUTPUT = ROOT / "docs" / "metrics" / "r2_public_partition_migration_simulation.json"
MIB = 1024 * 1024
DEFAULT_CANDIDATE_BYTES = 2 * MIB
DEFAULT_PRIORITY_BYTES = 10 * MIB
DEFAULT_ACTIVATION_ASSET_COUNT = 15_000
DEFAULT_ACTIVATION_TOTAL_BYTES = 500 * MIB
DEFAULT_ACTIVATION_INDIVIDUAL_BYTES = 20 * MIB


def _candidate_record(artifact: dict, priority_bytes: int) -> dict:
    return {
        "bytes": artifact["bytes"],
        "group": artifact["group"],
        "key": artifact["key"],
        "path": f"data/{artifact['path']}",
        "rationale": "Query partition meets the migration-candidate byte threshold.",
        "tier": "priority" if artifact["bytes"] >= priority_bytes else "candidate",
    }


def _activation_gate(current: int, threshold: int, rationale: str) -> dict:
    return {
        "current": current,
        "rationale": rationale,
        "threshold": threshold,
        "triggered_now": current >= threshold,
    }


def build_simulation(
    site: Path,
    manifest_path: Path,
    *,
    candidate_bytes: int = DEFAULT_CANDIDATE_BYTES,
    priority_bytes: int = DEFAULT_PRIORITY_BYTES,
    activation_asset_count: int = DEFAULT_ACTIVATION_ASSET_COUNT,
    activation_total_bytes: int = DEFAULT_ACTIVATION_TOTAL_BYTES,
    activation_individual_bytes: int = DEFAULT_ACTIVATION_INDIVIDUAL_BYTES,
) -> dict:
    if min(
        candidate_bytes,
        priority_bytes,
        activation_asset_count,
        activation_total_bytes,
        activation_individual_bytes,
    ) <= 0:
        raise CorpusMetricsError("All simulation thresholds must be positive")
    if priority_bytes < candidate_bytes:
        raise CorpusMetricsError("Priority threshold cannot be smaller than candidate threshold")

    manifest = read_manifest(manifest_path)
    artifacts = validated_manifest_artifacts(manifest, manifest_path)
    static = static_asset_summary(site)
    query_partitions = [item for item in artifacts if item["kind"] == "query_partition"]
    bootstrap = [item for item in artifacts if item["kind"] == "bootstrap"]

    candidates = [
        _candidate_record(item, priority_bytes)
        for item in query_partitions
        if item["bytes"] >= candidate_bytes
    ]
    candidates.sort(key=lambda item: (-item["bytes"], item["path"]))
    candidate_total_bytes = sum(item["bytes"] for item in candidates)

    group_summary = {}
    for group in sorted({item["group"] for item in query_partitions}):
        group_partitions = [item for item in query_partitions if item["group"] == group]
        group_candidates = [item for item in candidates if item["group"] == group]
        group_summary[group] = {
            "candidate_bytes": sum(item["bytes"] for item in group_candidates),
            "candidate_count": len(group_candidates),
            "partition_count": len(group_partitions),
            "total_bytes": sum(item["bytes"] for item in group_partitions),
        }

    activation_gates = {
        "asset_count": _activation_gate(
            static["asset_count"],
            activation_asset_count,
            "Provides an early review point below the Workers Static Assets asset-count hard limit.",
        ),
        "individual_asset_bytes": _activation_gate(
            static["largest_asset"]["bytes"],
            activation_individual_bytes,
            "Provides an early review point below the Workers Static Assets per-file hard limit.",
        ),
        "total_static_bytes": _activation_gate(
            static["total_bytes"],
            activation_total_bytes,
            "Marks the documented point where deploy and checkout weight require review.",
        ),
    }
    triggered_gates = sorted(name for name, gate in activation_gates.items() if gate["triggered_now"])

    large_bootstrap = [
        {
            "bytes": item["bytes"],
            "path": f"data/{item['path']}",
            "rationale": (
                "Bootstrap artifact remains static; compact it before considering an R2 "
                "dependency for initial load."
            ),
        }
        for item in bootstrap
        if item["bytes"] >= candidate_bytes
    ]
    large_bootstrap.sort(key=lambda item: (-item["bytes"], item["path"]))

    return {
        "activation_assessment": {
            "gates": activation_gates,
            "recommendation": (
                "evaluate_r2_only_after_a_gate_is_sustained_and_prerequisites_pass"
                if triggered_gates
                else "keep_workers_static_assets"
            ),
            "triggered_gates": triggered_gates,
        },
        "candidate_partitions": candidates,
        "current_static_footprint": static,
        "group_summary": group_summary,
        "large_bootstrap_artifacts_kept_static": large_bootstrap,
        "migration_thresholds": {
            "activation_asset_count": activation_asset_count,
            "activation_individual_asset_bytes": activation_individual_bytes,
            "activation_total_static_bytes": activation_total_bytes,
            "candidate_partition_bytes": candidate_bytes,
            "priority_partition_bytes": priority_bytes,
            "rationale": {
                "activation": (
                    "R2 review requires a sustained documented architecture gate, "
                    "not merely an eligible partition."
                ),
                "candidate": (
                    f"The {candidate_bytes}-byte threshold is "
                    f"{(candidate_bytes / activation_individual_bytes) * 100:.1f}% of the "
                    "individual-asset activation warning and identifies deploy-heavy lazy payloads early."
                ),
                "priority": (
                    f"The {priority_bytes}-byte threshold is "
                    f"{(priority_bytes / activation_individual_bytes) * 100:.1f}% of the "
                    "individual-asset activation warning."
                ),
            },
        },
        "projected_static_footprint_if_candidates_moved": {
            "asset_count": static["asset_count"] - len(candidates),
            "bytes_removed": candidate_total_bytes,
            "candidate_count": len(candidates),
            "remaining_total_bytes": static["total_bytes"] - candidate_total_bytes,
        },
        "safety": {
            "activates_r2": False,
            "cloud_api_calls": False,
            "creates_resources": False,
            "estimated_cost_usd": None,
            "mode": "offline_read_only_simulation",
        },
        "schema_version": "civicledger-r2-migration-simulation-v1",
        "source": {
            "dataset_version": manifest.get("dataset_version"),
            "evaluated_query_partition_count": len(query_partitions),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--candidate-bytes", type=int, default=DEFAULT_CANDIDATE_BYTES)
    parser.add_argument("--priority-bytes", type=int, default=DEFAULT_PRIORITY_BYTES)
    parser.add_argument("--activation-asset-count", type=int, default=DEFAULT_ACTIVATION_ASSET_COUNT)
    parser.add_argument("--activation-total-bytes", type=int, default=DEFAULT_ACTIVATION_TOTAL_BYTES)
    parser.add_argument("--activation-individual-bytes", type=int, default=DEFAULT_ACTIVATION_INDIVIDUAL_BYTES)
    parser.add_argument("--json", action="store_true", help="Print the report")
    args = parser.parse_args()

    site = args.site.resolve()
    manifest_path = (args.manifest or site / "data" / "manifest.json").resolve()
    try:
        report = build_simulation(
            site,
            manifest_path,
            candidate_bytes=args.candidate_bytes,
            priority_bytes=args.priority_bytes,
            activation_asset_count=args.activation_asset_count,
            activation_total_bytes=args.activation_total_bytes,
            activation_individual_bytes=args.activation_individual_bytes,
        )
        write_json(args.output.resolve(), report)
    except (OSError, CorpusMetricsError) as exc:
        raise SystemExit(f"R2 public partition simulation failed: {exc}") from exc

    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        projection = report["projected_static_footprint_if_candidates_moved"]
        print(
            "R2 migration simulation complete (no resources created): "
            f"candidates={projection['candidate_count']}, "
            f"candidate_bytes={projection['bytes_removed']}, "
            f"recommendation={report['activation_assessment']['recommendation']}"
        )


if __name__ == "__main__":
    main()
