#!/usr/bin/env python3
"""Recommend, defer, or decline a Cloudflare rollback from gate evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


VERSION_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.IGNORECASE)


class RecommendationError(RuntimeError):
    pass


def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RecommendationError(f"{path} must contain a JSON object")
    return value


def recommend(gates: dict, readiness: dict) -> dict:
    rows = gates.get("gates")
    if not isinstance(rows, list) or not rows:
        raise RecommendationError("Gate report must contain a non-empty gates array")
    failed = [row for row in rows if isinstance(row, dict) and str(row.get("status", "")).lower() in {"failed", "failure"}]
    post_deploy_failed = [row for row in failed if str(row.get("phase", "")).lower() in {"post_deploy", "post-deploy", "production"}]
    pre_deploy_failed = [row for row in failed if row not in post_deploy_failed]
    target = readiness.get("rollback_target_version_id")
    active = readiness.get("active_version_ids") or []
    target_valid = isinstance(target, str) and bool(VERSION_ID.fullmatch(target))
    active_valid = isinstance(active, list) and any(isinstance(value, str) and VERSION_ID.fullmatch(value) for value in active)

    if not failed:
        status, reason = "no_action", "No failed production gate was reported."
    elif pre_deploy_failed and not post_deploy_failed:
        status, reason = "no_action", "Failures occurred before production deployment; keep the current production version."
    elif not target_valid or not active_valid or target in active:
        status, reason = "manual_review", "A post-deploy gate failed, but rollback readiness does not identify a distinct valid prior version."
    else:
        status, reason = "rollback_recommended", "A post-deploy gate failed and a distinct prior Cloudflare version is available."

    report = {
        "failed_gate_names": [str(row.get("name", "unnamed")) for row in failed],
        "post_deploy_failed_gate_names": [str(row.get("name", "unnamed")) for row in post_deploy_failed],
        "pre_deploy_failed_gate_names": [str(row.get("name", "unnamed")) for row in pre_deploy_failed],
        "reason": reason,
        "rollback_command": readiness.get("rollback_command") if status == "rollback_recommended" else None,
        "rollback_target_version_id": target if status == "rollback_recommended" else None,
        "schema_version": "civicledger-rollback-recommendation-v1",
        "status": status,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = recommend(load(args.gates), load(args.readiness))
    except (OSError, json.JSONDecodeError, RecommendationError) as exc:
        raise SystemExit(f"Rollback recommendation failed: {exc}") from exc
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Cloudflare rollback recommendation: {report['status']} ({report['reason']})")


if __name__ == "__main__":
    main()
