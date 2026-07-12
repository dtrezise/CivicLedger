#!/usr/bin/env python3
"""Build source-backed official involvement and institutional event context."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.official_event_involvement import (  # noqa: E402
    CachedRateLimitedHttpClient,
    OfficialCongressGovClient,
    build_official_event_involvement,
)


DEFAULT_EVENTS = ROOT / "data" / "context" / "federal_events.json"
DEFAULT_ROLES = ROOT / "data" / "public_officials" / "public_official_roles.json"
DEFAULT_OUTPUT = ROOT / "data" / "context" / "official_event_involvement.json"
DEFAULT_CACHE = (
    Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    / "civicledger"
    / "official_event_involvement"
)


def _repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_input(path: Path) -> tuple[dict, dict]:
    content = path.read_bytes()
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload, {
        "path": _repo_path(path),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "byte_count": len(content),
    }


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def write_partitioned_dataset(path: Path, dataset: dict) -> dict:
    partition_dir = path.parent / path.stem
    partition_dir.mkdir(parents=True, exist_ok=True)
    for stale in partition_dir.glob("relationships-*.json"):
        stale.unlink()

    congress_by_event = {
        bill["event_id"]: int(bill["congress"])
        for bill in dataset.get("bills", [])
        if bill.get("event_id") and bill.get("congress") is not None
    }
    grouped: dict[str, list[dict]] = {}
    for relationship in dataset.get("relationships", []):
        congress = congress_by_event.get(relationship.get("event_id"))
        key = str(congress) if congress is not None else "institutional"
        grouped.setdefault(key, []).append(relationship)

    partition_records = {}
    for key, relationships in sorted(grouped.items()):
        partition_path = partition_dir / f"relationships-{key}.json"
        payload = {
            "schema_version": "official-event-involvement-relationships-v1",
            "partition": key,
            "relationship_count": len(relationships),
            "relationships": relationships,
        }
        write_json_atomic(partition_path, payload)
        encoded = partition_path.read_bytes()
        partition_records[key] = {
            "path": _repo_path(partition_path),
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "relationship_count": len(relationships),
        }

    manifest = {
        key: value for key, value in dataset.items() if key != "relationships"
    }
    manifest["relationships_partitioned"] = True
    manifest["relationship_partitions"] = partition_records
    write_json_atomic(path, manifest)
    return manifest
    path.chmod(0o644)


def progress_reporter(message: str) -> None:
    match = re.search(r"(\d+)/(\d+)", message)
    if not match:
        print(message, flush=True)
        return
    current, total = (int(value) for value in match.groups())
    if current == 1 or current == total or current % 10 == 0:
        print(message, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--roles", type=Path, default=DEFAULT_ROLES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--api-key", default=os.environ.get("CONGRESS_GOV_API_KEY"))
    parser.add_argument("--offline", action="store_true", help="Require every HTTP response to exist in cache.")
    parser.add_argument("--refresh", action="store_true", help="Replace cached responses from official sources.")
    parser.add_argument("--min-interval", type=float, default=0.25, help="Minimum seconds between live requests.")
    args = parser.parse_args()

    if args.offline and args.refresh:
        parser.error("--offline and --refresh cannot be combined")
    if not args.offline and not args.api_key:
        parser.error("Set CONGRESS_GOV_API_KEY, pass --api-key, or use --offline with a complete cache")

    federal_events, events_provenance = load_input(args.events)
    public_official_roles, roles_provenance = load_input(args.roles)
    http_client = CachedRateLimitedHttpClient(
        args.cache_dir,
        offline=args.offline,
        refresh=args.refresh,
        min_interval_seconds=args.min_interval,
    )
    congress_client = OfficialCongressGovClient(http_client, api_key=args.api_key)
    dataset = build_official_event_involvement(
        federal_events,
        public_official_roles,
        congress_client,
        input_provenance={
            "federal_events": events_provenance,
            "public_official_roles": roles_provenance,
        },
        progress=progress_reporter,
    )
    manifest = write_partitioned_dataset(args.output, dataset)
    print(
        f"Wrote {args.output} and {len(manifest['relationship_partitions'])} relationship partitions "
        f"with {dataset['summary']['relationship_count']} relationships, "
        f"{dataset['summary']['roll_call_count']} roll calls, "
        f"{http_client.network_requests} live requests, and {http_client.cache_hits} cache hits."
    )


if __name__ == "__main__":
    main()
