#!/usr/bin/env python3
"""Build branch-aware disclosure ingestion queue for federal officials."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
PRESIDENTIAL_OGE_STATUS = ROOT / "data" / "disclosures" / "presidential_oge_disclosure_status.json"
OUTPUT = ROOT / "data" / "disclosures" / "disclosure_ingestion_queue.json"


SOURCE_FOR_BRANCH = {
    "House": "house-financial-disclosure",
    "Senate": "senate-public-financial-disclosure",
}


def expected_forms_for_role(role: dict) -> list[str]:
    category = role.get("role_category")
    branch = role.get("branch")
    chamber = role.get("source_metadata", {}).get("chamber")
    if branch == "Legislative" and chamber in {"House", "Senate"}:
        return ["Annual Financial Disclosure", "Periodic Transaction Report"]
    if branch == "Judicial":
        return ["Judicial Financial Disclosure Report", "AO 10-T Periodic Transaction Report"]
    if branch == "Executive" and category in {"cabinet", "cabinet_level", "elected_executive"}:
        return ["OGE Form 278e", "OGE Form 278-T"]
    return ["Financial Disclosure", "Periodic Transaction Report"]


def source_for_role(role: dict) -> str:
    branch = role.get("branch")
    metadata = role.get("source_metadata", {})
    chamber = metadata.get("chamber")
    if branch == "Legislative":
        return SOURCE_FOR_BRANCH.get(chamber, "congressional-financial-disclosure")
    if branch == "Executive":
        return "oge-individual-disclosures"
    if branch == "Judicial":
        return "judicial-financial-disclosure"
    return "unknown-source"


def retrieval_mode_for_role(role: dict) -> str:
    source_id = source_for_role(role)
    if source_id == "house-financial-disclosure":
        return "official_house_clerk_search"
    if source_id == "senate-public-financial-disclosure":
        return "official_senate_acknowledged_search"
    if source_id == "oge-individual-disclosures":
        return "official_oge_collection_search"
    if source_id == "judicial-financial-disclosure":
        return "official_judicial_acknowledged_request"
    return "official_source_review"


def priority_for_role(role: dict) -> str:
    if role.get("service_end") is None:
        return "high_current_official"
    if role.get("presidential_term") == "trump-47":
        return "high_current_term"
    return "historical_backfill"


def build_queue() -> dict:
    officials = json.loads(PUBLIC_OFFICIALS.read_text())
    presidential_oge = json.loads(PRESIDENTIAL_OGE_STATUS.read_text())
    entries = []
    seen = set()

    for status in presidential_oge.get("officials", []):
        key = ("presidential-oge", status["official_id"], status["presidential_term"])
        entries.append(
            {
                "queue_id": f"oge:{status['presidential_term']}:{status['official_id']}",
                "official_id": status["official_id"],
                "full_name": status["full_name"],
                "branch": "Executive",
                "role_category": "elected_executive",
                "presidential_term": status["presidential_term"],
                "source_id": "oge-individual-disclosures",
                "source_status": status["source_status"],
                "expected_forms": status["expected_forms"],
                "retrieval_mode": "official_oge_collection_search",
                "review_required": True,
                "promotion_status": "raw_document_required",
                "priority": "high_current_official" if status.get("service_end") is None else "presidential_baseline",
                "notes": status["availability_note"],
            }
        )
        seen.add(key)

    for role in officials.get("roles", []):
        branch = role.get("branch")
        category = role.get("role_category")
        if branch == "Legislative" and category not in {"representative", "delegate", "resident_commissioner", "senator"}:
            continue
        if branch == "Executive" and category not in {"cabinet", "cabinet_level", "elected_executive"}:
            continue
        if branch == "Judicial" and category not in {"article_iii_judge", "supreme_court"}:
            continue

        metadata = role.get("source_metadata", {})
        chamber = metadata.get("chamber")
        congress_number = metadata.get("congress_number")
        source_id = source_for_role(role)
        key = (
            source_id,
            role["external_person_id"],
            role.get("presidential_term"),
            chamber,
            congress_number,
            role.get("role_category"),
        )
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "queue_id": ":".join(str(part) for part in key if part),
                "official_id": role["external_person_id"],
                "full_name": role["full_name"],
                "branch": branch,
                "role_category": category,
                "role_title": role.get("role_title"),
                "office": role.get("office"),
                "agency": role.get("agency"),
                "court": role.get("court"),
                "presidential_term": role.get("presidential_term"),
                "congress_number": congress_number,
                "chamber": chamber,
                "state": metadata.get("state"),
                "district": metadata.get("district"),
                "source_id": source_id,
                "source_status": "source_search_required",
                "expected_forms": expected_forms_for_role(role),
                "retrieval_mode": retrieval_mode_for_role(role),
                "review_required": True,
                "promotion_status": "raw_document_required",
                "priority": priority_for_role(role),
                "source_url": role.get("source_url"),
            }
        )

    counts_by_branch = Counter(row["branch"] for row in entries)
    counts_by_source = Counter(row["source_id"] for row in entries)
    counts_by_term = Counter(row.get("presidential_term") or "unknown" for row in entries)
    counts_by_congress = Counter(str(row["congress_number"]) for row in entries if row.get("congress_number"))
    counts_by_priority = Counter(row["priority"] for row in entries)
    current_entries = [row for row in entries if row["priority"] in {"high_current_official", "high_current_term"}]
    return {
        "generated_at": date.today().isoformat(),
        "schema_version": "disclosure-ingestion-queue-v1",
        "context_label": (
            "Branch-aware queue for raw disclosure retrieval and review. Queue rows are not trade records; "
            "public trade rows require raw document archive, parser output, and reviewer promotion."
        ),
        "summary": {
            "queue_item_count": len(entries),
            "current_or_current_term_queue_item_count": len(current_entries),
            "counts_by_branch": dict(sorted(counts_by_branch.items())),
            "counts_by_source": dict(sorted(counts_by_source.items())),
            "counts_by_term": dict(sorted(counts_by_term.items())),
            "counts_by_congress": dict(sorted(counts_by_congress.items())),
            "counts_by_priority": dict(sorted(counts_by_priority.items())),
        },
        "entries": sorted(
            entries,
            key=lambda row: (
                row["branch"],
                row.get("presidential_term") or "",
                row.get("congress_number") or 0,
                row["full_name"],
                row["source_id"],
            ),
        ),
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_queue(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
