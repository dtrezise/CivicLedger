#!/usr/bin/env python3
"""Build a JEFS-safe judiciary disclosure research manifest from the FJC roster."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.judicial_disclosures import (  # noqa: E402
    build_judicial_disclosure_manifest,
    file_sha256,
)


DEFAULT_INPUT = ROOT / "data" / "public_officials" / "public_official_roles.json"
DEFAULT_OUTPUT = ROOT / "data" / "disclosures" / "judicial_disclosure_manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-year", type=int, default=2009)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_year < 1978 or args.start_year > args.as_of.year:
        raise SystemExit("--start-year must be between 1978 and --as-of year")
    roster = json.loads(args.input.read_text())
    payload = build_judicial_disclosure_manifest(
        roster,
        start_year=args.start_year,
        as_of=args.as_of,
        roster_sha256=file_sha256(args.input),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        f"Wrote {args.output} with {payload['summary']['official_count']} officials "
        f"and {payload['summary']['role_count']} service roles"
    )


if __name__ == "__main__":
    main()
