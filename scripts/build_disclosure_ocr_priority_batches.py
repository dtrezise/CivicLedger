#!/usr/bin/env python3
"""Prioritize official House and Senate image disclosures without inventing OCR text."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.house_disclosures import house_ocr_priority_record  # noqa: E402
from app.services.senate_disclosures import senate_ocr_priority_record  # noqa: E402


HOUSE_MANIFEST = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
SENATE_DATASET = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"
OUTPUT = ROOT / "data" / "disclosures" / "disclosure_ocr_priority_batches.json"
BATCH_SIZE = 50


def load_house_documents(manifest: dict) -> list[dict]:
    documents = []
    for year, record in sorted(manifest.get("year_partitions", {}).items()):
        partition = json.loads((ROOT / record["path"]).read_text())
        if str(partition.get("filing_year")) != year:
            raise ValueError(f"House partition year mismatch for {record['path']}")
        documents.extend(partition.get("documents", []))
    return documents


def priority_sort_key(row: dict) -> tuple:
    filing_ordinal = date.fromisoformat(row["filing_date"]).toordinal()
    return (-row["priority_score"], -filing_ordinal, row["document_id"])


def build_batch(chamber: str, candidates: list[dict], *, as_of: date) -> dict:
    ordered = sorted(candidates, key=priority_sort_key)
    eligible = [row for row in ordered if row["eligible_for_ocr_batch"]]
    selected = eligible[:BATCH_SIZE]
    digest_input = "\n".join(row["document_id"] for row in selected).encode("utf-8")
    tier_counts = Counter(row["priority_tier"] for row in ordered)
    return {
        "batch_id": f"{chamber.lower()}-ocr-highest-confidence-{as_of.isoformat()}",
        "chamber": chamber,
        "batch_status": "ready_for_ocr_processing",
        "processing_boundary": "metadata_only_no_ocr_content_generated",
        "backlog_document_count": len(ordered),
        "eligible_document_count": len(eligible),
        "selected_document_count": len(selected),
        "remaining_eligible_document_count": max(0, len(eligible) - len(selected)),
        "selected_source_page_count": sum(row["source_page_count"] for row in selected),
        "selected_source_byte_count": sum(row["source_byte_count"] for row in selected),
        "priority_tier_counts": dict(sorted(tier_counts.items())),
        "selected_document_id_sha256": hashlib.sha256(digest_input).hexdigest(),
        "candidates": selected,
    }


def build_dataset() -> dict:
    house_manifest = json.loads(HOUSE_MANIFEST.read_text())
    senate_dataset = json.loads(SENATE_DATASET.read_text())
    generated_dates = [
        date.fromisoformat(house_manifest["generated_at"]),
        date.fromisoformat(senate_dataset["generated_at"]),
    ]
    as_of = max(generated_dates)
    house_candidates = [
        row
        for document in load_house_documents(house_manifest)
        if (row := house_ocr_priority_record(document, as_of=as_of)) is not None
    ]
    senate_candidates = [
        row
        for document in senate_dataset.get("documents", [])
        if (row := senate_ocr_priority_record(document, as_of=as_of)) is not None
    ]
    batches = [
        build_batch("House", house_candidates, as_of=as_of),
        build_batch("Senate", senate_candidates, as_of=as_of),
    ]
    return {
        "generated_at": as_of.isoformat(),
        "schema_version": "disclosure-ocr-priority-batches-v1",
        "context_label": (
            "Deterministic metadata-only priority batches for official image disclosures. "
            "No OCR text or transaction content is inferred or fabricated."
        ),
        "priority_policy": {
            "primary_order": [
                "evidence_score_descending",
                "filing_date_descending",
                "document_id_ascending",
            ],
            "house_evidence": [
                "official House Clerk PTR URL",
                "source PDF SHA-256",
                "deterministic filer identity match",
                "source PDF page count",
            ],
            "senate_evidence": [
                "official Senate report URL",
                "source report-page SHA-256",
                "deterministic filer identity match",
                "official Senate media-image manifest",
            ],
            "batch_size_per_chamber": BATCH_SIZE,
            "ocr_content_generation": "not_performed",
        },
        "summary": {
            "backlog_document_count": sum(batch["backlog_document_count"] for batch in batches),
            "eligible_document_count": sum(batch["eligible_document_count"] for batch in batches),
            "selected_document_count": sum(batch["selected_document_count"] for batch in batches),
            "selected_source_page_count": sum(batch["selected_source_page_count"] for batch in batches),
            "selected_source_byte_count": sum(batch["selected_source_byte_count"] for batch in batches),
            "ocr_content_record_count": 0,
            "transaction_rows_created": 0,
        },
        "batches": batches,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
