#!/usr/bin/env python3
"""Build production crypto market-price context from Tiingo crypto data."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

from app.services.market_prices import CRYPTO_PRICE_SYMBOLS, CRYPTO_REFERENCE, TiingoCryptoClient


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "context" / "crypto_prices.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=os.environ.get("TIINGO_API_KEY"))
    parser.add_argument("--start", default="2023-01-01", help="Inclusive start date in YYYY-MM-DD form.")
    parser.add_argument("--end", default=date.today().isoformat(), help="Inclusive end date in YYYY-MM-DD form.")
    return parser.parse_args()


def build_dataset(api_key: str, start: str, end: str) -> dict:
    client = TiingoCryptoClient(api_key=api_key)
    series = {}
    coverage = {}
    point_count = 0
    source_counts = Counter()

    for symbol in CRYPTO_PRICE_SYMBOLS:
        points = client.historical_prices(symbol, start_date=start, end_date=end)
        rows = [point.as_dict() for point in points]
        series[symbol] = {
            "symbol": symbol,
            "asset_class": "crypto",
            "issuer_name": CRYPTO_REFERENCE[symbol]["issuer_name"],
            "price_field_for_overlays": "close",
            "points": rows,
        }
        point_count += len(rows)
        source_counts.update(point.get("source", "tiingo_crypto") for point in rows)
        coverage[symbol] = {
            "status": "covered" if rows else "missing",
            "point_count": len(rows),
            "first_date": rows[0]["date"] if rows else None,
            "last_date": rows[-1]["date"] if rows else None,
        }

    return {
        "generated_at": date.today().isoformat(),
        "context_label": (
            "Crypto price overlays use Tiingo crypto daily close data. Context only - "
            "no inference of causation, intent, legality, ethics, or investment performance."
        ),
        "scope": {
            "symbols": CRYPTO_PRICE_SYMBOLS,
            "start_date": start,
            "end_date": end,
            "description": "Production crypto price overlays for public-official trade timelines.",
        },
        "source": {
            "id": "tiingo-crypto",
            "name": "Tiingo Crypto",
            "url": "https://api.tiingo.com/tiingo/crypto/prices",
            "source_tier": "market_data_provider",
        },
        "summary": {
            "active_crypto_price_provider": "Tiingo Crypto",
            "series_count": len(series),
            "covered_symbol_count": sum(1 for item in coverage.values() if item["status"] == "covered"),
            "missing_symbol_count": sum(1 for item in coverage.values() if item["status"] == "missing"),
            "price_point_count": point_count,
            "source_counts": dict(sorted(source_counts.items())),
        },
        "crypto_reference": {symbol: {"symbol": symbol, **meta} for symbol, meta in CRYPTO_REFERENCE.items()},
        "coverage_report": coverage,
        "series": series,
    }


def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit("Set TIINGO_API_KEY or pass --api-key to refresh crypto price data.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(args.api_key, args.start, args.end), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
