from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from urllib.request import Request, urlopen


HOUSE_INDEX_URL = (
    "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.txt"
)
HOUSE_FINANCIAL_DOCUMENT_URL = (
    "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}/{document_id}.pdf"
)
HOUSE_PTR_DOCUMENT_URL = (
    "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{document_id}.pdf"
)
USER_AGENT = "CivicLedger research crawler/0.2 (+https://civic-ledger.dan-a2c.workers.dev/)"
NAME_NOISE = {
    "jr",
    "sr",
    "ii",
    "iii",
    "iv",
    "md",
    "facs",
    "phd",
    "esq",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class HouseIndexFetch:
    year: int
    source_url: str
    sha256: str
    byte_count: int
    rows: list[dict]


def normalize_name(value: str | None) -> str:
    ascii_value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def meaningful_name_tokens(value: str | None) -> list[str]:
    return [token for token in normalize_name(value).split() if token not in NAME_NOISE]


def normalize_district(value: str | int | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.lower() == "at large":
        return "0"
    return normalized.lstrip("0") or "0"


def parse_house_index(content: bytes) -> list[dict]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = content.decode("cp1252")
    reader = csv.DictReader(io.StringIO(decoded), delimiter="\t")
    required = {"Prefix", "Last", "First", "Suffix", "FilingType", "StateDst", "Year", "FilingDate", "DocID"}
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        raise ValueError("House disclosure index fields do not match the expected Clerk format")
    rows = []
    for row in reader:
        cleaned = {key: (value or "").strip() for key, value in row.items()}
        if cleaned.get("DocID"):
            rows.append(cleaned)
    return rows


def fetch_house_index(year: int) -> HouseIndexFetch:
    source_url = HOUSE_INDEX_URL.format(year=year)
    request = Request(source_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        content = response.read()
    return HouseIndexFetch(
        year=year,
        source_url=source_url,
        sha256=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
        rows=parse_house_index(content),
    )


def split_state_district(value: str) -> tuple[str | None, str | None]:
    normalized = (value or "").strip().upper()
    if len(normalized) < 2:
        return None, None
    return normalized[:2], normalize_district(normalized[2:])


def parse_filing_date(value: str) -> date:
    return datetime.strptime(value, "%m/%d/%Y").date()


def document_url(row: dict) -> str:
    template = HOUSE_PTR_DOCUMENT_URL if row.get("FilingType") == "P" else HOUSE_FINANCIAL_DOCUMENT_URL
    return template.format(year=row["Year"], document_id=row["DocID"])


def source_row_sha256(row: dict) -> str:
    canonical = "\n".join(f"{key}={str(row.get(key) or '').strip()}" for key in sorted(row))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def house_transaction_signature(row: dict) -> str:
    identity = "|".join(
        normalize_name(str(row.get(key) or ""))
        for key in (
            "official_id",
            "trade_date",
            "action",
            "owner",
            "asset_display_name",
            "ticker",
            "value_range_label",
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _signature_evidence(document: dict, predecessor: dict) -> dict:
    amendment_signatures = set(document.get("transaction_signatures") or [])
    predecessor_signatures = set(predecessor.get("transaction_signatures") or [])
    overlap = amendment_signatures & predecessor_signatures
    union = amendment_signatures | predecessor_signatures
    return {
        "evidence_type": "transaction_signature_comparison",
        "amendment_signature_count": len(amendment_signatures),
        "predecessor_signature_count": len(predecessor_signatures),
        "exact_overlap_count": len(overlap),
        "jaccard_similarity": round(len(overlap) / len(union), 4) if union else None,
        "signature_algorithm": "normalized-official-date-action-owner-asset-ticker-amount-sha256",
    }


def _filing_date_evidence(document: dict, predecessor: dict) -> dict:
    amendment_date = document.get("filing_date")
    predecessor_date = predecessor.get("filing_date")
    day_gap = None
    chronological = None
    if amendment_date and predecessor_date:
        try:
            day_gap = (date.fromisoformat(amendment_date) - date.fromisoformat(predecessor_date)).days
            chronological = day_gap >= 0
        except ValueError:
            pass
    return {
        "evidence_type": "filing_date_relationship",
        "amendment_filing_date": amendment_date,
        "predecessor_filing_date": predecessor_date,
        "day_gap": day_gap,
        "chronologically_consistent": chronological,
    }


def house_ocr_priority_record(document: dict, *, as_of: date) -> dict | None:
    """Build a metadata-only OCR work item for an image-only House PTR."""
    if document.get("parser_status") != "ocr_required":
        return None

    source_url = str(document.get("source_url") or "")
    parsed_url = urlparse(source_url)
    official_url = (
        parsed_url.scheme == "https"
        and parsed_url.netloc == "disclosures-clerk.house.gov"
        and parsed_url.path.startswith("/public_disc/ptr-pdfs/")
    )
    file_hash = str(document.get("file_hash") or "").lower()
    hash_verified = bool(SHA256_RE.fullmatch(file_hash))
    identity_verified = (
        document.get("match_status") == "matched"
        and bool(document.get("official_id"))
        and int(document.get("match_score") or 0) >= 8
    )
    page_count = int(document.get("page_count") or 0)
    page_manifested = page_count > 0
    filing_date = date.fromisoformat(document["filing_date"])
    age_days = max(0, (as_of - filing_date).days)
    recency_points = 15 if age_days <= 365 else 10 if age_days <= 1095 else 5

    checks = {
        "official_source_url": official_url,
        "source_file_sha256_present": hash_verified,
        "filer_identity_deterministically_matched": identity_verified,
        "source_page_count_present": page_manifested,
    }
    evidence_score = (
        (30 if official_url else 0)
        + (25 if hash_verified else 0)
        + (20 if identity_verified else 0)
        + (10 if page_manifested else 0)
        + recency_points
    )
    eligible = all(checks.values())
    return {
        "document_id": document["document_id"],
        "source_id": document.get("source_id"),
        "chamber": "House",
        "official_id": document.get("official_id"),
        "official_name": document.get("official_name"),
        "filing_date": document["filing_date"],
        "source_url": source_url,
        "source_file_sha256": file_hash or None,
        "source_page_count": page_count,
        "source_byte_count": int(document.get("byte_count") or 0),
        "priority_score": evidence_score,
        "priority_tier": "highest_confidence" if eligible and evidence_score >= 90 else "evidence_gap",
        "eligibility_checks": checks,
        "eligible_for_ocr_batch": eligible,
        "processing_status": "metadata_prioritized_ocr_not_run",
        "ocr_content_present": False,
        "transaction_rows_created": 0,
    }


def house_document_family_key(document: dict) -> str:
    """Group only explicitly related filings; never infer that same-year PTRs are amendments."""
    title = normalize_name(document.get("report_title") or document.get("report_type"))
    title = re.sub(r"\b(amended|amendment|corrected|correction)\b", "", title).strip()
    explicit_reference = str(
        document.get("amends_document_id")
        or document.get("original_document_id")
        or document.get("document_id")
    )
    identity = document.get("official_id") or normalize_name(document.get("filer_name"))
    value = "|".join([str(identity), title, explicit_reference])
    return f"house-family-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def reconcile_house_amendments(documents: list[dict]) -> list[dict]:
    """Annotate explicit amendment chains without suppressing or merging source records."""
    by_id = {document["document_id"]: document for document in documents}
    output = []
    for source in documents:
        document = dict(source)
        document["document_family_id"] = house_document_family_key(document)
        referenced_id = document.get("amends_document_id") or document.get("original_document_id")
        if referenced_id:
            reference_field = (
                "amends_document_id" if document.get("amends_document_id") else "original_document_id"
            )
            document["amendment_status"] = (
                "explicit_reference_resolved" if referenced_id in by_id else "explicit_reference_unresolved"
            )
            document["supersedes_document_id"] = referenced_id
            document["amendment_reconciliation_evidence"] = [
                {
                    "evidence_type": "explicit_source_field",
                    "field": reference_field,
                    "value": referenced_id,
                    "source_document_id": document["document_id"],
                }
            ]
            if referenced_id in by_id:
                predecessor = by_id[referenced_id]
                document["amendment_reconciliation_evidence"].extend(
                    [
                        _filing_date_evidence(document, predecessor),
                        _signature_evidence(document, predecessor),
                    ]
                )
            document["amendment_linkage_confidence"] = (
                "explicit_resolved" if referenced_id in by_id else "explicit_unresolved"
            )
        else:
            document["amendment_status"] = "no_explicit_amendment_reference"
            document["supersedes_document_id"] = None
            document["amendment_reconciliation_evidence"] = []
            document["amendment_linkage_confidence"] = "none"
        document["amendment_reconciliation_action"] = "annotate_only"
        document["source_record_preserved"] = True
        output.append(document)
    return output


def house_roles(public_officials: dict) -> list[dict]:
    return [
        role
        for role in public_officials.get("roles", [])
        if role.get("branch") == "Legislative"
        and role.get("source_metadata", {}).get("chamber") == "House"
    ]


def score_role_match(row: dict, role: dict, filed_date: date) -> tuple[int, list[str]]:
    reasons = []
    score = 0
    role_tokens = meaningful_name_tokens(role.get("full_name"))
    first_tokens = meaningful_name_tokens(row.get("First"))
    last_tokens = meaningful_name_tokens(row.get("Last"))
    metadata = role.get("source_metadata", {})
    row_state, row_district = split_state_district(row.get("StateDst", ""))

    if last_tokens and all(token in role_tokens for token in last_tokens):
        score += 4
        reasons.append("surname")
    if first_tokens and first_tokens[0] in role_tokens:
        score += 3
        reasons.append("first_name")
    if row_district is not None and row_district == normalize_district(metadata.get("district")):
        score += 2
        reasons.append("district")
    if row_state and row_state == metadata.get("state"):
        score += 2
        reasons.append("state")

    role_start = datetime.fromisoformat(role["service_start"]).date()
    role_end = datetime.fromisoformat(role.get("service_end") or "9999-12-31").date()
    if role_start <= filed_date <= role_end:
        score += 1
        reasons.append("active_on_filing_date")
    return score, reasons


def match_house_member(row: dict, roles: list[dict]) -> dict:
    filed_date = parse_filing_date(row["FilingDate"])
    row_state, _ = split_state_district(row.get("StateDst", ""))
    candidates: dict[str, dict] = {}
    for role in roles:
        metadata = role.get("source_metadata", {})
        if metadata.get("state") != row_state:
            continue
        role_start = datetime.fromisoformat(role["service_start"]).date()
        service_end = role.get("service_end")
        role_end = datetime.fromisoformat(service_end).date() if service_end else date.max
        grace_end = (
            role_end + timedelta(days=180)
            if service_end and role_end <= date.max - timedelta(days=180)
            else role_end
        )
        if not role_start <= filed_date <= grace_end:
            continue
        score, reasons = score_role_match(row, role, filed_date)
        official_id = role["external_person_id"]
        previous = candidates.get(official_id)
        if previous is None or score > previous["score"]:
            candidates[official_id] = {"score": score, "reasons": reasons, "role": role}

    ranked = sorted(candidates.items(), key=lambda item: (-item[1]["score"], item[0]))
    candidate_summary = [
        {
            "official_id": official_id,
            "score": candidate["score"],
            "reasons": candidate["reasons"],
            "official_name": candidate["role"].get("full_name"),
        }
        for official_id, candidate in ranked[:5]
    ]
    if not ranked or ranked[0][1]["score"] < 8:
        return {
            "match_status": "unmatched",
            "match_score": ranked[0][1]["score"] if ranked else 0,
            "identity_resolution": "manual_review_required",
            "identity_candidates": candidate_summary,
        }
    if len(ranked) > 1 and ranked[0][1]["score"] == ranked[1][1]["score"]:
        return {
            "match_status": "ambiguous",
            "match_score": ranked[0][1]["score"],
            "identity_resolution": "ambiguous_manual_review_required",
            "identity_candidates": candidate_summary,
        }

    official_id, match = ranked[0]
    role = match["role"]
    return {
        "match_status": "matched",
        "match_score": match["score"],
        "match_reasons": match["reasons"],
        "identity_resolution": "deterministic_match",
        "identity_candidates": candidate_summary,
        "official_id": official_id,
        "official_name": role["full_name"],
        "bioguide_id": role.get("source_metadata", {}).get("bioguide_id"),
    }


def build_house_ptr_index(public_officials: dict, start_year: int, end_year: int) -> dict:
    roles = house_roles(public_officials)
    documents = []
    source_indexes = []
    filing_type_counts = Counter()
    all_row_count = 0

    for year in range(start_year, end_year + 1):
        fetched = fetch_house_index(year)
        all_row_count += len(fetched.rows)
        filing_type_counts.update(row["FilingType"] for row in fetched.rows)
        ptr_rows = [
            row
            for row in fetched.rows
            if row.get("FilingType") == "P" and normalize_name(row.get("Prefix")) == "hon"
        ]
        source_indexes.append(
            {
                "year": year,
                "source_url": fetched.source_url,
                "sha256": fetched.sha256,
                "byte_count": fetched.byte_count,
                "row_count": len(fetched.rows),
                "member_ptr_count": len(ptr_rows),
            }
        )
        for row in ptr_rows:
            state, district = split_state_district(row["StateDst"])
            match = match_house_member(row, roles)
            documents.append(
                {
                    "document_id": f"house-ptr-{row['Year']}-{row['DocID']}",
                    "clerk_document_id": row["DocID"],
                    "source_id": "house-financial-disclosure",
                    "source_index_url": fetched.source_url,
                    "source_url": document_url(row),
                    "source_tier": "official",
                    "report_type": "periodic_transaction_report",
                    "filing_type_code": row["FilingType"],
                    "filing_year": int(row["Year"]),
                    "filing_date": parse_filing_date(row["FilingDate"]).isoformat(),
                    "filer_name": " ".join(
                        value for value in [row.get("Prefix"), row.get("First"), row.get("Last"), row.get("Suffix")] if value
                    ),
                    "state": state,
                    "district": district,
                    "record_status": "official_house_index",
                    "source_row_sha256": source_row_sha256(row),
                    "source_row_metadata": dict(sorted(row.items())),
                    "review_required_before_public_trade": True,
                    **match,
                }
            )

    documents = reconcile_house_amendments(documents)
    match_counts = Counter(document["match_status"] for document in documents)
    return {
        "schema_version": "house-disclosure-index-v1",
        "generated_at": date.today().isoformat(),
        "source": {
            "id": "house-financial-disclosure",
            "name": "Office of the Clerk, U.S. House of Representatives",
            "url": "https://disclosures-clerk.house.gov/financialdisclosure",
            "source_tier": "official",
        },
        "scope": {
            "start_year": start_year,
            "end_year": end_year,
            "document_scope": "Member periodic transaction reports indexed by the House Clerk",
        },
        "summary": {
            "source_index_count": len(source_indexes),
            "source_index_row_count": all_row_count,
            "member_ptr_document_count": len(documents),
            "matched_member_ptr_document_count": match_counts["matched"],
            "ambiguous_member_ptr_document_count": match_counts["ambiguous"],
            "unmatched_member_ptr_document_count": match_counts["unmatched"],
            "filing_type_counts": dict(sorted(filing_type_counts.items())),
            "review_required_before_public_trade": True,
            "public_production_trade_count": 0,
        },
        "source_indexes": source_indexes,
        "documents": sorted(documents, key=lambda row: (row["filing_date"], row["clerk_document_id"])),
    }
