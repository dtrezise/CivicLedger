"""Build executive OGE disclosure coverage targets from dated official roles."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any


OGE_COLLECTION_URL = (
    "https://www.oge.gov/web/oge.nsf/"
    "Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm="
)


def _years(start: str | None, end: str | None, *, first_year: int, as_of: date) -> list[int]:
    if not start:
        return []
    start_value = max(first_year, date.fromisoformat(start).year)
    end_value = min(as_of.year, date.fromisoformat(end).year if end else as_of.year)
    return list(range(start_value, end_value + 1)) if start_value <= end_value else []


def build_executive_disclosure_manifest(
    roster: dict[str, Any],
    presidential_documents: dict[str, Any],
    *,
    first_year: int = 2009,
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or date.today()
    people = {
        row["external_person_id"]: row
        for row in roster.get("people", [])
        if row.get("branch") == "Executive"
    }
    roles = [row for row in roster.get("roles", []) if row.get("branch") == "Executive"]
    roles_by_person: dict[str, list[dict[str, Any]]] = {person_id: [] for person_id in people}
    for role in roles:
        roles_by_person.setdefault(role["external_person_id"], []).append(role)

    documents_by_official: dict[str, list[dict[str, Any]]] = {}
    for document in presidential_documents.get("documents", []):
        documents_by_official.setdefault(document.get("official_id", ""), []).append(document)

    officials = []
    category_counts: Counter[str] = Counter()
    indexed_document_count = 0
    for person_id, person in sorted(people.items(), key=lambda item: (item[1]["full_name"], item[0])):
        person_roles = []
        coverage_years: set[int] = set()
        agencies: set[str] = set()
        offices: set[str] = set()
        for role in sorted(
            roles_by_person.get(person_id, []),
            key=lambda item: (item.get("service_start") or "", item["external_role_id"]),
        ):
            coverage_years.update(
                _years(
                    role.get("service_start"),
                    role.get("service_end"),
                    first_year=first_year,
                    as_of=as_of,
                )
            )
            category_counts[role.get("role_category") or "uncategorized"] += 1
            if role.get("agency"):
                agencies.add(role["agency"])
            if role.get("office"):
                offices.add(role["office"])
            person_roles.append(
                {
                    "role_id": role["external_role_id"],
                    "presidential_term": role.get("presidential_term"),
                    "role_category": role.get("role_category"),
                    "title": role.get("role_title") or role.get("office"),
                    "office": role.get("office"),
                    "agency": role.get("agency"),
                    "service_start": role.get("service_start"),
                    "service_end": role.get("service_end"),
                    "source_url": role.get("source_url"),
                }
            )
        linked_documents = sorted(
            documents_by_official.get(person_id, []),
            key=lambda row: (row.get("filing_date") or "", row.get("document_id") or ""),
        )
        indexed_document_count += len(linked_documents)
        officials.append(
            {
                "official_id": person_id,
                "full_name": person["full_name"],
                "offices": sorted(offices),
                "agencies": sorted(agencies),
                "service_periods": person_roles,
                "research_years": sorted(coverage_years),
                "report_families": [
                    {
                        "name": "OGE Form 278e",
                        "sections": ["positions", "assets_and_income", "transactions", "liabilities", "agreements"],
                        "coverage_semantics": "annual_new_entrant_or_termination_as_applicable",
                    },
                    {
                        "name": "OGE Form 278-T",
                        "sections": ["periodic_transactions"],
                        "coverage_semantics": "conditional_on_reportable_transactions",
                    },
                ],
                "document_status": {
                    "state": "official_documents_indexed_review_gated" if linked_documents else "metadata_only_collection_search_pending",
                    "indexed_document_count": len(linked_documents),
                    "reviewed_trade_count": 0,
                    "absence_inference_allowed": False,
                },
                "indexed_documents": [
                    {
                        key: document.get(key)
                        for key in (
                            "document_id",
                            "document_type",
                            "filing_date",
                            "source_url",
                            "file_sha256",
                            "document_status",
                        )
                        if document.get(key) is not None
                    }
                    for document in linked_documents
                ],
            }
        )

    return {
        "generated_at": as_of.isoformat(),
        "schema_version": "executive-oge-disclosure-manifest-v1",
        "source": {
            "source_id": "oge-individual-disclosures",
            "collection_url": OGE_COLLECTION_URL,
            "source_tier": "official",
        },
        "collection_policy": {
            "raw_document_required": True,
            "content_addressed_archive_required": True,
            "review_required_before_public_trade": True,
            "amendments_preserved": True,
            "sections_kept_semantically_separate": True,
        },
        "interpretation_boundary": (
            "Roster coverage and an empty document list do not establish that an official "
            "filed no report or made no reportable transaction."
        ),
        "summary": {
            "official_count": len(officials),
            "role_count": len(roles),
            "role_category_counts": dict(sorted(category_counts.items())),
            "officials_with_indexed_documents": sum(
                1 for row in officials if row["document_status"]["indexed_document_count"]
            ),
            "indexed_document_count": indexed_document_count,
            "reviewed_trade_count": 0,
        },
        "officials": officials,
    }
