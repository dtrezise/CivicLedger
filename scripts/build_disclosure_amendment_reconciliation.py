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

from app.services.house_disclosures import reconcile_house_amendments  # noqa: E402
from app.services.senate_disclosures import reconcile_senate_amendments  # noqa: E402


HOUSE_INDEX = ROOT / "data" / "disclosures" / "house_disclosure_index.json"
SENATE_INDEX = ROOT / "data" / "disclosures" / "senate_disclosure_index.json"
OUTPUT = ROOT / "data" / "disclosures" / "disclosure_amendment_reconciliation.json"


def reconciliation_record(document: dict, *, chamber: str) -> dict:
    return {
        "document_id": document["document_id"],
        "document_family_id": document["document_family_id"],
        "chamber": chamber,
        "official_id": document.get("official_id"),
        "filer_name": document.get("official_name") or document.get("filer_name"),
        "filing_date": document.get("filing_date"),
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
    }


def build_dataset() -> dict:
    house_source = json.loads(HOUSE_INDEX.read_text())
    senate_source = json.loads(SENATE_INDEX.read_text())
    house_documents = reconcile_house_amendments(house_source.get("documents", []))
    senate_documents = reconcile_senate_amendments(senate_source.get("documents", []))
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
    linked_count = sum(bool(row["candidate_supersedes_document_id"]) for row in records)
    generated_at = max(
        date.fromisoformat(house_source["generated_at"]),
        date.fromisoformat(senate_source["generated_at"]),
    ).isoformat()
    return {
        "generated_at": generated_at,
        "schema_version": "disclosure-amendment-reconciliation-v1",
        "context_label": (
            "Document-level amendment reconciliation retains every official filing. Links are annotations "
            "supported by explicit source fields or exact official metadata; no source record is overwritten."
        ),
        "reconciliation_policy": {
            "destructive_merge_allowed": False,
            "automatic_trade_suppression_allowed": False,
            "house_link_rule": "explicit amends_document_id or original_document_id only",
            "senate_link_rule": (
                "official amendment title plus exactly one non-amendment filing in the same exact "
                "filer, normalized-title, and filing-date family"
            ),
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
