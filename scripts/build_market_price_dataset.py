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

from app.services.market_prices import (  # noqa: E402
    MARKET_PRICE_SYMBOLS,
    TICKER_REFERENCE,
    NasdaqClient,
    TiingoClient,
)


OUTPUT = ROOT / "data" / "context" / "market_prices.json"
DEFAULT_START = "2023-01-01"


def _load_existing_dataset() -> dict:
    if not OUTPUT.exists():
        return {}
    return json.loads(OUTPUT.read_text())


def _series_from_points(symbol: str, source: str, price_field: str, points: list[dict]) -> dict:
    return {
        "symbol": symbol.upper(),
        "source": source,
        "source_url": (
            f"https://www.tiingo.com/tiingo/daily/{symbol.upper()}"
            if source == "tiingo"
            else f"https://www.nasdaq.com/market-activity/stocks/{symbol.upper()}/historical"
        ),
        "price_field_for_overlays": price_field,
        "reference": TICKER_REFERENCE.get(symbol.upper(), {}),
        "points": points,
    }


def _point_value(point: dict) -> float | None:
    return point.get("adj_close") if point.get("adj_close") is not None else point.get("close")


def _coverage_from_series(status: str, item: dict, **extra: str) -> dict:
    point_rows = item.get("points", [])
    return {
        "status": status,
        "provider": item.get("source"),
        "point_count": len(point_rows),
        "first_date": point_rows[0]["date"] if point_rows else None,
        "last_date": point_rows[-1]["date"] if point_rows else None,
        **extra,
    }


def build_dataset(
    api_key: str | None,
    start: str,
    end: str,
    symbols: list[str],
    existing: dict | None = None,
) -> dict:
    tiingo_client = TiingoClient(api_key=api_key)
    nasdaq_client = NasdaqClient()
    existing = existing or {}
    existing_series = existing.get("series", {})
    series = {}
    coverage = {}
    anomalies = []
    for symbol in symbols:
        symbol = symbol.upper()
        primary_error = None
        try:
            points = tiingo_client.historical_prices(symbol, start_date=start, end_date=end)
            point_rows = [point.as_dict() for point in points]
            series[symbol] = _series_from_points(symbol, "tiingo", "adj_close", point_rows)
            coverage[symbol] = _coverage_from_series("covered", series[symbol])
        except Exception as exc:
            primary_error = str(exc)
            cached = existing_series.get(symbol)
            if cached and cached.get("points"):
                series[symbol] = cached
                coverage[symbol] = _coverage_from_series(
                    "cached",
                    cached,
                    cached_from=existing.get("generated_at"),
                    primary_error=primary_error,
                )
            else:
                try:
                    points = nasdaq_client.historical_prices(
                        symbol,
                        start_date=start,
                        end_date=end,
                        asset_class=TICKER_REFERENCE.get(symbol, {}).get("asset_class"),
                    )
                    point_rows = [point.as_dict() for point in points]
                    series[symbol] = _series_from_points(symbol, "nasdaq", "close", point_rows)
                    coverage[symbol] = _coverage_from_series(
                        "covered",
                        series[symbol],
                        primary_error=primary_error,
                    )
                except Exception as fallback_exc:
                    coverage[symbol] = {
                        "status": "error",
                        "provider": None,
                        "point_count": 0,
                        "primary_error": primary_error,
                        "fallback_error": str(fallback_exc),
                    }
                    continue
        point_rows = series[symbol].get("points", [])
        for previous, current in zip(point_rows, point_rows[1:]):
            previous_value = _point_value(previous)
            current_value = _point_value(current)
            if not previous_value or current_value is None:
                continue
            pct_change = ((current_value - previous_value) / previous_value) * 100
            if abs(pct_change) >= 35:
                anomalies.append(
                    {
                        "symbol": symbol,
                        "date": current["date"],
                        "previous_date": previous["date"],
                        "pct_change": round(pct_change, 2),
                    }
                )

    provider_counts = {}
    for item in series.values():
        provider_counts[item["source"]] = provider_counts.get(item["source"], 0) + 1
    active_provider = "Tiingo"
    if provider_counts.get("nasdaq"):
        active_provider = "Tiingo preferred with Nasdaq fallback"
    if provider_counts and not provider_counts.get("tiingo"):
        active_provider = "Nasdaq fallback"

    return {
        "generated_at": date.today().isoformat(),
        "source": {
            "id": "market-price-provider-chain",
            "name": active_provider,
            "url": "https://www.tiingo.com/documentation/end-of-day",
            "fallback_url": "https://api.nasdaq.com/api/quote/{symbol}/historical",
            "source_tier": "market_data_provider",
        },
        "scope": {
            "description": (
                "Production ETF and ticker market-price overlays for public-official "
                "trade timelines. CivicLedger prefers Tiingo adjusted close and can "
                "fall back to Nasdaq daily close when Tiingo is temporarily limited."
            ),
            "observation_start": start,
            "observation_end": end,
            "symbols": [symbol.upper() for symbol in symbols],
        },
        "summary": {
            "series_count": len(series),
            "price_point_count": sum(len(item["points"]) for item in series.values()),
            "active_market_price_provider": active_provider,
            "symbols": [symbol.upper() for symbol in symbols],
            "provider_counts": provider_counts,
            "fresh_symbol_count": sum(1 for item in coverage.values() if item["status"] == "covered"),
            "cached_symbol_count": sum(1 for item in coverage.values() if item["status"] == "cached"),
            "covered_symbol_count": sum(1 for item in coverage.values() if item["status"] in {"covered", "cached"}),
            "missing_symbol_count": sum(1 for item in coverage.values() if item["status"] not in {"covered", "cached"}),
            "anomaly_count": len(anomalies),
        },
        "ticker_reference": {
            symbol: TICKER_REFERENCE.get(symbol, {})
            for symbol in [symbol.upper() for symbol in symbols]
        },
        "coverage_report": coverage,
        "anomaly_report": anomalies,
        "series": series,
        "context_label": "Market-price overlays prefer Tiingo adjusted close data and disclose Nasdaq close fallback when used. Context only - no inference of causation, intent, legality, ethics, or investment performance.",
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
    dataset = build_dataset(args.api_key, args.start, args.end, symbols, existing=_load_existing_dataset())
    OUTPUT.write_text(
        json.dumps(dataset, indent=2, sort_keys=True) + "\n"
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
