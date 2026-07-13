from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date
from urllib.request import Request, urlopen

from app.services.house_disclosures import (
    USER_AGENT,
    fetch_house_index,
    normalize_name,
    parse_filing_date,
    source_row_sha256,
)


HOUSE_SEARCH_URL = "https://disclosures-clerk.house.gov/FinancialDisclosure/ViewSearch"
HOUSE_ETHICS_FINANCIAL_DISCLOSURE_URL = "https://ethics.house.gov/financial-disclosure/"
HOUSE_ETHICS_STOCK_ACT_PTR_URL = (
    "https://ethics.house.gov/financial-disclosure-pink-sheets/"
    "periodic-reporting-personal-financial-transactions-pursuant-stock/"
)
HOUSE_FINANCIAL_DOCUMENT_URL = (
    "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}/{document_id}.pdf"
)
HOUSE_PTR_DOCUMENT_URL = (
    "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{document_id}.pdf"
)
MEMBER_PREFIXES = {"hon", "honorable"}
FINANCIAL_REPORT_FILING_TYPES = {"A", "O", "T"}
FILING_TYPE_LABELS = {
    "A": "amendment",
    "O": "original",
    "T": "termination",
}
KNOWN_2014_UNINDEXED_PTRS = [
    {
        "document_id": "20000284",
        "filer_name": "Hon. John A. Boehner",
        "source_url": HOUSE_PTR_DOCUMENT_URL.format(year=2014, document_id="20000284"),
    },
    {
        "document_id": "20002236",
        "filer_name": "Hon. Nancy Pelosi",
        "source_url": HOUSE_PTR_DOCUMENT_URL.format(year=2014, document_id="20002236"),
    },
]


def _fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read()


def _is_member(row: dict) -> bool:
    return normalize_name(row.get("Prefix")) in MEMBER_PREFIXES


def _filer_name(row: dict) -> str:
    return " ".join(
        value.strip()
        for value in (
            row.get("Prefix") or "",
            row.get("First") or "",
            row.get("Last") or "",
            row.get("Suffix") or "",
        )
        if value.strip()
    )


def _document_url(row: dict) -> str:
    template = HOUSE_PTR_DOCUMENT_URL if row.get("DisclosureType") == "PTR" else HOUSE_FINANCIAL_DOCUMENT_URL
    return template.format(year=row["Year"], document_id=row["DocID"])


def _document_record(row: dict, source: dict) -> dict:
    disclosure_type = row.get("DisclosureType")
    filing_type = row.get("FilingType")
    is_ptr = disclosure_type == "PTR"
    filing_year = row.get("Filing Year") or row.get("Year")
    return {
        "id": f"house-clerk-{row['DocID']}",
        "document_id": row["DocID"],
        "filer_name": _filer_name(row),
        "filer_category": "member" if _is_member(row) else "other_house_filer",
        "state_district": row.get("StateDst") or None,
        "archive_year": int(row["Year"]),
        "filing_year": int(filing_year),
        "filing_date": parse_filing_date(row["FilingDate"]).isoformat(),
        "disclosure_type": disclosure_type,
        "filing_type": filing_type,
        "report_type": (
            "periodic_transaction_report"
            if is_ptr
            else f"financial_disclosure_{FILING_TYPE_LABELS[filing_type]}"
        ),
        "transaction_section_status": (
            "periodic_transaction_report_metadata_only"
            if is_ptr
            else "possible_schedule_b_transactions_not_examined"
        ),
        "transaction_rows_created": 0,
        "source_url": _document_url(row),
        "source_index_url": source["url"],
        "source_index_sha256": source["sha256"],
        "source_row_sha256": source_row_sha256(row),
        "provenance": {
            "publisher": "Clerk of the U.S. House of Representatives",
            "collection": "Financial Disclosure Reports Database",
            "source_tier": "official",
            "extraction": "official_tab_delimited_bulk_index",
        },
    }


