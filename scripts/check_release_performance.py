#!/usr/bin/env python3
"""Enforce static shell, initial-load, partition, and deployment size budgets."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from public_corpus_metrics import deployable_files


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "pages-site"
DATA = SITE / "data"
MANIFEST = DATA / "manifest.json"

SHELL_BUDGETS = {
    "index.html": 20_000,
    "styles.css": 40_000,
    "app.js": 100_000,
    "favicon.svg": 10_000,
}
RUNTIME_ASSET_BUDGETS = {
    "styles": 40_000,
    "app": 110_000,
    "echarts": 1_100_000,
}
INITIAL_NAMES = ("overview", "officials_index", "coverage", "events", "timeline_index", "market_index")
INITIAL_RAW_BUDGET = 4_750_000
INITIAL_GZIP_BUDGET = 350_000
SHELL_GZIP_BUDGET = 36_000
RUNTIME_GZIP_BUDGET = 425_000
DEPLOYMENT_BUDGET = 325_000_000
LEGACY_SNAPSHOT_BUDGET = 5_000_000
GROUP_BUDGETS = {
    "timelines": 5_000_000,
    "roles": 8_000_000,
    "market": 5_000_000,
    "events": 2_000_000,
}


class CheckError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def compressed_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))


def validate_performance() -> dict[str, int]:
    manifest = json.loads(MANIFEST.read_text())
    asset_manifest = json.loads((SITE / "assets" / "manifest.json").read_text())
    shell_raw = 0
    shell_gzip = 0
    for name, limit in SHELL_BUDGETS.items():
        path = SITE / name
        require(path.is_file(), f"Missing shell asset: {name}")
        size = path.stat().st_size
        require(size <= limit, f"Shell asset {name} exceeds {limit:,} bytes")
        shell_raw += size
        shell_gzip += compressed_size(path)
    require(shell_gzip <= SHELL_GZIP_BUDGET, f"Compressed shell exceeds {SHELL_GZIP_BUDGET:,} bytes")

    runtime_raw = 0
    runtime_gzip = 0
    records = asset_manifest.get("assets", {})
    require(set(RUNTIME_ASSET_BUDGETS) <= set(records), "Runtime static asset manifest is incomplete")
    for name, limit in RUNTIME_ASSET_BUDGETS.items():
        path = SITE / records[name]["path"]
        require(path.is_file(), f"Missing hashed runtime asset: {name}")
        size = path.stat().st_size
        require(size <= limit, f"Runtime asset {name} exceeds {limit:,} bytes")
        runtime_raw += size
        runtime_gzip += compressed_size(path)
    require(runtime_gzip <= RUNTIME_GZIP_BUDGET, f"Compressed runtime assets exceed {RUNTIME_GZIP_BUDGET:,} bytes")

    initial_records = manifest.get("files", {})
    require(set(INITIAL_NAMES) <= set(initial_records), "Initial manifest entries are incomplete")
    initial_raw = sum(initial_records[name]["bytes"] for name in INITIAL_NAMES)
    initial_gzip = sum(compressed_size(DATA / initial_records[name]["path"]) for name in INITIAL_NAMES)
    require(initial_raw <= INITIAL_RAW_BUDGET, f"Initial JSON payload exceeds {INITIAL_RAW_BUDGET:,} bytes")
    require(initial_gzip <= INITIAL_GZIP_BUDGET, f"Compressed initial JSON exceeds {INITIAL_GZIP_BUDGET:,} bytes")

    largest_partition = 0
    lazy_bytes = 0
    partition_count = 0
    for group, group_limit in GROUP_BUDGETS.items():
        records = manifest.get("partitions", {}).get(group, {})
        require(records, f"Missing {group} partitions")
        for name, record in records.items():
            size = record["bytes"]
            require(size <= group_limit, f"{group} partition {name} exceeds {group_limit:,} bytes")
            largest_partition = max(largest_partition, size)
            lazy_bytes += size
            partition_count += 1

    legacy_snapshot = DATA / "civicledger-static.json"
    require(legacy_snapshot.is_file(), "Compatibility snapshot is missing")
    require(legacy_snapshot.stat().st_size <= LEGACY_SNAPSHOT_BUDGET, "Compatibility snapshot exceeds its non-runtime budget")
    deployment_bytes = sum(path.stat().st_size for path in deployable_files(SITE))
    require(deployment_bytes <= DEPLOYMENT_BUDGET, f"Pages artifact exceeds {DEPLOYMENT_BUDGET:,} bytes")

    return {
        "deployment_bytes": deployment_bytes,
        "initial_gzip_bytes": initial_gzip,
        "initial_raw_bytes": initial_raw,
        "largest_partition_bytes": largest_partition,
        "partition_count": partition_count,
        "runtime_gzip_bytes": runtime_gzip,
        "runtime_raw_bytes": runtime_raw,
        "shell_gzip_bytes": shell_gzip,
        "shell_raw_bytes": shell_raw,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        summary = validate_performance()
    except (OSError, json.JSONDecodeError, CheckError) as exc:
        raise SystemExit(f"Release performance validation failed: {exc}") from exc
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("Release performance validation passed: " + ", ".join(f"{key}={value}" for key, value in summary.items()))


if __name__ == "__main__":
    main()
