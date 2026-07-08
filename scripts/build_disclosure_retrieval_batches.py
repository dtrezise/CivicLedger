#!/usr/bin/env python3
"""Build first-pass source retrieval batches from the disclosure ingestion queue."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from app.services.official_sources import OFFICIAL_SOURCES


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "disclosures" / "disclosure_ingestion_queue.json"
OUTPUT = ROOT / "data" / "disclosures" / "disclosure_retrieval_batches.json"

SOURCE_ORDER = [
    "house-financial-disclosure",
    "senate-public-financial-disclosure",
    "oge-individual-disclosures",
    "judicial-financial-disclosure",
]

BATCH_LIMITS = {
    "house-financial-disclosure": 24,
    "senate-public-financial-disclosure": 24,
    "oge-individual-disclosures": 24,
    "judicial-financial-disclosure": 24,
}


def source_by_id() -> dict[str, dict]:
    return {source["id"]: source for source in OFFICIAL_SOURCES}


def batch_status(source: dict) -> str:
    access_mode = source.get("access_mode") or ""
    if "acknowledged" in access_mode:
        return "blocked_pending_human_access_acknowledgement"
    return "ready_for_official_source_search"


def source_instruction(source_id: str) -> str:
    if source_id == "house-financial-disclosure":
        return "Use House Clerk disclosure search for the named member and current Congress, then archive raw PDF before parsing."
    if source_id == "senate-public-financial-disclosure":
        return "After source terms are acknowledged, search the Senate public disclosure system for the named senator and archive raw reports before parsing."
    if source_id == "oge-individual-disclosures":
        return "Search OGE individual disclosures by official name; archive released 278e or 278-T files before parser review."
    if source_id == "judicial-financial-disclosure":
        return "After judiciary access terms are acknowledged, request/search JEFS records by judge name and court before parser review."
    return "Search official source and archive raw evidence before parser review."


def candidate_row(entry: dict, source: dict, rank: int) -> dict:
    search_terms = [
        entry.get("full_name"),
        entry.get("state"),
        str(entry.get("district") or ""),
        entry.get("court"),
        entry.get("agency"),
        entry.get("presidential_term"),
    ]
    return {
        "rank": rank,
        "queue_id": entry["queue_id"],
        "official_id": entry["official_id"],
        "full_name": entry["full_name"],
        "branch": entry["branch"],
        "role_category": entry.get("role_category"),
        "role_title": entry.get("role_title"),
        "presidential_term": entry.get("presidential_term"),
        "congress_number": entry.get("congress_number"),
        "chamber": entry.get("chamber"),
        "state": entry.get("state"),
        "district": entry.get("district"),
        "agency": entry.get("agency"),
        "court": entry.get("court"),
        "expected_forms": entry.get("expected_forms", []),
        "source_url": source.get("search_url") or source.get("source_url"),
        "retrieval_mode": entry.get("retrieval_mode"),
        "promotion_status": entry.get("promotion_status"),
        "review_required": True,
        "source_search_terms": [term for term in search_terms if term],
    }


def sort_entries(entries: list[dict]) -> list[dict]:
    priority_rank = {
        "presidential_baseline": 0,
        "high_current_official": 1,
        "high_current_term": 2,
        "historical_backfill": 3,
    }
    return sorted(
        entries,
        key=lambda row: (
            priority_rank.get(row.get("priority"), 9),
            -(row.get("congress_number") or 0),
            row.get("presidential_term") or "",
            row.get("full_name") or "",
        ),
    )


def build_dataset() -> dict:
    queue = json.loads(QUEUE.read_text())
    sources = source_by_id()
    batches = []
    for source_id in SOURCE_ORDER:
        source = sources[source_id]
        entries = [row for row in queue.get("entries", []) if row.get("source_id") == source_id]
        selected = sort_entries(entries)[: BATCH_LIMITS[source_id]]
        acknowledgement_required = "acknowledged" in (source.get("access_mode") or "")
        candidates = [candidate_row(entry, source, rank) for rank, entry in enumerate(selected, start=1)]
        batch = {
            "batch_id": f"{source_id}:first-pass:{date.today().isoformat()}",
            "source_id": source_id,
            "source_name": source["name"],
            "branch": source["branch"],
            "generated_at": date.today().isoformat(),
            "batch_status": batch_status(source),
            "candidate_count": len(candidates),
            "total_queue_count": len(entries),
            "access_mode": source.get("access_mode"),
            "access_acknowledgement_required": acknowledgement_required,
            "review_required_before_public_trade": True,
            "source_url": source.get("source_url"),
            "search_url": source.get("search_url"),
            "instruction": source_instruction(source_id),
            "rights_note": source.get("rights_note"),
            "candidates": candidates,
        }
        batches.append(batch)

    status_counts = Counter(batch["batch_status"] for batch in batches)
    return {
        "generated_at": date.today().isoformat(),
        "schema_version": "disclosure-retrieval-batches-v1",
        "context_label": (
            "First-pass retrieval batches select real source-backed officials from the disclosure queue. "
            "They do not bypass official access acknowledgements and do not create public trade rows."
        ),
        "summary": {
            "batch_count": len(batches),
            "candidate_count": sum(batch["candidate_count"] for batch in batches),
            "status_counts": dict(sorted(status_counts.items())),
            "review_required_before_public_trade": True,
        },
        "batches": batches,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
