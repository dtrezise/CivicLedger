#!/usr/bin/env python3
"""Check generated CivicLedger source freshness for scheduled refreshes."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "data" / "public_officials" / "public_official_roles.json",
    ROOT / "data" / "disclosures" / "presidential_oge_disclosure_status.json",
    ROOT / "data" / "disclosures" / "presidential_oge_documents.json",
    ROOT / "data" / "disclosures" / "presidential_oge_transactions.json",
    ROOT / "data" / "disclosures" / "disclosure_ingestion_queue.json",
    ROOT / "data" / "disclosures" / "disclosure_retrieval_batches.json",
    ROOT / "data" / "disclosures" / "production_trade_promotions.json",
    ROOT / "data" / "disclosures" / "source_staleness_alerts.json",
    ROOT / "data" / "disclosures" / "disclosure_completeness_dashboard.json",
    ROOT / "data" / "context" / "market_prices.json",
    ROOT / "data" / "context" / "crypto_prices.json",
    ROOT / "pages-site" / "data" / "civicledger-static.json",
]


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def main() -> None:
    today = date.today()
    failures = []
    warnings = []
    for path in FILES:
        if not path.exists():
            failures.append(f"Missing required generated file: {path.relative_to(ROOT)}")
            continue
        data = json.loads(path.read_text())
        generated = parse_date(data.get("generated_at"))
        if not generated:
            warnings.append(f"{path.relative_to(ROOT)} has no generated_at date")
            continue
        age_days = (today - generated).days
        if age_days > 14:
            failures.append(f"{path.relative_to(ROOT)} is stale: {age_days} days old")

    queue_path = ROOT / "data" / "disclosures" / "disclosure_ingestion_queue.json"
    if queue_path.exists():
        queue = json.loads(queue_path.read_text())
        current_count = queue.get("summary", {}).get("current_or_current_term_queue_item_count", 0)
        if current_count <= 0:
            failures.append("Disclosure queue has no current-official/current-term entries")

    market_path = ROOT / "data" / "context" / "market_prices.json"
    if market_path.exists():
        market = json.loads(market_path.read_text())
        if market.get("summary", {}).get("missing_symbol_count", 0) != 0:
            warnings.append("Market overlay coverage has missing symbols")

    alerts_path = ROOT / "data" / "disclosures" / "source_staleness_alerts.json"
    if alerts_path.exists():
        alerts = json.loads(alerts_path.read_text())
        if alerts.get("summary", {}).get("high_alert_count", 0) > 0:
            failures.append("Source staleness alerts contain high-severity alerts")

    for warning in warnings:
        print(f"WARNING: {warning}")
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        sys.exit(1)
    print("Source freshness check passed.")


if __name__ == "__main__":
    main()
