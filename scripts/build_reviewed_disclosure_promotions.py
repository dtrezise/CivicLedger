#!/usr/bin/env python3
"""Systematically evaluate disclosure parser previews for evidence-qualified promotion."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.promotion import build_parser_preview_review_dataset  # noqa: E402


HOUSE_MANIFEST = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
SENATE_DATASET = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"
OUTPUT = ROOT / "data" / "disclosures" / "reviewed_disclosure_promotions.json"


def load_house_evidence(manifest: dict) -> tuple[list[dict], list[dict]]:
    documents = []
    transactions = []
    for year, record in sorted(manifest.get("year_partitions", {}).items()):
        partition = json.loads((ROOT / record["path"]).read_text())
        if str(partition.get("filing_year")) != year:
            raise ValueError(f"House partition year mismatch for {record['path']}")
        documents.extend(partition.get("documents", []))
        transactions.extend(partition.get("transactions", []))
    return documents, transactions


def build_dataset() -> dict:
    house_manifest = json.loads(HOUSE_MANIFEST.read_text())
    senate_dataset = json.loads(SENATE_DATASET.read_text())
    house_documents, house_transactions = load_house_evidence(house_manifest)
    generated_at = max(
        date.fromisoformat(house_manifest["generated_at"]),
        date.fromisoformat(senate_dataset["generated_at"]),
    ).isoformat()
    return build_parser_preview_review_dataset(
        [*house_documents, *senate_dataset.get("documents", [])],
        [*house_transactions, *senate_dataset.get("transactions", [])],
        generated_at=generated_at,
    )


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
