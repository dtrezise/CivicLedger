#!/usr/bin/env python3
"""Build a source-hashed House Clerk PTR index matched to the official roster."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.house_disclosures import build_house_ptr_index  # noqa: E402


PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
OUTPUT = ROOT / "data" / "disclosures" / "house_disclosure_index.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2009)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    args = parser.parse_args()
    if args.start_year > args.end_year:
        raise SystemExit("--start-year cannot be after --end-year")
    public_officials = json.loads(PUBLIC_OFFICIALS.read_text())
    dataset = build_house_ptr_index(public_officials, args.start_year, args.end_year)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
