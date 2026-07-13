#!/usr/bin/env python3
"""Build non-destructive, evidence-bearing amendment reconciliation artifacts."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.house_disclosures import (  # noqa: E402
    house_transaction_signature,
    reconcile_house_amendments,
)
from app.services.senate_disclosures import (  # noqa: E402
    reconcile_senate_amendments,
    senate_report_date,
    senate_transaction_signature,
)


HOUSE_INDEX = ROOT / "data" / "disclosures" / "house_disclosure_index.json"
SENATE_INDEX = ROOT / "data" / "disclosures" / "senate_disclosure_index.json"
HOUSE_TRANSACTIONS = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
SENATE_TRANSACTIONS = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"
OUTPUT = ROOT / "data" / "disclosures" / "disclosure_amendment_reconciliation.json"


def transaction_signatures(transactions: list[dict], signature_builder) -> dict[str, list[str]]:
    by_document: dict[str, set[str]] = {}
    for transaction in transactions:
        document_id = transaction.get("document_id")
        if document_id:
            by_document.setdefault(document_id, set()).add(signature_builder(transaction))
    return {document_id: sorted(signatures) for document_id, signatures in by_document.items()}


def house_transaction_rows(manifest: dict) -> list[dict]:
    rows = []
    for record in manifest.get("year_partitions", {}).values():
        partition = json.loads((ROOT / record["path"]).read_text())
        rows.extend(partition.get("transactions", []))
    return rows


def add_signatures(documents: list[dict], signatures: dict[str, list[str]]) -> list[dict]:
    return [
        {**document, "transaction_signatures": signatures.get(document["document_id"], [])}
        for document in documents
    ]


def reconciliation_record(document: dict, *, chamber: str) -> dict:
    report_date = senate_report_date(document) if chamber == "Senate" else None
    return {
        "document_id": document["document_id"],
        "document_family_id": document["document_family_id"],
        "chamber": chamber,
        "official_id": document.get("official_id"),
        "filer_name": document.get("official_name") or document.get("filer_name"),
        "filing_date": document.get("filing_date"),
        "report_date": report_date.isoformat() if report_date else None,
        "source_url": document.get("source_url"),
        "source_tier": document.get("source_tier"),
        "is_amendment": bool(
            document.get("is_amendment")
            or document.get("amends_document_id")
            or document.get("original_document_id")
        ),
        "amendment_status": document["amendment_status"],
        "candidate_supersedes_document_id": document.get("candidate_supersedes_document_id")
        or document.get("supersedes_document_id"),
        "linkage_confidence": document["amendment_linkage_confidence"],
        "reconciliation_evidence": document["amendment_reconciliation_evidence"],
        "reconciliation_action": document["amendment_reconciliation_action"],
        "source_record_preserved": document["source_record_preserved"],
        "transaction_signature_count": len(document.get("transaction_signatures") or []),
    }


def build_dataset() -> dict:
    house_source = json.loads(HOUSE_INDEX.read_text())
    senate_source = json.loads(SENATE_INDEX.read_text())
    house_transaction_source = json.loads(HOUSE_TRANSACTIONS.read_text())
    senate_transaction_source = json.loads(SENATE_TRANSACTIONS.read_text())
    house_signatures = transaction_signatures(
        house_transaction_rows(house_transaction_source), house_transaction_signature
    )
    senate_signatures = transaction_signatures(
        senate_transaction_source.get("transactions", []), senate_transaction_signature
    )
    house_documents = reconcile_house_amendments(
        add_signatures(house_source.get("documents", []), house_signatures)
    )
    senate_documents = reconcile_senate_amendments(
        add_signatures(senate_source.get("documents", []), senate_signatures)
    )
    records = [
        reconciliation_record(document, chamber="House")
        for document in house_documents
        if document["amendment_status"] != "no_explicit_amendment_reference"
    ]
    records.extend(
        reconciliation_record(document, chamber="Senate")
        for document in senate_documents
        if document.get("is_amendment")
    )
    records.sort(key=lambda row: (row["filing_date"], row["chamber"], row["document_id"]))
    status_counts = Counter(row["amendment_status"] for row in records)
    chamber_counts = Counter(row["chamber"] for row in records)
    confidence_counts = Counter(row["linkage_confidence"] for row in records)
    linked_count = sum(bool(row["candidate_supersedes_document_id"]) for row in records)
    generated_at = max(
        date.fromisoformat(house_source["generated_at"]),
        date.fromisoformat(senate_source["generated_at"]),
    ).isoformat()
    return {
        "generated_at": generated_at,
        "schema_version": "disclosure-amendment-reconciliation-v2",
        "context_label": (
            "Document-level amendment reconciliation retains every official filing. Links are annotations "
            "supported by explicit source fields, official report dates, and transaction signatures when "
            "available; no source record is overwritten."
        ),
        "reconciliation_policy": {
            "destructive_merge_allowed": False,
            "automatic_trade_suppression_allowed": False,
            "house_link_rule": "explicit amends_document_id or original_document_id only",
            "senate_link_rule": (
                "same exact filer and report type, predecessor filed no more than 45 days earlier, "
                "then unique score of at least 80 with a margin of 15 based on official report dates "
                "and exact normalized transaction-signature overlap"
            ),
            "transaction_signature_fields": [
                "official_id",
                "trade_date",
                "action",
                "owner",
                "asset_display_name",
                "ticker",
                "value_range_label",
            ],
            "unresolved_amendments_remain_reviewable": True,
        },
        "summary": {
            "source_document_count": len(house_documents) + len(senate_documents),
            "amendment_document_count": len(records),
            "linked_candidate_count": linked_count,
            "unlinked_or_ambiguous_count": len(records) - linked_count,
            "source_record_preserved_count": sum(row["source_record_preserved"] for row in records),
            "chamber_counts": dict(sorted(chamber_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "linkage_confidence_counts": dict(sorted(confidence_counts.items())),
            "report_date_evidence_link_count": sum(
                row["linkage_confidence"] == "candidate_exact_report_date" for row in records
            ),
            "transaction_signature_evidence_link_count": sum(
                row["linkage_confidence"] == "candidate_date_and_signature_evidence"
                for row in records
            ),
            "amendment_with_transaction_signature_count": sum(
                row["transaction_signature_count"] > 0 for row in records
            ),
            "destructive_change_count": 0,
        },
        "reconciliations": records,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
