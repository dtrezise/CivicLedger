#!/usr/bin/env python3
"""Build the official-source House 2009-2014 transaction-document index."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.house_historical_disclosures import (  # noqa: E402
    build_house_historical_transaction_index,
)


OUTPUT = ROOT / "data" / "disclosures" / "house_historical_transaction_index.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2009)
    parser.add_argument("--end-year", type=int, default=2014)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    dataset = build_house_historical_transaction_index(
        args.start_year,
        args.end_year,
        as_of=args.as_of,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(OUTPUT), **dataset["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
