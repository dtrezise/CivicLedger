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
            "promotion_id": row.get("promotion_id"),
            "source_id": row.get("source_id"),
            "record_status": row.get("record_status"),
            "blocked_reason": "reviewed fixture or non-production source; real public trade promotion requires official raw document review",
        }
        for row in reviewed.get("promotions", [])
        if row.get("public_production_trade") is not True
    ]
    production_ready_raw_docs = [
        row
        for row in raw_archive.get("documents", [])
        if row.get("archive_status") == "archived"
        and row.get("expected_official_id")
        and row.get("source_status") not in {"downloadable_public_sample"}
    ]
    return {
        "generated_at": date.today().isoformat(),
        "schema_version": "production-trade-promotions-v1",
        "context_label": (
            "Production trade promotion gate. Rows appear only after official raw documents are archived, "
            "parsed, reviewed, and explicitly marked public production."
        ),
        "summary": {
            "reviewed_public_trade_count": len(public_rows),
            "blocked_non_production_review_count": len(blocked_rows),
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
