#!/usr/bin/env python3
"""Build deterministic, content-hashed browser assets for the static release."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "pages-site"
ASSET_DIR = SITE / "assets"
MANIFEST = ASSET_DIR / "manifest.json"
HTML_PATHS = (SITE / "index.html", SITE / "404.html")


class AssetBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class Asset:
    key: str
    source: Path
    stem: str
    suffix: str
    attribute: str

    def build_record(self) -> tuple[dict[str, object], bytes]:
        content = self.source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        sri = "sha384-" + base64.b64encode(hashlib.sha384(content).digest()).decode("ascii")
        filename = f"{self.stem}.{digest[:12]}{self.suffix}"
        return (
            {
                "bytes": len(content),
                "path": f"assets/{filename}",
                "sha256": digest,
                "source": self.source.relative_to(SITE).as_posix(),
                "sri": sri,
            },
            content,
        )


ASSETS = (
    Asset("styles", SITE / "styles.css", "styles", ".css", "href"),
    Asset("echarts", SITE / "vendor" / "echarts-5.6.0.min.js", "echarts-5.6.0", ".min.js", "src"),
    Asset("app", SITE / "app.js", "app", ".js", "src"),
)


def expected_build() -> tuple[dict[str, object], dict[Path, bytes], dict[Path, str]]:
    records: dict[str, dict[str, object]] = {}
    outputs: dict[Path, bytes] = {}
    for asset in ASSETS:
        record, content = asset.build_record()
        records[asset.key] = record
        outputs[SITE / str(record["path"])] = content

    manifest = {
        "assets": records,
        "schema_version": "civicledger-static-assets-v1",
    }
    outputs[MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")

    html_outputs: dict[Path, str] = {}
    for html_path in HTML_PATHS:
        html = html_path.read_text()
        for asset in ASSETS:
            if f'data-static-asset="{asset.key}"' not in html:
                continue
            record = records[asset.key]
            tag_pattern = re.compile(
                rf'<(?P<tag>link|script)\b[^>]*data-static-asset="{re.escape(asset.key)}"[^>]*>',
                re.IGNORECASE,
            )

            def replace_tag(match: re.Match[str]) -> str:
                tag = re.sub(r"\s*/\s+(?=integrity=)", " ", match.group(0))
                value = f'./{record["path"]}'
                attribute_pattern = re.compile(rf'{asset.attribute}="[^"]*"')
                if not attribute_pattern.search(tag):
                    raise AssetBuildError(f"{html_path.name} asset {asset.key} lacks {asset.attribute}")
                tag = attribute_pattern.sub(f'{asset.attribute}="{value}"', tag, count=1)
                if re.search(r'\bintegrity="[^"]*"', tag):
                    tag = re.sub(r'\bintegrity="[^"]*"', f'integrity="{record["sri"]}"', tag, count=1)
                else:
                    closing = "/>" if tag.rstrip().endswith("/>") else ">"
                    tag = tag.rstrip()[: -len(closing)].rstrip() + f' integrity="{record["sri"]}"{closing}'
                return tag

            html, replacements = tag_pattern.subn(replace_tag, html, count=1)
            if replacements != 1:
                raise AssetBuildError(f"{html_path.name} needs one {asset.key} asset tag")
        html_outputs[html_path] = html
    return manifest, outputs, html_outputs


def stale_assets(expected_paths: set[Path]) -> list[Path]:
    if not ASSET_DIR.exists():
        return []
    managed_prefixes = tuple(f"{asset.stem}." for asset in ASSETS)
    return sorted(
        path
        for path in ASSET_DIR.iterdir()
        if path.is_file() and path.name.startswith(managed_prefixes) and path not in expected_paths
    )


def check(outputs: dict[Path, bytes], html_outputs: dict[Path, str]) -> None:
    problems: list[str] = []
    for path, expected in outputs.items():
        if not path.is_file():
            problems.append(f"missing {path.relative_to(ROOT)}")
        elif path.read_bytes() != expected:
            problems.append(f"stale {path.relative_to(ROOT)}")
    for path, expected in html_outputs.items():
        if path.read_text() != expected:
            problems.append(f"stale references in {path.relative_to(ROOT)}")
    for path in stale_assets(set(outputs)):
        problems.append(f"obsolete {path.relative_to(ROOT)}")
    if problems:
        raise AssetBuildError("; ".join(problems))


def write(outputs: dict[Path, bytes], html_outputs: dict[Path, str]) -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for path in stale_assets(set(outputs)):
        path.unlink()
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    for path, content in html_outputs.items():
        path.write_text(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if generated assets or HTML references are stale")
    args = parser.parse_args()
    try:
        manifest, outputs, html_outputs = expected_build()
        if args.check:
            check(outputs, html_outputs)
        else:
            write(outputs, html_outputs)
    except (OSError, AssetBuildError) as exc:
        raise SystemExit(f"Static asset build failed: {exc}") from exc
    mode = "verified" if args.check else "built"
    print(f"Static assets {mode}: assets={len(manifest['assets'])}, bytes={sum(r['bytes'] for r in manifest['assets'].values()):,}")


if __name__ == "__main__":
    main()
