#!/usr/bin/env python3
"""Build production market-price context from Tiingo EOD data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.market_prices import MARKET_PRICE_SYMBOLS, TiingoClient  # noqa: E402


OUTPUT = ROOT / "data" / "context" / "market_prices.json"
DEFAULT_START = "2023-01-01"


def build_dataset(api_key: str | None, start: str, end: str, symbols: list[str]) -> dict:
    client = TiingoClient(api_key=api_key)
    series = {}
    for symbol in symbols:
        points = client.historical_prices(symbol, start_date=start, end_date=end)
        series[symbol.upper()] = {
            "symbol": symbol.upper(),
            "source": "tiingo",
            "source_url": f"https://www.tiingo.com/tiingo/daily/{symbol.upper()}",
            "price_field_for_overlays": "adj_close",
            "points": [point.as_dict() for point in points],
        }

    return {
        "generated_at": date.today().isoformat(),
        "source": {
            "id": "tiingo-eod",
            "name": "Tiingo End-of-Day Stock Price API",
            "url": "https://www.tiingo.com/documentation/end-of-day",
            "source_tier": "market_data_provider",
        },
        "scope": {
            "description": (
                "Production ETF and ticker market-price overlays for public-official "
                "trade timelines. CivicLedger uses adjusted close for neutral "
                "post-trade movement context."
            ),
            "observation_start": start,
            "observation_end": end,
            "symbols": [symbol.upper() for symbol in symbols],
        },
        "summary": {
            "series_count": len(series),
            "price_point_count": sum(len(item["points"]) for item in series.values()),
            "active_market_price_provider": "Tiingo",
            "symbols": [symbol.upper() for symbol in symbols],
        },
        "series": series,
        "context_label": "Market-price overlays use Tiingo adjusted close data. Context only - no inference of causation, intent, legality, ethics, or investment performance.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.environ.get("TIINGO_API_KEY"))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--symbols", default=",".join(MARKET_PRICE_SYMBOLS))
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("Set TIINGO_API_KEY or pass --api-key to refresh market price data.")
    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(args.api_key, args.start, args.end, symbols), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
