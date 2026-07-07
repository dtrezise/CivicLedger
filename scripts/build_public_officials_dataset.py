#!/usr/bin/env python3
"""Build the first source-backed public officials dataset.

The generated JSON is committed so local/dev/Page builds do not depend on live
network access. Re-run this script when refreshing executive Cabinet pages or
the FJC Article III export.
"""

from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "public_officials" / "public_official_roles.json"
CONGRESSIONAL_OUTPUT = ROOT / "data" / "public_officials" / "congressional_service_terms.json"

FJC_SERVICE_CSV = "https://www.fjc.gov/sites/default/files/history/federal-judicial-service.csv"
FJC_EXPORT_PAGE = (
    "https://www.fjc.gov/history/judges/"
    "biographical-directory-article-iii-federal-judges-export"
)
BIDEN_CABINET_PAGE = "https://bidenwhitehouse.archives.gov/administration/cabinet/"
TRUMP45_CABINET_PAGE = "https://trumpwhitehouse.archives.gov/the-trump-administration/the-cabinet/"
TRUMP47_CABINET_PAGE = "https://www.whitehouse.gov/administration/cabinet/"
TRUMP47_NOMINATION_PAGE = (
    "https://www.whitehouse.gov/presidential-actions/2025/01/"
    "cabinet-and-cabinet-level-appointments/"
)

TERMS = {
    "trump-45": {
        "label": "Trump 45",
        "administration": "Donald J. Trump Administration",
        "term_start": "2017-01-20",
        "term_end": "2021-01-20",
        "president": "Donald J. Trump",
    },
    "biden-46": {
        "label": "Biden 46",
        "administration": "Joseph R. Biden Administration",
        "term_start": "2021-01-20",
        "term_end": "2025-01-20",
        "president": "Joseph R. Biden",
    },
    "trump-47": {
        "label": "Trump 47",
        "administration": "Donald J. Trump Administration",
        "term_start": "2025-01-20",
        "term_end": None,
        "president": "Donald J. Trump",
    },
}

EXECUTIVE_DEPARTMENTS = {
    "Secretary of Agriculture": "Department of Agriculture",
    "Secretary of Commerce": "Department of Commerce",
    "Secretary of Defense": "Department of Defense",
    "Secretary of Education": "Department of Education",
    "Secretary of Energy": "Department of Energy",
    "Secretary of Health and Human Services": "Department of Health and Human Services",
    "Secretary of Homeland Security": "Department of Homeland Security",
    "Secretary of Housing and Urban Development": "Department of Housing and Urban Development",
    "Secretary of Labor": "Department of Labor",
    "Secretary of State": "Department of State",
    "Secretary of the Interior": "Department of the Interior",
    "Secretary of the Treasury": "Department of the Treasury",
    "Secretary of Transportation": "Department of Transportation",
    "Secretary of Veterans Affairs": "Department of Veterans Affairs",
    "Attorney General": "Department of Justice",
    "Acting Attorney General": "Department of Justice",
    "Secretary of War": "Department of Defense",
}

TRUMP45_ARCHIVE_ROWS = [
    ("Sonny Perdue", "Secretary of Agriculture"),
    ("Jeffrey Rosen", "Acting Attorney General"),
    ("Gina Haspel", "Director of the Central Intelligence Agency"),
    ("Wilbur L. Ross, Jr.", "Secretary of Commerce"),
    ("Christopher C. Miller", "Acting Secretary of Defense"),
    ("Elisabeth Prince DeVos", "Secretary of Education"),
    ("Dan Brouillette", "Secretary of Energy"),
    ("Andrew Wheeler", "Administrator of the Environmental Protection Agency"),
    ("Alex Azar", "Secretary of Health and Human Services"),
    ("Chad Wolf", "Acting Secretary of Homeland Security"),
    ("Benjamin S. Carson, Sr.", "Secretary of Housing and Urban Development"),
    ("David Bernhardt", "Secretary of the Interior"),
    ("Eugene Scalia", "Secretary of Labor"),
    ("Russ Vought", "Director of the Office of Management and Budget"),
    ("John Ratcliffe", "Director of National Intelligence"),
    ("Jovita Carranza", "Administrator of the Small Business Administration"),
    ("Mike Pompeo", "Secretary of State"),
    ("Elaine L. Chao", "Secretary of Transportation"),
    ("Steven T. Mnuchin", "Secretary of the Treasury"),
    ("Robert Wilkie", "Secretary of Veterans Affairs"),
    ("Michael R. Pence", "Vice President"),
    ("Mark Meadows", "White House Chief of Staff"),
]


class HeadingPairParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture: str | None = None
        self.buffer: list[str] = []
        self.pending_h3: str | None = None
        self.pairs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"h3", "h4"}:
            self.capture = tag
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            value = " ".join(data.split())
            if value:
                self.buffer.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag != self.capture:
            return
        text = html.unescape(" ".join(self.buffer).strip())
        if tag == "h3":
            self.pending_h3 = text
        elif tag == "h4" and self.pending_h3 and text:
            self.pairs.append((self.pending_h3, text))
            self.pending_h3 = None
        self.capture = None
        self.buffer = []


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "CivicLedger data refresh"})
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def normalize_role(value: str) -> str:
    return " ".join(value.split()).strip()


def normalize_name(value: str) -> str:
    value = normalize_role(value)
    return re.sub(r"^(Dr\.|General)\s+", "", value).strip()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def source_info(source_id: str) -> dict:
    sources = {
        "fjc-article-iii-service": {
            "name": "Federal Judicial Center Article III Federal Judicial Service CSV",
            "url": FJC_SERVICE_CSV,
            "landing_url": FJC_EXPORT_PAGE,
            "source_tier": "official",
            "branch": "Judicial",
        },
        "biden-46-cabinet-archive": {
            "name": "Biden White House Archive Cabinet page",
            "url": BIDEN_CABINET_PAGE,
            "source_tier": "official_archive",
            "branch": "Executive",
        },
        "trump-45-cabinet-archive": {
            "name": "Trump White House Archive Cabinet page",
            "url": TRUMP45_CABINET_PAGE,
            "source_tier": "official_archive",
            "branch": "Executive",
        },
        "trump-47-current-cabinet": {
            "name": "White House Cabinet page",
            "url": TRUMP47_CABINET_PAGE,
            "source_tier": "official",
            "branch": "Executive",
        },
        "trump-47-cabinet-nominations": {
            "name": "President Trump Cabinet and Cabinet-Level Appointments",
            "url": TRUMP47_NOMINATION_PAGE,
            "source_tier": "official",
            "branch": "Executive",
        },
        "congress-gov-member-roster": {
            "name": "Congress.gov Member API",
            "url": "https://api.congress.gov/v3/member/congress/{congress}",
            "landing_url": "https://api.congress.gov/",
            "source_tier": "official",
            "branch": "Legislative",
        },
        "house-clerk-current-members": {
            "name": "House Clerk Current Member XML",
            "url": "https://clerk.house.gov/xml/lists/memberdata.xml",
            "source_tier": "official",
            "branch": "Legislative",
        },
        "senate-current-members": {
            "name": "Senate.gov Current Senators XML",
            "url": "https://www.senate.gov/general/contact_information/senators_cfm.xml",
            "source_tier": "official",
            "branch": "Legislative",
        },
    }
    return sources[source_id]


def agency_for_role(role_title: str) -> str | None:
    role_title = normalize_role(role_title)
    if role_title.startswith("Acting Secretary of "):
        role_title = "Secretary of " + role_title.removeprefix("Acting Secretary of ")
    return EXECUTIVE_DEPARTMENTS.get(role_title)


def executive_role_category(role_title: str) -> str:
    if role_title in {"President", "Vice President"}:
        return "elected_executive"
    if agency_for_role(role_title):
        return "cabinet"
    return "cabinet_level"


def make_role(
    *,
    person_name: str,
    role_title: str,
    branch: str,
    presidential_term: str,
    role_category: str,
    source_id: str,
    source_row_id: str,
    office: str | None = None,
    agency: str | None = None,
    court: str | None = None,
    service_start: str | None = None,
    service_end: str | None = None,
    appointing_president: str | None = None,
    source_metadata: dict | None = None,
) -> dict:
    person_name = normalize_name(person_name)
    role_title = normalize_role(role_title)
    source = source_info(source_id)
    person_id_prefix = "fjc" if branch == "Judicial" else "exec"
    person_slug = slugify(person_name)
    role_slug = slugify(f"{presidential_term}-{source_row_id}-{person_name}-{role_title}")
    return {
        "external_role_id": f"{source_id}:{role_slug}",
        "external_person_id": f"{person_id_prefix}:{person_slug}",
        "full_name": person_name,
        "branch": branch,
        "presidential_term": presidential_term,
        "administration": TERMS[presidential_term]["administration"],
        "role_category": role_category,
        "role_title": role_title,
        "office": office or role_title,
        "agency": agency,
        "court": court,
        "service_start": service_start,
        "service_end": service_end,
        "appointing_president": appointing_president,
        "source_id": source_id,
        "source_name": source["name"],
        "source_url": source["url"],
        "source_tier": source["source_tier"],
        "source_retrieved_at": date.today().isoformat(),
        "source_metadata": source_metadata or {},
    }


