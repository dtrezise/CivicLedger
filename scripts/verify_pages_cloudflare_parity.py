#!/usr/bin/env python3
"""Compare the public GitHub Pages and Cloudflare static releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin


DEFAULT_PATHS = ("release.json", "data/manifest.json", "release-checksums.json")


class ParityError(RuntimeError):
    pass


def fetch(base_url: str, path: str, timeout: float = 30) -> bytes:
    url = urljoin(base_url.rstrip("/") + "/", path)
    request = urllib.request.Request(url, headers={"User-Agent": "CivicLedger-Parity-Check/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ParityError(f"{url} returned HTTP {response.status}")
            return response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ParityError(f"Unable to fetch {url}: {exc}") from exc


def json_body(payload: bytes, path: str) -> dict:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParityError(f"{path} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ParityError(f"{path} must contain a JSON object")
    return value


def checksum_paths(payload: dict) -> list[str]:
    rows = payload.get("files")
    if not isinstance(rows, list):
        raise ParityError("release-checksums.json has no files array")
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    if any(not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts for path in paths):
        raise ParityError("release-checksums.json contains an unsafe path")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ParityError("release-checksums.json paths must be sorted and unique")
    return paths


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate(pages_url: str, cloudflare_url: str, *, include_files: bool = True) -> dict:
    pages = {path: fetch(pages_url, path) for path in DEFAULT_PATHS}
    cloudflare = {path: fetch(cloudflare_url, path) for path in DEFAULT_PATHS}
    pages_release = json_body(pages["release.json"], "release.json")
    cloudflare_release = json_body(cloudflare["release.json"], "release.json")
    pages_manifest = json_body(pages["data/manifest.json"], "data/manifest.json")
    cloudflare_manifest = json_body(cloudflare["data/manifest.json"], "data/manifest.json")
    pages_checksums = json_body(pages["release-checksums.json"], "release-checksums.json")
    cloudflare_checksums = json_body(cloudflare["release-checksums.json"], "release-checksums.json")

    identity_fields = ("dataset_version", "methodology_version", "commit")
    identity_mismatches = [
        field for field in identity_fields if pages_release.get(field) != cloudflare_release.get(field)
    ]
    for field in ("dataset_version", "methodology_version"):
        if pages_manifest.get(field) != cloudflare_manifest.get(field) and field not in identity_mismatches:
            identity_mismatches.append(field)
    if identity_mismatches:
        raise ParityError("Release identity mismatch: " + ", ".join(identity_mismatches))

    pages_paths = checksum_paths(pages_checksums)
    cloudflare_paths = checksum_paths(cloudflare_checksums)
    if pages_paths != cloudflare_paths:
        raise ParityError("Release file inventories differ")

    mismatches: list[str] = []
    if include_files:
        for path in pages_paths:
            pages_body = fetch(pages_url, path)
            cloudflare_body = fetch(cloudflare_url, path)
            if digest(pages_body) != digest(cloudflare_body):
                mismatches.append(path)
        if mismatches:
            raise ParityError("Release file bytes differ: " + ", ".join(mismatches[:20]))

    return {
        "cloudflare_url": cloudflare_url,
        "dataset_version": pages_manifest.get("dataset_version"),
        "file_count": len(pages_paths),
        "pages_url": pages_url,
        "schema_version": "civicledger-pages-cloudflare-parity-v1",
        "status": "passed",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages-url", required=True)
    parser.add_argument("--cloudflare-url", required=True)
    parser.add_argument("--metadata-only", action="store_true", help="Compare identity and inventories without refetching every file.")
    parser.add_argument("--attempts", type=int, default=1, help="Retry the complete comparison while releases propagate.")
    parser.add_argument("--delay", type=float, default=15.0, help="Seconds between parity attempts.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = None
    last_error: Exception | None = None
    for attempt in range(max(1, args.attempts)):
        try:
            report = validate(args.pages_url, args.cloudflare_url, include_files=not args.metadata_only)
            break
        except (OSError, ParityError) as exc:
            last_error = exc
            if attempt + 1 < args.attempts:
                time.sleep(args.delay)
    if report is None:
        raise SystemExit(f"Pages/Cloudflare parity verification failed: {last_error}") from last_error
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Pages/Cloudflare parity passed: dataset={report['dataset_version']}, files={report['file_count']}")


if __name__ == "__main__":
    main()
