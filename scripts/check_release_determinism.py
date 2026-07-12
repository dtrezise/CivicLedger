#!/usr/bin/env python3
"""Check canonical generated JSON and optionally prove a second build is byte-identical."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "pages-site" / "data"
MANIFEST = DATA / "manifest.json"


class CheckError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_snapshot() -> dict[str, str]:
    return {
        path.relative_to(DATA).as_posix(): digest(path)
        for path in sorted(DATA.rglob("*"))
        if path.is_file()
    }


def validate_canonical_json() -> dict[str, int | str]:
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    expected_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    require(manifest_bytes == expected_manifest, "manifest.json is not canonical sorted JSON")

    records = list(manifest.get("files", {}).values())
    records.extend(record for group in manifest.get("partitions", {}).values() for record in group.values())
    paths = [record["path"] for record in records]
    require(list(manifest.get("files", {})) == sorted(manifest.get("files", {})), "Manifest file keys must be sorted")
    for group, group_records in manifest.get("partitions", {}).items():
        require(list(group_records) == sorted(group_records), f"Manifest {group} keys must be sorted")
    require(len(paths) == len(set(paths)), "Manifest contains duplicate paths")

    aggregate = hashlib.sha256()
    for relative_path in paths:
        path = DATA / relative_path
        encoded = path.read_bytes()
        payload = json.loads(encoded)
        expected = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
        require(encoded == expected, f"Generated partition is not canonical JSON: {relative_path}")
        aggregate.update(relative_path.encode())
        aggregate.update(b"\0")
        aggregate.update(encoded)

    return {
        "aggregate_sha256": aggregate.hexdigest(),
        "canonical_partitions": len(paths),
    }


def validate_rebuild() -> int:
    before = public_snapshot()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "backend")
    builder_python = Path(sys.executable)
    bundled_venv_python = ROOT / ".venv" / "bin" / "python"
    if importlib.util.find_spec("pydantic_settings") is None and bundled_venv_python.is_file():
        builder_python = bundled_venv_python
    result = subprocess.run(
        [str(builder_python), str(ROOT / "scripts" / "build_pages_dataset.py")],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, f"Rebuild failed: {result.stderr.strip() or result.stdout.strip()}")
    after = public_snapshot()
    changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    require(not changed, "Second Pages build was not byte-identical: " + ", ".join(changed[:12]))
    return len(after)


def validate(rebuild: bool = False) -> dict[str, int | str]:
    summary = validate_canonical_json()
    if rebuild:
        summary["rebuild_files"] = validate_rebuild()
        validate_canonical_json()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="Run the Pages builder again and compare every output hash.")
    args = parser.parse_args()
    try:
        summary = validate(rebuild=args.rebuild)
    except (OSError, json.JSONDecodeError, CheckError) as exc:
        raise SystemExit(f"Release determinism validation failed: {exc}") from exc
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("Release determinism validation passed: " + ", ".join(f"{key}={value}" for key, value in summary.items()))


if __name__ == "__main__":
    main()
