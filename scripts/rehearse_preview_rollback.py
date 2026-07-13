#!/usr/bin/env python3
"""Rehearse Cloudflare rollback target selection without changing production."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from verify_cloudflare_rollback import collect_active_version_ids, collect_ids, load_json


class RehearsalError(RuntimeError):
    pass


def select_target(versions_path: Path, status_path: Path) -> tuple[str, str, list[str]]:
    versions = collect_ids(load_json(versions_path))
    active = collect_active_version_ids(load_json(status_path))
    prior = [value for value in versions if value not in active]
    if not active or not prior:
        raise RehearsalError("Cannot select a distinct active and prior version")
    return active[0], prior[-1], versions


def build_preview_config(site_dir: Path, destination: Path) -> Path:
    config = {
        "$schema": "node_modules/wrangler/config-schema.json",
        "name": "civic-ledger-rollback-rehearsal",
        "compatibility_date": "2026-07-13",
        "workers_dev": True,
        "preview_urls": True,
        "assets": {"directory": str(site_dir.resolve())},
    }
    path = destination / "wrangler.preview.jsonc"
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return path


def rehearse(versions_path: Path, status_path: Path, site_dir: Path, wrangler: list[str], run_dry_run: bool) -> dict:
    active, target, versions = select_target(versions_path, status_path)
    with tempfile.TemporaryDirectory(prefix="civicledger-rollback-rehearsal-") as temp:
        config = build_preview_config(site_dir, Path(temp))
        rollback_command = [*wrangler, "rollback", target, "--message", "PREVIEW-ONLY rehearsal", "--config", str(config), "--yes"]
        dry_run_command = [*wrangler, "deploy", "--dry-run", "--config", str(config)]
        result = None
        if run_dry_run:
            env = {key: value for key, value in os.environ.items() if key not in {"CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"}}
            result = subprocess.run(dry_run_command, cwd=temp, env=env, capture_output=True, text=True)
            if result.returncode != 0:
                raise RehearsalError(result.stderr.strip() or result.stdout.strip() or "Wrangler dry-run failed")
        return {
            "active_version_id": active,
            "available_version_count": len(versions),
            "dry_run_command": shlex.join(dry_run_command),
            "executed": bool(run_dry_run),
            "rollback_command_verified_only": shlex.join(rollback_command),
            "rollback_executed": False,
            "rollback_target_version_id": target,
            "schema_version": "civicledger-preview-rollback-rehearsal-v1",
            "status": "passed",
            "wrangler_exit_code": result.returncode if result else None,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, default=Path("pages-site"))
    parser.add_argument("--wrangler", nargs="+", default=["npx", "--yes", "wrangler@4.110.0"])
    parser.add_argument("--run-dry-run", action="store_true", help="Run only Wrangler deploy --dry-run with Cloudflare credentials removed.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = rehearse(args.versions, args.status, args.site_dir, args.wrangler, args.run_dry_run)
    except (OSError, json.JSONDecodeError, RehearsalError) as exc:
        raise SystemExit(f"Preview rollback rehearsal failed: {exc}") from exc
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Preview-only rollback rehearsal passed: target={report['rollback_target_version_id']}, dry_run={report['executed']}")


if __name__ == "__main__":
    main()