def parse_heading_pairs(url: str) -> list[tuple[str, str]]:
    parser = HeadingPairParser()
    parser.feed(fetch_text(url))
    return parser.pairs


def elected_executive_rows() -> list[dict]:
    rows = []
    elected = {
        "trump-45": [
            ("Donald J. Trump", "President"),
            ("Michael R. Pence", "Vice President"),
        ],
        "biden-46": [
            ("Joseph R. Biden", "President"),
            ("Kamala Harris", "Vice President"),
        ],
        "trump-47": [
            ("Donald J. Trump", "President"),
            ("JD Vance", "Vice President"),
        ],
    }
    source_by_term = {
        "trump-45": "trump-45-cabinet-archive",
        "biden-46": "biden-46-cabinet-archive",
        "trump-47": "trump-47-current-cabinet",
    }
    for term, people in elected.items():
        for index, (name, role_title) in enumerate(people, start=1):
            rows.append(
                make_role(
                    person_name=name,
                    role_title=role_title,
                    branch="Executive",
                    presidential_term=term,
                    role_category="elected_executive",
                    source_id=source_by_term[term],
                    source_row_id=f"elected-{index}",
                    service_start=TERMS[term]["term_start"],
                    service_end=TERMS[term]["term_end"],
                    source_metadata={"term_label": TERMS[term]["label"]},
                )
            )
    return rows


def executive_rows() -> list[dict]:
    rows = elected_executive_rows()

    for index, (name, role_title) in enumerate(TRUMP45_ARCHIVE_ROWS, start=1):
        rows.append(
            make_role(
                person_name=name,
                role_title=role_title,
                branch="Executive",
                presidential_term="trump-45",
                role_category=executive_role_category(role_title),
                source_id="trump-45-cabinet-archive",
                source_row_id=f"archive-cabinet-{index}",
                agency=agency_for_role(role_title),
                service_start="2017-01-20",
                service_end="2021-01-20",
                source_metadata={"source_scope": "Archived Cabinet page roster"},
            )
        )

    for index, (name, role_title) in enumerate(parse_heading_pairs(BIDEN_CABINET_PAGE), start=1):
        if name == "Mobile Menu Overlay":
            continue
        rows.append(
            make_role(
                person_name=name,
                role_title=role_title.title() if role_title.isupper() else role_title,
                branch="Executive",
                presidential_term="biden-46",
                role_category=executive_role_category(role_title.title() if role_title.isupper() else role_title),
                source_id="biden-46-cabinet-archive",
                source_row_id=f"archive-cabinet-{index}",
                agency=agency_for_role(role_title.title() if role_title.isupper() else role_title),
                service_start="2021-01-20",
                service_end="2025-01-20",
                source_metadata={"source_scope": "Archived Cabinet page roster"},
            )
        )

    for index, (name, role_title) in enumerate(parse_heading_pairs(TRUMP47_CABINET_PAGE), start=1):
        if name in {"About", "Media", "Initiatives", "Subscribe to the WH Newsletter"}:
            continue
        rows.append(
            make_role(
                person_name=name,
                role_title=role_title,
                branch="Executive",
                presidential_term="trump-47",
                role_category=executive_role_category(role_title),
                source_id="trump-47-current-cabinet",
                source_row_id=f"current-cabinet-{index}",
                agency=agency_for_role(role_title),
                service_start="2025-01-20",
                service_end=None,
                source_metadata={"source_scope": "Current Cabinet page roster"},
            )
        )

    return rows


def judge_display_name(value: str) -> str:
    pieces = [piece.strip() for piece in value.split(",") if piece.strip()]
    if len(pieces) == 1:
        return pieces[0]
    last_name, rest = pieces[0], pieces[1:]
    suffix = ""
    if rest and re.fullmatch(r"(Jr\.?|Sr\.?|I{2,3}|IV|V)", rest[-1]):
        suffix = rest.pop()
    display = f"{' '.join(rest)} {last_name}".strip()
    if suffix:
        display = f"{display}, {suffix}"
    return display


