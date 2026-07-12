"""Build judiciary disclosure coverage targets without automating JEFS access."""

from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any


JUDICIAL_SOURCE_ID = "judicial-financial-disclosure"
JEFS_URL = "https://pub.jefs.uscourts.gov/"


def service_years(
    service_start: str | None,
    service_end: str | None,
    *,
    start_year: int,
    as_of: date,
) -> list[int]:
    if not service_start:
        return []
    first = max(start_year, date.fromisoformat(service_start).year)
    last = min(as_of.year, date.fromisoformat(service_end).year if service_end else as_of.year)
    return list(range(first, last + 1)) if first <= last else []


def build_judicial_disclosure_manifest(
    roster: dict[str, Any],
    *,
    start_year: int = 2009,
    as_of: date | None = None,
    roster_sha256: str | None = None,
) -> dict[str, Any]:
    as_of = as_of or date.today()
    judicial_people = {
        row["external_person_id"]: row
        for row in roster.get("people", [])
        if row.get("branch") == "Judicial"
    }
    judicial_roles = [
        row for row in roster.get("roles", []) if row.get("branch") == "Judicial"
    ]
    roles_by_person: dict[str, list[dict[str, Any]]] = {
        person_id: [] for person_id in judicial_people
    }
    for role in judicial_roles:
        roles_by_person.setdefault(role["external_person_id"], []).append(role)

    active_by_year: Counter[int] = Counter()
    officials = []
    for person_id, person in sorted(
        judicial_people.items(), key=lambda item: (item[1]["full_name"], item[0])
    ):
        periods = []
        covered_years: set[int] = set()
        courts: set[str] = set()
        for role in sorted(
            roles_by_person.get(person_id, []),
            key=lambda item: (item.get("service_start") or "", item["external_role_id"]),
        ):
            years = service_years(
                role.get("service_start"),
                role.get("service_end"),
                start_year=start_year,
                as_of=as_of,
            )
            covered_years.update(years)
            if role.get("court"):
                courts.add(role["court"])
            periods.append(
                {
                    "role_id": role["external_role_id"],
                    "role_category": role.get("role_category"),
                    "title": role.get("role_title") or role.get("office"),
                    "court": role.get("court"),
                    "service_start": role.get("service_start"),
                    "service_end": role.get("service_end"),
                    "source_url": role.get("source_url"),
                    "source_metadata": role.get("source_metadata") or {},
                }
            )
        for year in covered_years:
            active_by_year[year] += 1
        officials.append(
            {
                "official_id": person_id,
                "full_name": person["full_name"],
                "courts": sorted(courts),
                "service_periods": periods,
                "research_years": sorted(covered_years),
                "report_families": [
                    {
                        "name": "AO 10 annual financial disclosure report",
                        "coverage_semantics": "research_target_not_a_filing_assertion",
                    },
                    {
                        "name": "AO 10-T periodic transaction report",
                        "coverage_semantics": "conditional_on_reportable_transactions",
                    },
                ],
                "document_status": {
                    "state": "metadata_only_requester_governed",
                    "indexed_document_count": 0,
                    "parser_preview_transaction_count": 0,
                    "reviewed_trade_count": 0,
                    "absence_inference_allowed": False,
                },
                "request_search_keys": {
                    "name": person["full_name"],
                    "courts": sorted(courts),
                    "fjc_identifier": person_id.removeprefix("fjc:"),
                },
            }
        )

    return {
        "generated_at": as_of.isoformat(),
        "schema_version": "judicial-disclosure-manifest-v1",
        "source": {
            "source_id": JUDICIAL_SOURCE_ID,
            "portal_url": JEFS_URL,
            "roster_source": "Federal Judicial Center Article III service data",
            "roster_sha256": roster_sha256,
            "source_tier": "official",
        },
        "access_policy": {
            "mode": "requester_governed_acknowledged_portal",
            "automated_document_acquisition": False,
            "requester_identity_required": True,
            "terms_acknowledgement_required": True,
            "raw_document_required_before_parsing": True,
            "review_required_before_public_trade": True,
        },
        "interpretation_boundary": (
            "This manifest measures roster and service-year research coverage only. "
            "It does not assert that a report exists, that a report was required, or that "
            "an official did or did not make reportable transactions."
        ),
        "summary": {
            "official_count": len(officials),
            "role_count": len(judicial_roles),
            "research_year_count": len(active_by_year),
            "active_officials_by_year": {
                str(year): count for year, count in sorted(active_by_year.items())
            },
            "indexed_document_count": 0,
            "reviewed_trade_count": 0,
        },
        "officials": officials,
    }


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
