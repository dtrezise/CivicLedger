#!/usr/bin/env python3
"""Build all-tracked-executive OGE disclosure coverage metadata."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.executive_disclosures import build_executive_disclosure_manifest  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--roster",
        type=Path,
        default=ROOT / "data" / "public_officials" / "public_official_roles.json",
    )
    parser.add_argument(
        "--presidential-documents",
        type=Path,
        default=ROOT / "data" / "disclosures" / "presidential_oge_documents.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "disclosures" / "executive_oge_disclosure_manifest.json",
    )
    parser.add_argument("--first-year", type=int, default=2009)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_executive_disclosure_manifest(
        json.loads(args.roster.read_text()),
        json.loads(args.presidential_documents.read_text()),
        first_year=args.first_year,
        as_of=args.as_of,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        f"Wrote {args.output} with {payload['summary']['official_count']} officials and "
        f"{payload['summary']['indexed_document_count']} linked documents"
    )


if __name__ == "__main__":
    main()
