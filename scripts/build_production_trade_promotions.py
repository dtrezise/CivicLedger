#!/usr/bin/env python3
"""Build production promotion gate status from reviewed disclosure artifacts."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEWED_PROMOTIONS = ROOT / "data" / "disclosures" / "reviewed_disclosure_promotions.json"
RAW_ARCHIVE = ROOT / "data" / "disclosures" / "raw_document_archive_index.json"
OUTPUT = ROOT / "data" / "disclosures" / "production_trade_promotions.json"


def read_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text())


def build_dataset() -> dict:
    reviewed = read_json(REVIEWED_PROMOTIONS, {"promotions": [], "summary": {}})
    raw_archive = read_json(RAW_ARCHIVE, {"documents": [], "summary": {}})
    public_rows = [
        row
        for row in reviewed.get("promotions", [])
        if row.get("public_production_trade") is True and row.get("review_status") == "reviewed_public_production"
    ]
    blocked_rows = [
        {
            "record_id": row.get("record_id"),
            "document_id": row.get("document_id"),
            "source_id": row.get("source_id"),
            "source_file_hash": row.get("source_file_hash"),
            "blocked_criteria": row.get("failed_criteria", []),
            "blocked_reason": "parser preview lacks one or more required source or review evidence criteria",
        }
        for row in reviewed.get("evidence_review_queue", [])
        if row.get("eligible_for_public_production") is not True
    ]
    production_ready_raw_docs = [
        row
        for row in raw_archive.get("documents", [])
        if row.get("archive_status") == "archived"
        and row.get("expected_official_id")
        and row.get("source_status") not in {"downloadable_public_sample"}
    ]
    return {
        "generated_at": reviewed.get("generated_at") or date.today().isoformat(),
        "schema_version": "production-trade-promotions-v1",
        "context_label": (
            "Production trade promotion gate. Rows appear only after official source provenance, hashes, "
            "parser quality, identity, and explicit human review evidence all pass."
        ),
        "summary": {
            "reviewed_public_trade_count": len(public_rows),
            "blocked_non_production_review_count": (
                reviewed.get("summary", {}).get("evaluated_record_count", 0) - len(public_rows)
            ),
            "blocked_evidence_review_batch_count": len(blocked_rows),
            "production_ready_raw_document_count": len(production_ready_raw_docs),
            "review_required_before_public_trade": True,
        },
        "public_trade_rows": public_rows,
        "blocked_rows": blocked_rows,
        "production_ready_raw_documents": production_ready_raw_docs,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
