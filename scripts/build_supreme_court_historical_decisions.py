#!/usr/bin/env python3
"""Build the official U.S. Reports decision index for calendar years 2009-2016."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.supreme_court_historical import (  # noqa: E402
    build_supreme_court_historical_decisions,
)


OUTPUT = ROOT / "data" / "context" / "supreme_court_historical_decisions.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2009-01-01")
    parser.add_argument("--end", default="2016-12-31")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    dataset = build_supreme_court_historical_decisions(
        args.start,
        args.end,
        as_of=args.as_of,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(OUTPUT), **dataset["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
