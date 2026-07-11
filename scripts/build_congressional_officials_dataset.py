#!/usr/bin/env python3
"""Build a Congress.gov-backed public-official roster for 111th-119th Congresses."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.congress_sources import (  # noqa: E402
    CongressGovClient,
    HOUSE_CURRENT_MEMBERS_XML_URL,
    SENATE_CURRENT_MEMBERS_XML_URL,
    chamber_label,
    congressional_member_dicts,
    display_name_from_congress_gov,
    fetch_house_current_members,
    fetch_senate_current_members,
    role_category_for_chamber,
    role_title_for_category,
    state_code,
)


OUTPUT = ROOT / "data" / "public_officials" / "congressional_service_terms.json"
CONGRESSES = {
    111: {
        "label": "111th Congress",
        "presidential_term": "obama-44",
        "administration": "Barack Obama Administration",
        "congress_start": "2009-01-03",
        "congress_end": "2011-01-03",
    },
    112: {
        "label": "112th Congress",
        "presidential_term": "obama-44",
        "administration": "Barack Obama Administration",
        "congress_start": "2011-01-03",
        "congress_end": "2013-01-03",
    },
    113: {
        "label": "113th Congress",
        "presidential_term": "obama-44",
        "administration": "Barack Obama Administration",
        "congress_start": "2013-01-03",
        "congress_end": "2015-01-03",
    },
    114: {
        "label": "114th Congress",
        "presidential_term": "obama-44",
        "administration": "Barack Obama Administration",
        "congress_start": "2015-01-03",
        "congress_end": "2017-01-03",
    },
    115: {
        "label": "115th Congress",
        "presidential_term": "trump-45",
        "administration": "Donald J. Trump Administration",
        "congress_start": "2017-01-03",
        "congress_end": "2019-01-03",
    },
    116: {
        "label": "116th Congress",
        "presidential_term": "trump-45",
        "administration": "Donald J. Trump Administration",
        "congress_start": "2019-01-03",
        "congress_end": "2021-01-03",
    },
    117: {
        "label": "117th Congress",
        "presidential_term": "biden-46",
        "administration": "Joseph R. Biden Administration",
        "congress_start": "2021-01-03",
        "congress_end": "2023-01-03",
    },
    118: {
        "label": "118th Congress",
        "presidential_term": "biden-46",
        "administration": "Joseph R. Biden Administration",
        "congress_start": "2023-01-03",
        "congress_end": "2025-01-03",
    },
    119: {
        "label": "119th Congress",
        "presidential_term": "trump-47",
        "administration": "Donald J. Trump Administration",
        "congress_start": "2025-01-03",
        "congress_end": "2027-01-03",
    },
}


def source_info(source_id: str) -> dict:
    return {
        "congress-gov-member-roster": {
            "id": "congress-gov-member-roster",
            "name": "Congress.gov Member API",
            "url": "https://api.congress.gov/v3/member/congress/{congress}",
            "landing_url": "https://api.congress.gov/",
            "source_tier": "official",
            "branch": "Legislative",
        },
        "house-clerk-current-members": {
            "id": "house-clerk-current-members",
            "name": "House Clerk Current Member XML",
            "url": HOUSE_CURRENT_MEMBERS_XML_URL,
            "source_tier": "official",
            "branch": "Legislative",
        },
        "senate-current-members": {
            "id": "senate-current-members",
            "name": "Senate.gov Current Senators XML",
            "url": SENATE_CURRENT_MEMBERS_XML_URL,
            "source_tier": "official",
            "branch": "Legislative",
        },
    }[source_id]


def chamber_for_congress(member: dict, congress: dict) -> str:
    """Return the chamber occupied at the start of the requested Congress.

    Congress.gov member-list rows describe a person's complete career. Using the
    last term therefore rewrites historical House service when a member later
    moves to the Senate. The list endpoint's district remains Congress-specific,
    so selecting the term active on the Congress start year restores the correct
    historical chamber without an extra member-detail request.
    """
    congress_start_year = int(congress["congress_start"][:4])
    terms = member.get("terms", {}).get("item", [])
    active_terms = []
    for term in terms:
        start_year = int(term.get("startYear") or 0)
        end_year = int(term["endYear"]) if term.get("endYear") else None
        if start_year <= congress_start_year and (end_year is None or end_year > congress_start_year):
            active_terms.append(term)
    selected = active_terms[-1] if active_terms else (terms[0] if terms else {})
    return chamber_label(selected.get("chamber"))


def role_start_for_member(member: dict, congress: dict, chamber: str) -> str:
    terms = member.get("terms", {}).get("item", [])
    years = sorted(
        int(term.get("startYear"))
        for term in terms
        if term.get("startYear") and chamber_label(term.get("chamber")) == chamber
    )
    if not years:
        return congress["congress_start"]
    congress_start_year = int(congress["congress_start"][:4])
    congress_end_year = int(congress["congress_end"][:4])
    eligible_years = [year for year in years if congress_start_year <= year < congress_end_year]
    start_year = eligible_years[0] if eligible_years else congress_start_year
    if start_year > congress_start_year:
        return f"{start_year}-01-03"
    return congress["congress_start"]


def role_from_member(member: dict, congress_number: int) -> dict:
    congress = CONGRESSES[congress_number]
    terms = member.get("terms", {}).get("item", [])
    chamber = chamber_for_congress(member, congress)
    state = state_code(member.get("state"))
    raw_district = member.get("district")
    if chamber == "Senate" or raw_district is None:
        district = None
    elif str(raw_district) == "0":
        district = "At Large"
    else:
        district = str(raw_district)
    role_category = role_category_for_chamber(chamber, state=state, district=district)
    source = source_info("congress-gov-member-roster")
    bioguide_id = member["bioguideId"]
    full_name = display_name_from_congress_gov(member["name"])
    district_slug = "senate" if chamber == "Senate" else f"district-{district}"
    return {
        "external_role_id": f"congress-gov:{congress_number}:{bioguide_id}:{chamber.lower()}:{district_slug}",
        "external_person_id": f"congress:{bioguide_id}",
        "full_name": full_name,
        "branch": "Legislative",
        "presidential_term": congress["presidential_term"],
        "administration": congress["administration"],
        "role_category": role_category,
        "role_title": role_title_for_category(role_category),
        "office": role_title_for_category(role_category),
        "agency": "United States Congress",
        "court": None,
        "service_start": role_start_for_member(member, congress, chamber),
        "service_end": None if congress_number == 119 else congress["congress_end"],
        "appointing_president": None,
        "source_id": source["id"],
        "source_name": source["name"],
        "source_url": f"https://api.congress.gov/v3/member/{bioguide_id}?format=json",
        "source_tier": source["source_tier"],
        "source_retrieved_at": date.today().isoformat(),
        "source_metadata": {
            "bioguide_id": bioguide_id,
            "congress_number": congress_number,
            "congress_label": congress["label"],
            "congress_start": congress["congress_start"],
            "congress_expected_end": congress["congress_end"],
            "chamber": chamber,
            "state": state,
            "state_name": member.get("state"),
            "district": district,
            "party": member.get("partyName"),
            "member_api_url": member.get("url"),
            "image_url": member.get("depiction", {}).get("imageUrl"),
            "update_date": member.get("updateDate"),
            "terms": terms,
        },
    }


def fetch_current_source_status() -> dict:
    status: dict[str, dict] = {}
    try:
        house = fetch_house_current_members()
        status["house-clerk-current-members"] = {
            "status": "ready",
            "member_count": len(house),
            "sample": congressional_member_dicts(house[:3]),
        }
    except Exception as exc:
        status["house-clerk-current-members"] = {"status": "error", "error": str(exc)}
    try:
        senate = fetch_senate_current_members()
        status["senate-current-members"] = {
            "status": "ready",
            "member_count": len(senate),
            "sample": congressional_member_dicts(senate[:3]),
        }
    except Exception as exc:
        status["senate-current-members"] = {"status": "error", "error": str(exc)}
    return status


def build_dataset(api_key: str | None = None) -> dict:
    client = CongressGovClient(api_key=api_key)
    roles = []
    counts_by_congress = {}
    for congress_number in CONGRESSES:
        members = client.members_by_congress(congress_number)
        counts_by_congress[str(congress_number)] = len(members)
        roles.extend(role_from_member(member, congress_number) for member in members)

    people = {}
    for role in roles:
        person = people.setdefault(
            role["external_person_id"],
            {
                "external_person_id": role["external_person_id"],
                "full_name": role["full_name"],
                "branch": "Legislative",
                "roles": [],
                "bioguide_id": role["source_metadata"]["bioguide_id"],
            },
        )
        person["roles"].append(role["external_role_id"])

    sources = []
    for source_id in [
        "congress-gov-member-roster",
        "house-clerk-current-members",
        "senate-current-members",
    ]:
        source = source_info(source_id)
        source_role_count = len(roles) if source_id == "congress-gov-member-roster" else 0
        sources.append({**source, "role_count": source_role_count})

    return {
        "generated_at": date.today().isoformat(),
        "scope": {
            "branch": "Legislative",
            "congress_numbers": list(CONGRESSES),
            "congresses": CONGRESSES,
            "description": (
                "Congressional public-official service roster for the 111th through "
                "119th Congresses, generated from Congress.gov member records."
            ),
        },
        "summary": {
            "person_count": len(people),
            "role_count": len(roles),
            "role_counts_by_chamber": dict(Counter(role["source_metadata"]["chamber"] for role in roles)),
            "role_counts_by_congress": counts_by_congress,
            "role_counts_by_party": dict(Counter(role["source_metadata"].get("party") for role in roles)),
            "role_counts_by_state": dict(Counter(role["source_metadata"].get("state") for role in roles)),
            "role_counts_by_term": dict(Counter(role["presidential_term"] for role in roles)),
            "role_counts_by_category": dict(Counter(role["role_category"] for role in roles)),
        },
        "people": sorted(people.values(), key=lambda item: item["full_name"]),
        "roles": sorted(
            roles,
            key=lambda role: (
                role["source_metadata"]["congress_number"],
                role["source_metadata"]["chamber"],
                role["source_metadata"].get("state") or "",
                role["source_metadata"].get("district") or "",
                role["full_name"],
            ),
        ),
        "sources": sources,
        "current_source_status": fetch_current_source_status(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.environ.get("CONGRESS_GOV_API_KEY"))
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("Set CONGRESS_GOV_API_KEY or pass --api-key to refresh congressional data.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(api_key=args.api_key), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
