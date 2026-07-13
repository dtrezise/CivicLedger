#!/usr/bin/env python3
"""Validate the public workbench against Workers Static Assets limits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = ROOT / "pages-site"
MAX_ASSETS = 20_000
MAX_ASSET_BYTES = 25 * 1024 * 1024


class CheckError(RuntimeError):
    pass


def validate_assets(site: Path) -> dict[str, int]:
    if not site.is_dir():
        raise CheckError(f"Static asset directory does not exist: {site}")

    symlinks = sorted(path for path in site.rglob("*") if path.is_symlink())
    if symlinks:
        names = ", ".join(path.relative_to(site).as_posix() for path in symlinks[:5])
        raise CheckError(f"Static asset directory contains symlinks: {names}")

    assets = sorted(path for path in site.rglob("*") if path.is_file())
    if len(assets) > MAX_ASSETS:
        raise CheckError(f"Asset count {len(assets):,} exceeds the Workers limit of {MAX_ASSETS:,}")

    oversized = [path for path in assets if path.stat().st_size > MAX_ASSET_BYTES]
    if oversized:
        details = ", ".join(
            f"{path.relative_to(site).as_posix()} ({path.stat().st_size:,} bytes)"
            for path in oversized[:5]
        )
        raise CheckError(f"Assets exceed the 25 MiB per-file limit: {details}")

    total_bytes = sum(path.stat().st_size for path in assets)
    largest = max((path.stat().st_size for path in assets), default=0)
    return {
        "asset_count": len(assets),
        "largest_asset_bytes": largest,
        "remaining_asset_slots": MAX_ASSETS - len(assets),
        "total_asset_bytes": total_bytes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        summary = validate_assets(args.site.resolve())
    except (OSError, CheckError) as exc:
        raise SystemExit(f"Cloudflare asset validation failed: {exc}") from exc
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("Cloudflare asset validation passed: " + ", ".join(f"{key}={value}" for key, value in summary.items()))


if __name__ == "__main__":
    main()
