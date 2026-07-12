#!/usr/bin/env python3
"""Build or verify the checksum inventory for the deployable Pages artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "pages-site"
OUTPUT = SITE / "release-checksums.json"


def inventory() -> dict:
    manifest = json.loads((SITE / "data" / "manifest.json").read_text())
    files = []
    for path in sorted(SITE.rglob("*")):
        if not path.is_file() or path == OUTPUT:
            continue
        payload = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(SITE).as_posix(),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return {
        "schema_version": "civicledger-pages-checksums-v1",
        "dataset_version": manifest.get("dataset_version"),
        "methodology_version": manifest.get("methodology_version"),
        "generated_at": manifest.get("generated_at"),
        "summary": {
            "file_count": len(files),
            "total_bytes": sum(row["bytes"] for row in files),
        },
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = inventory()
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != encoded:
            raise SystemExit("Release checksum inventory is stale; rebuild it after Pages data generation.")
        print(f"Release checksum inventory verified for {payload['summary']['file_count']} files")
        return
    OUTPUT.write_text(encoded)
    print(f"Wrote {OUTPUT} for {payload['summary']['file_count']} files")


if __name__ == "__main__":
    main()
