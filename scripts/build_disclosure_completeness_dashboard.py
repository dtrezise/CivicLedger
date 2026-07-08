#!/usr/bin/env python3
"""Build public data-completeness dashboard by branch, term, and source."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
QUEUE = ROOT / "data" / "disclosures" / "disclosure_ingestion_queue.json"
RAW_ARCHIVE = ROOT / "data" / "disclosures" / "raw_document_archive_index.json"
PROMOTIONS = ROOT / "data" / "disclosures" / "reviewed_disclosure_promotions.json"
PRODUCTION_PROMOTIONS = ROOT / "data" / "disclosures" / "production_trade_promotions.json"
RETRIEVAL_BATCHES = ROOT / "data" / "disclosures" / "disclosure_retrieval_batches.json"
STALE_ALERTS = ROOT / "data" / "disclosures" / "source_staleness_alerts.json"
OUTPUT = ROOT / "data" / "disclosures" / "disclosure_completeness_dashboard.json"


def read_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text())


def disclosure_source_for_role(role: dict) -> str:
    branch = role.get("branch")
    metadata = role.get("source_metadata", {})
    if branch == "Legislative":
        if metadata.get("chamber") == "House":
            return "house-financial-disclosure"
        if metadata.get("chamber") == "Senate":
            return "senate-public-financial-disclosure"
        return "congressional-financial-disclosure"
    if branch == "Executive":
        return "oge-individual-disclosures"
    if branch == "Judicial":
        return "judicial-financial-disclosure"
    return "unknown-source"


def key_for(row: dict, *, role_row: bool = False) -> tuple[str, str, str]:
    return (
        row.get("branch") or "Unknown",
        row.get("presidential_term") or "unknown-term",
        disclosure_source_for_role(row) if role_row else row.get("source_id") or "unknown-source",
    )


def build_dataset() -> dict:
    officials = read_json(PUBLIC_OFFICIALS, {"roles": [], "summary": {}})
    queue = read_json(QUEUE, {"entries": [], "summary": {}})
    raw_archive = read_json(RAW_ARCHIVE, {"documents": [], "summary": {}})
    promotions = read_json(PROMOTIONS, {"promotions": [], "summary": {}})
    production_promotions = read_json(PRODUCTION_PROMOTIONS, {"summary": {}})
    retrieval_batches = read_json(RETRIEVAL_BATCHES, {"batches": [], "summary": {}})
    stale_alerts = read_json(STALE_ALERTS, {"alerts": [], "summary": {}})

    role_counts = Counter(key_for(role, role_row=True) for role in officials.get("roles", []))
    people_by_key = defaultdict(set)
    for role in officials.get("roles", []):
        people_by_key[key_for(role, role_row=True)].add(role.get("external_person_id"))
    queue_counts = Counter(key_for(row) for row in queue.get("entries", []))
    current_queue_counts = Counter(
        key_for(row)
        for row in queue.get("entries", [])
        if row.get("priority") in {"high_current_official", "high_current_term"}
    )
    raw_counts_by_source = Counter(
        row.get("source_id") for row in raw_archive.get("documents", []) if row.get("archive_status") == "archived"
    )
    reviewed_count = production_promotions.get("summary", {}).get("reviewed_public_trade_count", 0)
    batch_by_source = {batch["source_id"]: batch for batch in retrieval_batches.get("batches", [])}
    alerts_by_source = Counter(row.get("source_id") or "global" for row in stale_alerts.get("alerts", []) if row.get("status") == "open")

    rows = []
    all_keys = sorted(set(role_counts) | set(queue_counts))
    for branch, term, source_id in all_keys:
        role_count = role_counts[(branch, term, source_id)]
        queue_count = queue_counts[(branch, term, source_id)]
        raw_count = 0
        source_pipeline_started = raw_counts_by_source[source_id] > 0
        readiness = "needs_raw_documents"
        if raw_count:
            readiness = "raw_archive_started"
        elif source_pipeline_started:
            readiness = "source_pipeline_started"
        if reviewed_count and raw_count:
            readiness = "reviewed_promotions_started"
        rows.append(
            {
                "branch": branch,
                "presidential_term": term,
                "source_id": source_id,
                "official_count": len(people_by_key[(branch, term, source_id)]),
                "role_count": role_count,
                "queue_item_count": queue_count,
                "current_queue_item_count": current_queue_counts[(branch, term, source_id)],
                "archived_raw_document_count": raw_count,
                "reviewed_public_trade_count": 0,
                "readiness_status": readiness,
                "source_pipeline_started": source_pipeline_started,
                "retrieval_batch_status": batch_by_source.get(source_id, {}).get("batch_status", "not_batched"),
                "retrieval_candidate_count": batch_by_source.get(source_id, {}).get("candidate_count", 0),
                "open_alert_count": alerts_by_source[source_id] + alerts_by_source["global"],
                "review_required_before_public_trade": True,
            }
        )

    branch_rows = []
    branch_sources = defaultdict(set)
    for row in rows:
        branch_sources[row["branch"]].add(row["source_id"])
    for branch in sorted({row["branch"] for row in rows}):
        branch_items = [row for row in rows if row["branch"] == branch]
        branch_raw_count = sum(raw_counts_by_source[source_id] for source_id in branch_sources[branch])
        branch_candidate_count = sum(
            batch_by_source.get(source_id, {}).get("candidate_count", 0)
            for source_id in branch_sources[branch]
        )
        branch_rows.append(
            {
                "branch": branch,
                "official_count": sum(row["official_count"] for row in branch_items),
                "role_count": sum(row["role_count"] for row in branch_items),
                "queue_item_count": sum(row["queue_item_count"] for row in branch_items),
                "archived_raw_document_count": branch_raw_count,
                "reviewed_public_trade_count": sum(row["reviewed_public_trade_count"] for row in branch_items),
                "retrieval_candidate_count": branch_candidate_count,
                "open_alert_count": sum(row["open_alert_count"] for row in branch_items),
                "readiness_status": "raw_archive_started"
                if branch_raw_count
                else "needs_raw_documents",
            }
        )

    return {
        "generated_at": date.today().isoformat(),
        "schema_version": "disclosure-completeness-dashboard-v1",
        "context_label": (
            "Completeness dashboard tracks source-backed role scope, queued source searches, raw archived documents, "
            "and reviewed public trade rows by branch, term, and source."
        ),
        "summary": {
            "branch_count": len(branch_rows),
            "completeness_row_count": len(rows),
            "queue_item_count": queue.get("summary", {}).get("queue_item_count", 0),
            "archived_raw_document_count": raw_archive.get("summary", {}).get("archived_document_count", 0),
            "reviewed_fixture_promotion_count": promotions.get("summary", {}).get("reviewed_fixture_promotion_count", 0),
            "reviewed_public_trade_count": reviewed_count,
            "retrieval_batch_count": retrieval_batches.get("summary", {}).get("batch_count", 0),
            "retrieval_candidate_count": retrieval_batches.get("summary", {}).get("candidate_count", 0),
            "open_warning_count": stale_alerts.get("summary", {}).get("open_warning_count", 0),
            "review_required_before_public_trade": True,
        },
        "branches": branch_rows,
        "rows": rows,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
