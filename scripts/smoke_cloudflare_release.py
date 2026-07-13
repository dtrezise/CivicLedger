#!/usr/bin/env python3
"""Verify a deployed CivicLedger static release and its delivery headers."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin


DEFAULT_URL = "https://civic-ledger.dan-a2c.workers.dev/"


class SmokeError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def fetch(base_url: str, path: str, attempts: int) -> tuple[bytes, dict[str, str], int]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": "CivicLedger-Release-Smoke/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read(), {key.lower(): value for key, value in response.headers.items()}, response.status
        except (urllib.error.URLError, TimeoutError) as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(min(2**attempt, 8))
    raise SmokeError(f"Unable to fetch {url}: {error}")


def require_cache(headers: dict[str, str], fragment: str, path: str) -> None:
    value = headers.get("cache-control", "")
    require(fragment in value, f"{path} Cache-Control missing {fragment!r}: {value!r}")


def validate(args: argparse.Namespace) -> dict:
    checks: list[dict[str, object]] = []
    responses: dict[str, tuple[bytes, dict[str, str], int]] = {}
    for path in (
        "/",
        "/app.js",
        "/release.json",
        "/data/manifest.json",
        "/data/partitions/officials-index.json",
        "/data/partitions/market/meta.json",
        "/data/partitions/timelines/exec-donald-j-trump.json",
        "/data/partitions/events/2017.json",
    ):
        body, headers, status = fetch(args.base_url, path, args.attempts)
        require(status == 200, f"{path} returned HTTP {status}")
        require(body, f"{path} returned an empty body")
        responses[path] = (body, headers, status)
        checks.append({"path": path, "status": status, "bytes": len(body)})

    html = responses["/"][0].decode("utf-8")
    require("CivicLedger Federal Trade Explorer" in html, "Root HTML does not contain the expected title")
    release = json.loads(responses["/release.json"][0])
    manifest = json.loads(responses["/data/manifest.json"][0])
    require(release.get("dataset_version") == manifest.get("dataset_version"), "Release and manifest dataset versions differ")
    if args.expected_commit:
        require(
            str(release.get("commit", "")).startswith(args.expected_commit),
            f"Expected commit {args.expected_commit}, received {release.get('commit')}",
        )

    if not args.skip_header_checks:
        root_headers = responses["/"][1]
        expected_headers = {
            "content-security-policy": "frame-ancestors 'none'",
            "cross-origin-opener-policy": "same-origin",
            "permissions-policy": "camera=()",
            "referrer-policy": "strict-origin-when-cross-origin",
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
        }
        for name, fragment in expected_headers.items():
            value = root_headers.get(name, "")
            require(fragment in value, f"Root response header {name} missing {fragment!r}: {value!r}")
        require_cache(root_headers, "max-age=0", "/")
        require_cache(responses["/app.js"][1], "max-age=300", "/app.js")
        require_cache(responses["/release.json"][1], "no-store", "/release.json")
        require_cache(responses["/data/manifest.json"][1], "max-age=3600", "/data/manifest.json")

    return {
        "base_url": args.base_url,
        "checks": checks,
        "commit": release.get("commit"),
        "dataset_version": manifest.get("dataset_version"),
        "schema_version": "civicledger-cloudflare-smoke-v1",
        "security_headers_checked": not args.skip_header_checks,
        "status": "passed",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--expected-commit")
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--skip-header-checks", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args)
    except (SmokeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cloudflare release smoke failed: {exc}") from exc
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"Cloudflare release smoke passed: commit={report['commit']}, "
        f"dataset={report['dataset_version']}, endpoints={len(report['checks'])}"
    )


if __name__ == "__main__":
    main()
