#!/usr/bin/env python3
"""Validate the public workbench against Workers Static Assets limits."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = ROOT / "pages-site"
MAX_ASSETS = 20_000
MAX_ASSET_BYTES = 25 * 1024 * 1024


class CheckError(RuntimeError):
    pass


def validate_assets(site: Path) -> dict[str, int | list[dict[str, int | str]] | dict[str, int]]:
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
    bytes_by_extension: dict[str, int] = defaultdict(int)
    for path in assets:
        bytes_by_extension[path.suffix.lower() or "[no extension]"] += path.stat().st_size
    largest_assets = [
        {"path": path.relative_to(site).as_posix(), "bytes": path.stat().st_size}
        for path in sorted(assets, key=lambda item: item.stat().st_size, reverse=True)[:10]
    ]
    return {
        "asset_count": len(assets),
        "bytes_by_extension": dict(sorted(bytes_by_extension.items())),
        "largest_asset_bytes": largest,
        "largest_assets": largest_assets,
        "remaining_asset_slots": MAX_ASSETS - len(assets),
        "total_asset_bytes": total_bytes,
    }


def load_baseline(path: Path | None) -> dict | None:
    if path is None:
        return None
    payload = json.loads(path.read_text())
    return payload.get("current", payload)


def build_report(site: Path, baseline_path: Path | None = None) -> dict:
    current = validate_assets(site)
    baseline = load_baseline(baseline_path)
    growth = None
    if baseline:
        baseline_bytes = int(baseline.get("total_asset_bytes", 0))
        current_bytes = int(current["total_asset_bytes"])
        growth = {
            "asset_count_delta": int(current["asset_count"]) - int(baseline.get("asset_count", 0)),
            "total_asset_bytes_delta": current_bytes - baseline_bytes,
            "total_asset_percent": round(((current_bytes - baseline_bytes) / baseline_bytes) * 100, 3)
            if baseline_bytes
            else None,
        }
    return {
        "baseline": baseline,
        "current": current,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "growth": growth,
        "limits": {"asset_count": MAX_ASSETS, "individual_asset_bytes": MAX_ASSET_BYTES},
        "schema_version": "civicledger-cloudflare-assets-v1",
    }


def markdown_summary(report: dict) -> str:
    current = report["current"]
    growth = report.get("growth") or {}
    growth_label = "Baseline established"
    if growth:
        growth_label = (
            f"{growth['total_asset_bytes_delta']:+,} bytes "
            f"({growth['total_asset_percent']:+.3f}%)"
        )
    return "\n".join(
        (
            "### Cloudflare static asset footprint",
            "",
            "| Measure | Value |",
            "| --- | ---: |",
            f"| Assets | {current['asset_count']:,} / {MAX_ASSETS:,} |",
            f"| Total uncompressed bytes | {current['total_asset_bytes']:,} |",
            f"| Largest asset bytes | {current['largest_asset_bytes']:,} / {MAX_ASSET_BYTES:,} |",
            f"| Growth from baseline | {growth_label} |",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    try:
        report = build_report(args.site.resolve(), args.baseline.resolve() if args.baseline else None)
        summary = report["current"]
    except (OSError, json.JSONDecodeError, CheckError) as exc:
        raise SystemExit(f"Cloudflare asset validation failed: {exc}") from exc
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        print(markdown_summary(report))
    elif args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(
            "Cloudflare asset validation passed: "
            + ", ".join(
                f"{key}={summary[key]}"
                for key in ("asset_count", "largest_asset_bytes", "remaining_asset_slots", "total_asset_bytes")
            )
        )


if __name__ == "__main__":
    main()
