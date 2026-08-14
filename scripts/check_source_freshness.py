#!/usr/bin/env python3
"""Check generated CivicLedger source freshness for scheduled refreshes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sys
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ArtifactPolicy:
    path: str
    max_age_days: int | None = 14
    stale_is_error: bool = True


ADVISORY_ARTIFACTS = {
    "data/disclosures/senate_disclosure_index.json",
    "data/disclosures/senate_ptr_transactions.json",
    "data/context/official_event_involvement.json",
    "data/context/sec_issuer_aliases.json",
    "data/context/sec_filing_events.json",
    "data/operations/source_refresh_telemetry.json",
}
REFERENCE_ARTIFACTS = {
    "data/disclosures/house_historical_transaction_index.json",
    "data/context/supreme_court_historical_decisions.json",
}
ARTIFACT_PATHS = (
    "data/public_officials/public_official_roles.json",
    "data/disclosures/presidential_oge_disclosure_status.json",
    "data/disclosures/presidential_oge_documents.json",
    "data/disclosures/presidential_oge_transactions.json",
    "data/disclosures/executive_oge_disclosure_manifest.json",
    "data/disclosures/judicial_disclosure_manifest.json",
    "data/disclosures/disclosure_ingestion_queue.json",
    "data/disclosures/disclosure_retrieval_batches.json",
    "data/disclosures/production_trade_promotions.json",
    "data/disclosures/source_staleness_alerts.json",
    "data/disclosures/disclosure_completeness_dashboard.json",
    "data/disclosures/disclosure_ocr_priority_batches.json",
    "data/disclosures/disclosure_ocr_results.json",
    "data/disclosures/disclosure_amendment_reconciliation.json",
    "data/disclosures/house_disclosure_index.json",
    "data/disclosures/house_historical_transaction_index.json",
    "data/disclosures/house_ptr_transactions.json",
    "data/disclosures/senate_disclosure_index.json",
    "data/disclosures/senate_ptr_transactions.json",
    "data/context/federal_events.json",
    "data/context/supreme_court_historical_decisions.json",
    "data/context/fred_market_context.json",
    "data/context/market_prices.json",
    "data/context/crypto_prices.json",
    "data/context/asset_resolution.json",
    "data/context/trade_market_reactions.json",
    "data/context/official_event_involvement.json",
    "data/context/source_snapshots.json",
    "data/context/entity_reference.json",
    "data/context/sec_issuer_aliases.json",
    "data/context/sec_filing_events.json",
    "data/context/primary_source_context.json",
    "data/operations/source_refresh_telemetry.json",
    "pages-site/data/civicledger-static.json",
)
POLICIES = tuple(
    ArtifactPolicy(
        path,
        max_age_days=None if path in REFERENCE_ARTIFACTS else 14,
        stale_is_error=path not in ADVISORY_ARTIFACTS,
    )
    for path in ARTIFACT_PATHS
)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def evaluate_artifacts(
    root: Path,
    today: date,
    policies: tuple[ArtifactPolicy, ...] = POLICIES,
) -> tuple[list[str], list[str]]:
    failures = []
    warnings = []
    for policy in policies:
        path = root / policy.path
        if not path.exists():
            failures.append(f"Missing required generated file: {policy.path}")
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"Unreadable generated file: {policy.path} ({type(exc).__name__})")
            continue
        if not isinstance(data, dict):
            failures.append(f"Unreadable generated file: {policy.path} (expected a JSON object)")
            continue
        try:
            generated = parse_date(
                data.get("generated_at") or data.get("artifact_date") or data.get("captured_at")
            )
        except (TypeError, ValueError):
            failures.append(f"{policy.path} has an invalid generated date")
            continue
        if not generated:
            warnings.append(f"{policy.path} has no generated_at date")
            continue
        if policy.max_age_days is None:
            continue
        age_days = (today - generated).days
        if age_days <= policy.max_age_days:
            continue
        message = f"{policy.path} is stale: {age_days} days old"
        (failures if policy.stale_is_error else warnings).append(message)
    return failures, warnings


def main() -> None:
    today = date.today()
    failures, warnings = evaluate_artifacts(ROOT, today)

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
