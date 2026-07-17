#!/usr/bin/env python3
"""Write runtime release metadata into the static deployment artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "pages-site" / "data" / "manifest.json"
DEFAULT_OUTPUT = ROOT / "pages-site" / "release.json"


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--deployed-at", default=None)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    commit = args.commit.strip()
    if not commit:
        raise SystemExit("Release metadata requires a non-empty commit identifier.")
    payload = {
        "commit": commit,
        "dataset_generated_at": manifest.get("generated_at"),
        "dataset_version": manifest.get("dataset_version"),
        "deployed_at": args.deployed_at or iso_utc_now(),
        "schema_version": "civicledger-release-v1",
        "short_commit": commit[:7],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote release metadata for {payload['short_commit']} and dataset {payload['dataset_version']}")


if __name__ == "__main__":
    main()
