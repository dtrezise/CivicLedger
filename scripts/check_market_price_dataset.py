#!/usr/bin/env python3
"""Validate generated Tiingo market-price coverage before publishing."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "context" / "market_prices.json"


def main() -> None:
    data = json.loads(DATASET.read_text())
    summary = data["summary"]
    coverage = data.get("coverage_report", {})
    usable_statuses = {"covered", "cached"}
    missing = [symbol for symbol, item in coverage.items() if item.get("status") not in usable_statuses]
    provider = summary.get("active_market_price_provider", "")
    if not any(name in provider for name in ["Tiingo", "Nasdaq"]):
        raise SystemExit("market price provider is not recognized")
    if summary.get("covered_symbol_count", 0) < 20:
        raise SystemExit("market price coverage dropped below expected symbol count")
    if missing:
        raise SystemExit(f"market price coverage missing symbols: {', '.join(missing)}")
    if summary.get("price_point_count", 0) < 15000:
        raise SystemExit("market price point count dropped below expected threshold")
    anomalies = data.get("anomaly_report", [])
    if len(anomalies) > 20:
        raise SystemExit(f"too many market price anomalies: {len(anomalies)}")
    print(
        "Market price dataset ok: "
        f"{summary['covered_symbol_count']} symbols, "
        f"{summary['price_point_count']} points, "
        f"{summary.get('provider_counts', {})}, "
        f"{len(anomalies)} anomalies"
    )


if __name__ == "__main__":
    main()
