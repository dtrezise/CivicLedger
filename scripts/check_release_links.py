#!/usr/bin/env python3
"""Validate static links, fragments, manifest paths, and official provenance hosts."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "pages-site"


class DocumentLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        for name in ("href", "src"):
            if attributes.get(name):
                self.links.append((name, attributes[name]))


def official_host_allowed(hostname: str) -> bool:
    hostname = hostname.lower().strip(".")
    return (
        hostname.endswith(".gov")
        or hostname == "gov"
        or hostname == "stlouisfed.org"
        or hostname.endswith(".stlouisfed.org")
    )


def manifest_paths(manifest: dict) -> list[str]:
    paths = [record["path"] for record in manifest.get("files", {}).values()]
    for records in manifest.get("partitions", {}).values():
        paths.extend(record["path"] for record in records.values())
    return paths


def main() -> None:
    parser = DocumentLinks()
    parser.feed((SITE / "index.html").read_text())
    errors = []
    for kind, value in parser.links:
        if value.startswith("#"):
            if value[1:] not in parser.ids:
                errors.append(f"Missing fragment target: {value}")
            continue
        parts = urlsplit(value)
        if parts.scheme:
            if parts.scheme not in {"https", "mailto"}:
                errors.append(f"Unsupported {kind} scheme: {value}")
            continue
        target = (SITE / parts.path.lstrip("/")).resolve()
        if SITE.resolve() not in target.parents and target != SITE.resolve():
            errors.append(f"Path escapes Pages root: {value}")
        elif not target.exists():
            errors.append(f"Missing local asset: {value}")

    manifest = json.loads((SITE / "data" / "manifest.json").read_text())
    for relative in manifest_paths(manifest):
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append(f"Unsafe manifest path: {relative}")
        elif not (SITE / "data" / relative).is_file():
            errors.append(f"Missing manifest file: {relative}")

    overview = json.loads((SITE / "data" / "partitions" / "overview.json").read_text())
    for source in overview.get("sources", []):
        for key in ("source_url", "search_url", "download_url", "public_sample_url"):
            value = source.get(key)
            if not value:
                continue
            parts = urlsplit(value)
            if parts.scheme != "https" or not official_host_allowed(parts.hostname or ""):
                errors.append(f"Official source URL is outside the allow policy: {value}")

    if errors:
        raise SystemExit("Release link validation failed:\n- " + "\n- ".join(errors))
    print(
        f"Release link validation passed: html_links={len(parser.links)}, "
        f"manifest_paths={len(manifest_paths(manifest))}"
    )


if __name__ == "__main__":
    main()
