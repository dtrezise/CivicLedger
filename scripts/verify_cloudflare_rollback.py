#!/usr/bin/env python3
"""Verify that Cloudflare retains a current and prior rollback target."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


VERSION_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.IGNORECASE)


class RollbackError(RuntimeError):
    pass


def version_id(record: dict) -> str | None:
    for key in ("id", "version_id", "versionId"):
        value = record.get(key)
        if isinstance(value, str) and VERSION_ID.match(value):
            return value
    version = record.get("version")
    if isinstance(version, dict):
        return version_id(version)
    return None


def collect_ids(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        candidate = version_id(value)
        if candidate and candidate not in found:
            found.append(candidate)
        for child in value.values():
            for item in collect_ids(child):
                if item not in found:
                    found.append(item)
    elif isinstance(value, list):
        for child in value:
            for item in collect_ids(child):
                if item not in found:
                    found.append(item)
    return found


def load_json(path: Path) -> object:
    text = path.read_text().strip()
    start_candidates = [index for index in (text.find("["), text.find("{")) if index >= 0]
    if not start_candidates:
        raise RollbackError(f"No JSON payload found in {path}")
    return json.loads(text[min(start_candidates) :])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        versions_payload = load_json(args.versions)
        status_payload = load_json(args.status)
        versions = collect_ids(versions_payload)
        active = collect_ids(status_payload)
        if not active:
            raise RollbackError("The active deployment did not expose a version identifier")
        prior = [value for value in versions if value not in active]
        if not prior:
            raise RollbackError("No prior Worker version is available for rollback")
        report = {
            "active_version_ids": active,
            "available_version_count": len(versions),
            "rollback_command": f"wrangler rollback {prior[0]} --message <reason> --config wrangler.jsonc",
            "rollback_target_version_id": prior[0],
            "schema_version": "civicledger-rollback-readiness-v1",
            "status": "ready",
        }
    except (OSError, json.JSONDecodeError, RollbackError) as exc:
        raise SystemExit(f"Cloudflare rollback verification failed: {exc}") from exc
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"Cloudflare rollback verification passed: active={active[0]}, "
        f"target={prior[0]}, versions={len(versions)}"
    )


if __name__ == "__main__":
    main()