def judicial_term(row: dict) -> str | None:
    president = row["Appointing President"]
    row_date = (
        parse_date(row.get("Commission Date"))
        or parse_date(row.get("Confirmation Date"))
        or parse_date(row.get("Nomination Date"))
    )
    if president == "Joseph R. Biden" and row_date and date(2021, 1, 20) <= row_date < date(2025, 1, 20):
        return "biden-46"
    if president == "Donald J. Trump" and row_date:
        if row_date < date(2021, 1, 20):
            return "trump-45"
        if row_date >= date(2025, 1, 20):
            return "trump-47"
    return None


def judicial_rows() -> list[dict]:
    text = fetch_text(FJC_SERVICE_CSV)
    rows = []
    for index, row in enumerate(csv.DictReader(text.splitlines()), start=1):
        term = judicial_term(row)
        if not term:
            continue
        court_type = row["Court Type"]
        court_name = row["Court Name"]
        appointment_title = row["Appointment Title"]
        is_supreme = "Supreme Court" in court_type or "Supreme Court" in court_name
        role_title = f"{appointment_title}, {court_name}"
        rows.append(
            make_role(
                person_name=judge_display_name(row["Judge Name"]),
                role_title=role_title,
                branch="Judicial",
                presidential_term=term,
                role_category="supreme_court" if is_supreme else "article_iii_judge",
                source_id="fjc-article-iii-service",
                source_row_id=f"{row['nid']}-{row['Sequence']}-{index}",
                court=court_name,
                service_start=row.get("Commission Date") or row.get("Confirmation Date") or row.get("Nomination Date") or None,
                service_end=row.get("Termination Date") or None,
                appointing_president=row["Appointing President"],
                source_metadata={
                    "fjc_nid": row["nid"],
                    "sequence": row["Sequence"],
                    "court_type": court_type,
                    "appointment_title": appointment_title,
                    "nomination_date": row.get("Nomination Date") or None,
                    "confirmation_date": row.get("Confirmation Date") or None,
                    "commission_date": row.get("Commission Date") or None,
                    "senate_vote_type": row.get("Senate Vote Type") or None,
                    "ayes_nays": row.get("Ayes/Nays") or None,
                    "termination": row.get("Termination") or None,
                },
            )
        )
    return rows


def congressional_rows() -> list[dict]:
    if not CONGRESSIONAL_OUTPUT.exists():
        return []
    data = json.loads(CONGRESSIONAL_OUTPUT.read_text())
    return data.get("roles", [])


def build_dataset() -> dict:
    roles = executive_rows() + judicial_rows() + congressional_rows()
    people = {}
    for role in roles:
        person = people.setdefault(
            role["external_person_id"],
            {
                "external_person_id": role["external_person_id"],
                "full_name": role["full_name"],
                "branch": role["branch"],
                "roles": [],
            },
        )
        person["roles"].append(role["external_role_id"])

    sources = []
    source_ids = sorted({role["source_id"] for role in roles})
    for source_id in source_ids:
        source = source_info(source_id)
        source_counts = Counter(role["branch"] for role in roles if role["source_id"] == source_id)
        sources.append({**source, "id": source_id, "role_count": sum(source_counts.values())})

    return {
        "generated_at": date.today().isoformat(),
        "scope": {
            "branches": ["Executive", "Judicial", "Legislative"],
            "presidential_terms": TERMS,
            "description": (
                "Source-backed public-official role database for executive Cabinet "
                "and Cabinet-level officials, Article III judges appointed during "
                "the last three presidential terms, and congressional service "
                "records for the 115th through 119th Congresses."
            ),
        },
        "summary": {
            "person_count": len(people),
            "role_count": len(roles),
            "role_counts_by_branch": dict(Counter(role["branch"] for role in roles)),
            "role_counts_by_term": dict(Counter(role["presidential_term"] for role in roles)),
            "role_counts_by_category": dict(Counter(role["role_category"] for role in roles)),
        },
        "people": sorted(people.values(), key=lambda item: (item["branch"], item["full_name"])),
        "roles": sorted(
            roles,
            key=lambda role: (
                role["branch"],
                role["presidential_term"],
                role["court"] or role["agency"] or "",
                role["full_name"],
                role["role_title"],
            ),
        ),
        "sources": sources,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