def build_house_historical_transaction_index(
    start_year: int = 2009,
    end_year: int = 2014,
    *,
    as_of: date | None = None,
    index_fetcher=fetch_house_index,
    binary_fetcher=_fetch_bytes,
) -> dict:
    if start_year < 2009 or end_year > 2014 or start_year > end_year:
        raise ValueError("Historical House transaction index supports archive years 2009 through 2014")

    documents = []
    index_snapshots = []
    year_summaries = []
    indexed_document_ids = set()
    for year in range(start_year, end_year + 1):
        fetched = index_fetcher(year)
        source = {
            "url": fetched.source_url,
            "sha256": fetched.sha256,
        }
        indexed_document_ids.update(row["DocID"] for row in fetched.rows)
        selected_rows = [
            row
            for row in fetched.rows
            if row.get("DisclosureType") == "PTR"
            or (
                row.get("DisclosureType") == "FD"
                and row.get("FilingType") in FINANCIAL_REPORT_FILING_TYPES
                and _is_member(row)
            )
        ]
        records = [_document_record(row, source) for row in selected_rows]
        documents.extend(records)
        disclosure_counts = Counter(row.get("DisclosureType") or "unknown" for row in fetched.rows)
        member_ptr_count = sum(
            row.get("DisclosureType") == "PTR" and _is_member(row) for row in fetched.rows
        )
        index_snapshots.append(
            {
                "archive_year": year,
                "url": fetched.source_url,
                "sha256": fetched.sha256,
                "byte_count": fetched.byte_count,
                "row_count": len(fetched.rows),
            }
        )
        year_summaries.append(
            {
                "archive_year": year,
                "bulk_index_row_count": len(fetched.rows),
                "bulk_index_disclosure_counts": dict(sorted(disclosure_counts.items())),
                "indexed_ptr_document_count": disclosure_counts.get("PTR", 0),
                "indexed_member_ptr_document_count": member_ptr_count,
                "indexed_member_financial_report_count": sum(
                    record["disclosure_type"] == "FD" for record in records
                ),
                "separate_ptr_reporting_status": (
                    "not_applicable_pre_stock_act"
                    if year <= 2011
                    else "legacy_ptr_rows_present_in_fd_bulk_index"
                    if disclosure_counts.get("PTR", 0)
                    else "no_ptr_rows_in_bulk_index"
                ),
            }
        )

    gap_evidence = []
    if start_year <= 2014 <= end_year:
        for evidence in KNOWN_2014_UNINDEXED_PTRS:
            content = binary_fetcher(evidence["source_url"])
            gap_evidence.append(
                {
                    **evidence,
                    "archive_year": 2014,
                    "report_type": "periodic_transaction_report",
                    "bulk_index_membership": evidence["document_id"] in indexed_document_ids,
                    "source_sha256": hashlib.sha256(content).hexdigest(),
                    "source_byte_count": len(content),
                    "transaction_section_status": "ptr_form_not_parsed_into_transactions",
                    "transaction_rows_created": 0,
                }
            )

    documents.sort(
        key=lambda row: (
            row["archive_year"],
            row["filing_date"],
            row["document_id"],
        )
    )
    ptr_documents = [row for row in documents if row["disclosure_type"] == "PTR"]
    financial_documents = [row for row in documents if row["disclosure_type"] == "FD"]
    return {
        "schema_version": "house-historical-transaction-source-index-v1",
        "generated_at": (as_of or date.today()).isoformat(),
        "scope": {
            "archive_years": [start_year, end_year],
            "record_scope": (
                "All PTR rows in the official bulk indexes, plus member original, amended, and termination "
                "financial-disclosure metadata. Financial-disclosure PDFs were not parsed for Schedule B."
            ),
            "transaction_interpretation": (
                "Document-level source index only; no securities or transaction records were inferred."
            ),
        },
        "sources": [
            {
                "id": "house-clerk-bulk-financial-disclosure-indexes",
                "publisher": "Clerk of the U.S. House of Representatives",
                "source_tier": "official",
                "index_snapshots": index_snapshots,
            },
            {
                "id": "house-clerk-financial-disclosure-search",
                "url": HOUSE_SEARCH_URL,
                "source_tier": "official",
            },
            {
                "id": "house-ethics-financial-disclosure-guidance",
                "url": HOUSE_ETHICS_FINANCIAL_DISCLOSURE_URL,
                "ptr_guidance_url": HOUSE_ETHICS_STOCK_ACT_PTR_URL,
                "source_tier": "official",
            },
        ],
        "coverage": {
            "year_summaries": year_summaries,
            "declared_gaps": [
                {
                    "archive_years": [2009, 2011],
                    "status": "separate_ptr_reporting_not_applicable_pre_stock_act",
                    "impact": (
                        "Transactions, when reportable, appear within annual or termination financial "
                        "disclosures; this artifact does not parse those PDF schedules."
                    ),
                },
                {
                    "archive_years": [2012, 2013],
                    "status": "legacy_ptr_bulk_rows_backfilled",
                    "impact": "Official PTR document metadata is indexed; transaction rows remain unparsed.",
                },
                {
                    "archive_years": [2014, 2014],
                    "status": "official_bulk_index_known_incomplete",
                    "impact": (
                        "The 2014 bulk file omits official PTR PDFs demonstrated below. The search-only "
                        "catalog was not crawled, so 2014 is intentionally not represented as complete."
                    ),
                    "evidence_documents": gap_evidence,
                },
            ],
        },
        "summary": {
            "source_index_count": len(index_snapshots),
            "source_index_row_count": sum(row["row_count"] for row in index_snapshots),
            "indexed_document_count": len(documents),
            "indexed_ptr_document_count": len(ptr_documents),
            "indexed_member_ptr_document_count": sum(
                row["filer_category"] == "member" for row in ptr_documents
            ),
            "indexed_member_financial_report_count": len(financial_documents),
            "known_unindexed_2014_ptr_evidence_count": len(gap_evidence),
            "transaction_row_count": 0,
        },
        "documents": documents,
    }
