#!/usr/bin/env python3
"""Build deterministic, unlabeled queues for human empirical validation."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import date
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISCLOSURE_OUTPUT = ROOT / "data" / "quality" / "disclosure_validation_queue.json"
EVENT_OUTPUT = ROOT / "data" / "quality" / "event_relevance_review_queue.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def stable_order(rows: list[dict], seed: str) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: hashlib.sha256(f"{seed}|{row['review_item_id']}".encode()).hexdigest(),
    )


def stratified_sample(rows: list[dict], limit: int, seed: str) -> list[dict]:
    groups: dict[str, deque] = defaultdict(deque)
    for row in stable_order(rows, seed):
        groups[row["stratum"]].append(row)
    selected = []
    names = sorted(groups)
    while names and len(selected) < limit:
        remaining = []
        for name in names:
            if groups[name] and len(selected) < limit:
                selected.append(groups[name].popleft())
            if groups[name]:
                remaining.append(name)
        names = remaining
    return selected


def review_fields() -> dict:
    return {
        "label_status": "unreviewed",
        "reviewer_id": None,
        "second_reviewer_id": None,
        "reviewed_at": None,
        "adjudication_status": "not_started",
    }


def disclosure_row(source_lane: str, row: dict, stratum: str) -> dict:
    document_id = row.get("document_id") or row.get("senate_report_uuid")
    return {
        "review_item_id": f"{source_lane}:{document_id}",
        "source_lane": source_lane,
        "document_id": document_id,
        "official_id": row.get("official_id"),
        "official_name": row.get("official_name") or row.get("full_name") or row.get("filer_name"),
        "filing_date": row.get("filing_date") or row.get("reported_date"),
        "filing_year": row.get("filing_year") or row.get("report_year"),
        "report_type": row.get("report_type") or row.get("filing_type"),
        "source_url": row.get("source_url"),
        "source_tier": row.get("source_tier"),
        "record_status": row.get("record_status") or row.get("parser_status"),
        "stratum": stratum,
        "expected_review": "Compare every material extracted field with the official source.",
        **review_fields(),
    }


def build_disclosure_queue(root: Path = ROOT) -> dict:
    house = load_json(root / "data/disclosures/house_disclosure_index.json").get("documents", [])
    senate = load_json(root / "data/disclosures/senate_disclosure_index.json").get("documents", [])
    executive = load_json(root / "data/disclosures/presidential_oge_documents.json").get("documents", [])
    judicial = load_json(root / "data/disclosures/judicial_disclosure_manifest.json")

    candidates = {
        "house": [
            disclosure_row(
                "house",
                row,
                f"house|{row.get('filing_year')}|{row.get('match_status')}|{row.get('filing_type_code')}",
            )
            for row in house
        ],
        "senate": [
            disclosure_row(
                "senate",
                row,
                f"senate|{row.get('filing_year')}|{row.get('report_format')}|{'amendment' if row.get('is_amendment') else 'original'}",
            )
            for row in senate
        ],
        "executive": [
            disclosure_row(
                "executive",
                row,
                f"executive|{row.get('presidential_term')}|{row.get('filing_type')}|{row.get('transaction_section_status')}",
            )
            for row in executive
        ],
        "judicial": [],
    }
    quotas = {"house": 120, "senate": 120, "executive": 30, "judicial": 30}
    selected = []
    lane_summary = {}
    for lane, quota in quotas.items():
        rows = stratified_sample(candidates[lane], quota, f"civicledger-gold-v1:{lane}")
        selected.extend(rows)
        lane_summary[lane] = {
            "target": quota,
            "available": len(candidates[lane]),
            "selected": len(rows),
            "unmet": max(0, quota - len(rows)),
        }

    return {
        "schema_version": "disclosure-validation-queue-v1",
        "generated_at": date.today().isoformat(),
        "status": "human_labeling_required",
        "target_sample_count": sum(quotas.values()),
        "selected_sample_count": len(selected),
        "human_reviewed_count": 0,
        "source_lane_summary": lane_summary,
        "interpretation_boundary": (
            "This queue defines empirical review work. Selection does not validate a parser output, "
            "and an unreviewed item must not be counted as correct."
        ),
        "judicial_gap": {
            "indexed_document_count": judicial.get("summary", {}).get("indexed_document_count", 0),
            "message": "Judicial sampling cannot begin until permitted source documents are acquired.",
        },
        "items": sorted(selected, key=lambda row: (row["source_lane"], row["review_item_id"])),
    }


def build_event_queue(root: Path = ROOT, limit: int = 200) -> dict:
    rows = []
    timeline_dir = root / "pages-site/data/partitions/timelines"
    for path in sorted(timeline_dir.glob("*.json")):
        official = load_json(path).get("official", {})
        for event in official.get("events", []):
            candidate = event.get("trade_context_candidate") is True
            item_id = f"{official.get('id')}:{event.get('id')}"
            rows.append(
                {
                    "review_item_id": item_id,
                    "official_id": official.get("id"),
                    "official_name": official.get("full_name"),
                    "branch": official.get("branch"),
                    "event_id": event.get("id"),
                    "event_date": event.get("date"),
                    "relationship_tier": event.get("relationship_tier"),
                    "relationship_reasons": event.get("relationship_reasons", []),
                    "official_involvement": event.get("official_involvement", []),
                    "trade_context_candidate": candidate,
                    "candidate_rank": event.get("candidate_rank"),
                    "candidate_score": event.get("candidate_score"),
                    "nearby_trade_ids": event.get("nearby_trade_ids", []),
                    "stratum": (
                        f"{official.get('branch')}|{event.get('relationship_tier')}|"
                        f"{'candidate' if candidate else 'not_candidate'}"
                    ),
                    "review_question": "Is this sourced relationship useful context for the nearby disclosed transactions?",
                    "relevance_label": None,
                    "review_note": None,
                    **review_fields(),
                }
            )
    selected = stratified_sample(rows, limit, "civicledger-event-review-v1")
    return {
        "schema_version": "event-relevance-review-queue-v1",
        "generated_at": date.today().isoformat(),
        "status": "human_labeling_required",
        "target_sample_count": limit,
        "available_relationship_count": len(rows),
        "selected_sample_count": len(selected),
        "human_reviewed_count": 0,
        "sample_counts_by_stratum": dict(sorted(Counter(row["stratum"] for row in selected).items())),
        "interpretation_boundary": (
            "Reviewers label contextual usefulness only. They do not label causation, intent, knowledge, "
            "benefit, wrongdoing, or investigative truth."
        ),
        "items": sorted(selected, key=lambda row: row["review_item_id"]),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disclosure-output", type=Path, default=DISCLOSURE_OUTPUT)
    parser.add_argument("--event-output", type=Path, default=EVENT_OUTPUT)
    args = parser.parse_args()

    disclosure = build_disclosure_queue()
    event = build_event_queue()
    write_json(args.disclosure_output, disclosure)
    write_json(args.event_output, event)
    print(
        f"Wrote {disclosure['selected_sample_count']} disclosure and "
        f"{event['selected_sample_count']} event review items"
    )


if __name__ == "__main__":
    main()
