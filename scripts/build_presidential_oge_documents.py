#!/usr/bin/env python3
"""Build curated presidential OGE disclosure document and transaction indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_OUTPUT = ROOT / "data" / "disclosures" / "presidential_oge_documents.json"
TRANSACTION_OUTPUT = ROOT / "data" / "disclosures" / "presidential_oge_transactions.json"

USER_AGENT = "CivicLedger disclosure research bot contact: https://github.com/dtrezise/CivicLedger"
OGE_COLLECTION_URL = (
    "https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm="
)
OGE_PRESIDENT_2025_NOTICE = (
    "https://extapps2.oge.gov/web/oge.nsf/Resources/Available%2BNow%3A%2BThe%2BPresident"
    "%E2%80%99s%2Band%2BVice%2BPresident%E2%80%99s%2Bcertified%2Bannual%2Bfinancial%2Bdisclosure%2Breports"
)


CURATED_DOCUMENTS = [
    {
        "document_id": "oge-biden-2021-annual-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2021,
        "filing_type": "annual_278e",
        "filing_label": "2021 Annual OGE Form 278e",
        "reported_date": "2021-05-17",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/9A9B9318751632FA852586D9002EC0F9/%24FILE/Biden%2C%20Joseph%20R.%20%202021%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
    },
    {
        "document_id": "oge-biden-2022-annual-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2022,
        "filing_type": "annual_278e",
        "filing_label": "2022 Annual OGE Form 278e",
        "reported_date": "2022-05-16",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/E53C72B0E534B2E7852588410074776C/%24FILE/Biden%2C%20Joseph%20R.%20%202022%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
    },
    {
        "document_id": "oge-biden-2023-annual-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2023,
        "filing_type": "annual_278e",
        "filing_label": "2023 Annual OGE Form 278e",
        "reported_date": "2023-05-15",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/E0E994CFA156D7CF852589B000789259/%24FILE/Biden%2C%20Joseph%20R.%202023%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
    },
    {
        "document_id": "oge-biden-2024-annual-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2024,
        "filing_type": "annual_278e",
        "filing_label": "2024 Annual OGE Form 278e",
        "reported_date": "2024-05-15",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/F19EEDB6A75522E785258B1E007CDCC6/%24FILE/Biden%2C%20Joseph%20R.%20%202024%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
    },
    {
        "document_id": "oge-biden-2025-termination-278",
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "report_year": 2025,
        "filing_type": "termination_278e",
        "filing_label": "2025 Termination OGE Form 278e",
        "reported_date": "2025-01-20",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/34A58BA5A7439CA485258C1A00613D05/%24FILE/Biden%2C%20Joseph%20R.%20%202025%20Termination%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
    },
    {
        "document_id": "oge-trump-2020-annual-278",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-45",
        "report_year": 2020,
        "filing_type": "annual_278e",
        "filing_label": "2020 Annual OGE Form 278e",
        "reported_date": "2020-07-31",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/181BAF52E298FD70852585B70027E054/%24FILE/Trump%2C%20Donald%20J.%202020Annual%20278.pdf",
        "expected_transaction_activity": "annual_report_review_required",
    },
    {
        "document_id": "oge-trump-2021-termination-278",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-45",
        "report_year": 2021,
        "filing_type": "termination_278e",
        "filing_label": "2021 Termination OGE Form 278e",
        "reported_date": "2021-01-20",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/6E78B163F816EF6A852586630075291D/%24FILE/Trump%2C%20Donald%20J.%202021Termination%20278.pdf",
        "expected_transaction_activity": "annual_report_review_required",
    },
    {
        "document_id": "oge-trump-2025-annual-278",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "report_year": 2025,
        "filing_type": "annual_278e",
        "filing_label": "2025 Annual OGE Form 278e",
        "reported_date": "2025-06-13",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/4EC9A8E6DD078F2985258CA9002C9377/%24FILE/Trump%2C%20Donald%20J.%202025%20Annual%20278.pdf",
        "expected_transaction_activity": "none_or_not_applicable",
        "source_notice_url": OGE_PRESIDENT_2025_NOTICE,
    },
    {
        "document_id": "oge-trump-2025-278t-2025-10-17",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "report_year": 2025,
        "filing_type": "periodic_transaction_278t",
        "filing_label": "October 17, 2025 OGE Form 278-T",
        "reported_date": "2025-10-28",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/AA799A2729B4D1BE85258D430031A320/%24FILE/Donald%20J.%20Trump%2010.17.2025%20278-T.pdf",
        "expected_transaction_activity": "transaction_report",
    },
    {
        "document_id": "oge-trump-2026-278t-2026-05-08",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "report_year": 2026,
        "filing_type": "periodic_transaction_278t",
        "filing_label": "May 8, 2026 OGE Form 278-T",
        "reported_date": "2026-05-12",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/405E4EC4E27BE8D185258DF7002DD1C0/%24FILE/Trump%2C%20Donald%20J.-05.08.2026-278T%282%29.pdf",
        "expected_transaction_activity": "transaction_report",
    },
    {
        "document_id": "oge-trump-2026-annual-278",
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "report_year": 2026,
        "filing_type": "annual_278e",
        "filing_label": "2026 Annual OGE Form 278e",
        "reported_date": "2026-05-15",
        "source_url": "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/69AEAA9D7455ACD585258E27002DDEE1/%24FILE/Donald-J-Trump-2026-278ANNUAL.pdf",
        "expected_transaction_activity": "annual_report_review_required",
    },
]

UNAVAILABLE_DOCUMENTS = [
    {
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "service_start": "2009-01-20",
        "service_end": "2017-01-20",
        "availability_status": "official_archive_or_request_required",
        "availability_note": (
            "OGE states most public financial disclosure reports are destroyed six to seven years "
            "after creation unless needed for an ongoing investigation. Obama-term records therefore "
            "need archival/request workflow before parser promotion."
        ),
        "source_url": OGE_COLLECTION_URL,
    }
]

AMOUNT_RE = re.compile(
    r"[$S]\s*([0-9][0-9,\s.]*)\s*[-\u2022]\s*[$S]?\s*([0-9][0-9,\s.]*)",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
ACTION_RE = re.compile(
    r"\b(purchase|purchas[eo]|ourch\w+|du?rch\w+|nurch\w+|sale|sold|exchange)\b",
    re.IGNORECASE,
)
ROW_PREFIX_RE = re.compile(r"^\s*(\d{1,4})\s+")

TICKER_HINTS = {
    "ADOBE": "ADBE",
    "ADVANCED MICRO DEVICES": "AMD",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "APPLE": "AAPL",
    "BANK OF AMERICA": "BAC",
    "BOEING": "BA",
    "BROADCOM": "AVGO",
    "CITIGROUP": "C",
    "COINBASE": "COIN",
    "COMCAST": "CMCSA",
    "COSTCO": "COST",
    "CVS HEALTH": "CVS",
    "GOLDMAN": "GS",
    "HOME DEPOT": "HD",
    "INTEL": "INTC",
    "ISHARES GOLD TRUST": "IAU",
    "JPMORGAN": "JPM",
    "META PLATFORMS": "META",
    "MICROSOFT": "MSFT",
    "MORGAN STANLEY": "MS",
    "NETFLIX": "NFLX",
    "NVIDIA": "NVDA",
    "ORACLE": "ORCL",
    "PROCTER": "PG",
    "SALESFORCE": "CRM",
    "SERVICENOW": "NOW",
    "STATE STREET SPDR S&P 500 TRUST": "SPY",
    "TESLA": "TSLA",
    "THE BOEING": "BA",
    "THE HOME DEPOT": "HD",
    "VANGUARD S&P 500 ETF": "VOO",
    "VANGUARD TOTAL STOCK MARKET": "VTI",
    "WALMART": "WMT",
    "WELLS FARGO": "WFC",
}


def clean_amount(value: str) -> int | None:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    return int(digits)


def normalize_amount_label(label: str) -> tuple[str, int | None, int | None]:
    match = AMOUNT_RE.search(label)
    if not match:
        return (label.strip(), None, None)
    low = clean_amount(match.group(1))
    high = clean_amount(match.group(2))
    if low is None or high is None:
        return (label.strip(), low, high)
    return (f"${low:,} - ${high:,}", low, high)


def normalize_trade_date(value: str, report_year: int) -> tuple[str | None, bool]:
    match = DATE_RE.search(value)
    if not match:
        return (None, False)
    month = int(match.group(1))
    day = int(match.group(2))
    year_token = match.group(3)
    year = int(year_token)
    if year < 100:
        year += 2000
    corrected = False
    if year > report_year:
        year = report_year
        corrected = True
    try:
        return (date(year, month, day).isoformat(), corrected)
    except ValueError:
        return (None, False)


def action_from_text(value: str) -> str:
    action = ACTION_RE.search(value)
    if not action:
        return "UNKNOWN"
    token = action.group(1).lower()
    if token in {"sale", "sold"}:
        return "SELL"
    if token == "exchange":
        return "EXCHANGE"
    return "BUY"


def asset_class_for(description: str) -> str:
    value = description.upper()
    if "BITCOIN" in value or "ETHEREUM" in value or "CRYPTO" in value:
        return "crypto"
    if "ETF" in value or "EXCHANGE" in value or "VANGUARD" in value or "ISHARES" in value or "SPDR" in value:
        return "etf"
    if "DUE" in value or "B/E" in value or "BOND" in value or "REV" in value or "MUNI" in value or "GO " in value:
        return "fixed_income"
    if "MONEY FUND" in value or "FUND" in value:
        return "fund"
    return "equity"


def ticker_for(description: str, asset_class: str) -> str | None:
    value = description.upper()
    for needle, ticker in TICKER_HINTS.items():
        if needle in value:
            return ticker
    if asset_class == "fixed_income":
        return None
    ticker_match = re.search(r"\b([A-Z]{2,5})\s+(?:INC|CORP|PLC|CO|CL|COM)\b", description)
    if ticker_match:
        return ticker_match.group(1)
    return None


def cleaned_description(value: str) -> str:
    value = ROW_PREFIX_RE.sub("", value)
    value = ACTION_RE.split(value, maxsplit=1)[0]
    value = re.sub(r"\s+", " ", value).strip(" -|")
    return value[:220]


def parse_transaction_lines(document: dict, text_by_page: list[dict]) -> list[dict]:
    if document["filing_type"] != "periodic_transaction_278t":
        return []
    rows = []
    seen = set()
    for page in text_by_page:
        for line in page["text"].splitlines():
            normalized_line = re.sub(r"(\d{1,2})/(\d)\.(\d)/(\d{4})", r"\1/\2\3/\4", line)
            if "$" not in normalized_line and "S" not in normalized_line:
                continue
            amount = AMOUNT_RE.search(normalized_line)
            action = ACTION_RE.search(normalized_line)
            date_matches = (
                [match for match in DATE_RE.finditer(normalized_line) if match.start() < amount.start()]
                if amount
                else []
            )
            if not amount or not date_matches or not action:
                continue
            trade_date, corrected = normalize_trade_date(date_matches[-1].group(0), document["report_year"])
            if not trade_date:
                continue
            disclosure_lag_days = (
                date.fromisoformat(document["reported_date"]) - date.fromisoformat(trade_date)
            ).days
            amount_label, amount_min, amount_max = normalize_amount_label(amount.group(0))
            description = cleaned_description(normalized_line)
            if not description:
                continue
            asset_class = asset_class_for(description)
            ticker = ticker_for(description, asset_class)
            source_sequence = None
            prefix = ROW_PREFIX_RE.search(line)
            if prefix:
                source_sequence = int(prefix.group(1))
            dedupe_key = (document["document_id"], source_sequence, description, trade_date, amount_label)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            sequence = len(rows) + 1
            rows.append(
                {
                    "id": f"{document['document_id']}:tx-{sequence:04d}",
                    "document_id": document["document_id"],
                    "official_id": document["official_id"],
                    "full_name": document["full_name"],
                    "presidential_term": document["presidential_term"],
                    "source_sequence": source_sequence,
                    "trade_date": trade_date,
                    "reported_date": document["reported_date"],
                    "disclosure_lag_days": disclosure_lag_days,
                    "action": action_from_text(normalized_line),
                    "ticker": ticker,
                    "asset_display_name": description,
                    "asset_class": asset_class,
                    "value_range_label": amount_label,
                    "value_range_min": amount_min,
                    "value_range_max": amount_max,
                    "record_status": "official_oge_parser_preview_not_promoted",
                    "confidence_label": "Official OGE 278-T parser preview; review required",
                    "parsing_confidence": 0.58 if corrected else 0.7,
                    "review_required_before_public_trade": True,
                    "public_production_trade": False,
                    "date_normalized_from_ocr": corrected,
                    "source_url": document["source_url"],
                    "source_page": page["page"],
                    "source_line_text": re.sub(r"\s+", " ", normalized_line).strip()[:350],
                }
            )
    return rows


def fetch_pdf(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read()


def extract_pdf_text(content: bytes) -> tuple[list[dict], int]:
    reader = PdfReader(BytesIO(content))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": index, "text": text})
    return pages, len(reader.pages)


def document_from_pdf(document: dict, content: bytes) -> tuple[dict, list[dict]]:
    text_by_page, page_count = extract_pdf_text(content)
    text_sample = "\n".join(page["text"] for page in text_by_page[:3])
    transactions = parse_transaction_lines(document, text_by_page)
    transaction_actions = Counter(row["action"] for row in transactions)
    asset_classes = Counter(row["asset_class"] for row in transactions)
    no_transaction_hint = bool(
        re.search(r"Part\s*7[:\s]+Transactions.{0,300}\b(?:None|N/A)\b", text_sample, re.IGNORECASE | re.DOTALL)
        or document.get("expected_transaction_activity") == "none_or_not_applicable"
    )
    result = {
        **document,
        "source_tier": "official",
        "source_collection_url": OGE_COLLECTION_URL,
        "archive_status": "official_source_linked_not_committed",
        "content_type": "application/pdf",
        "byte_count": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "page_count": page_count,
        "parser_status": "parsed_preview" if transactions else "document_indexed",
        "review_status": "review_required_before_public_trade",
        "review_required_before_public_trade": True,
        "public_production_trade_count": 0,
        "transaction_summary": {
            "parser_preview_transaction_count": len(transactions),
            "parser_preview_actions": dict(sorted(transaction_actions.items())),
            "asset_class_counts": dict(sorted(asset_classes.items())),
            "no_transaction_hint": no_transaction_hint,
        },
        "parser_preview": re.sub(r"\s+", " ", text_sample).strip()[:700],
    }
    return result, transactions


def load_existing_documents() -> tuple[dict, dict]:
    if DOCUMENT_OUTPUT.exists() and TRANSACTION_OUTPUT.exists():
        return (json.loads(DOCUMENT_OUTPUT.read_text()), json.loads(TRANSACTION_OUTPUT.read_text()))
    return ({}, {})


def build(refresh: bool) -> tuple[dict, dict]:
    existing_documents, existing_transactions = load_existing_documents()
    if not refresh and existing_documents and existing_transactions:
        return (existing_documents, existing_transactions)

    documents = []
    transactions = []
    failures = []
    for document in CURATED_DOCUMENTS:
        try:
            content = fetch_pdf(document["source_url"])
            parsed_document, parsed_transactions = document_from_pdf(document, content)
            documents.append(parsed_document)
            transactions.extend(parsed_transactions)
        except Exception as exc:  # pragma: no cover - defensive for live source outages.
            failures.append({"document_id": document["document_id"], "error": f"{type(exc).__name__}: {exc}"})
            documents.append(
                {
                    **document,
                    "source_tier": "official",
                    "source_collection_url": OGE_COLLECTION_URL,
                    "archive_status": "official_source_linked_fetch_failed",
                    "parser_status": "fetch_failed",
                    "review_status": "review_required_before_public_trade",
                    "review_required_before_public_trade": True,
                    "public_production_trade_count": 0,
                    "transaction_summary": {"parser_preview_transaction_count": 0},
                }
            )

    document_counts = Counter(row["official_id"] for row in documents)
    term_counts = Counter(row["presidential_term"] for row in documents)
    transaction_counts = Counter(row["official_id"] for row in transactions)
    document_index = {
        "generated_at": date.today().isoformat(),
        "schema_version": "presidential-oge-documents-v1",
        "context_label": (
            "Curated official OGE presidential disclosure documents. Parsed transaction rows are previews "
            "and require review before public production promotion."
        ),
        "source": {
            "id": "oge-individual-disclosures",
            "name": "OGE Officials' Individual Disclosures",
            "collection_url": OGE_COLLECTION_URL,
            "source_tier": "official",
            "use_restrictions_preserved": True,
        },
        "summary": {
            "document_count": len(documents),
            "unavailable_official_count": len(UNAVAILABLE_DOCUMENTS),
            "parser_preview_transaction_count": len(transactions),
            "public_production_trade_count": 0,
            "document_counts_by_official": dict(sorted(document_counts.items())),
            "document_counts_by_term": dict(sorted(term_counts.items())),
            "fetch_failure_count": len(failures),
        },
        "unavailable_documents": UNAVAILABLE_DOCUMENTS,
        "documents": sorted(documents, key=lambda row: (row["official_id"], row["report_year"], row["document_id"])),
        "failures": failures,
    }
    transaction_index = {
        "generated_at": date.today().isoformat(),
        "schema_version": "presidential-oge-transactions-v1",
        "context_label": (
            "Official OGE 278-T parser-preview transaction rows for timeline exploration only; "
            "review is required before production trade promotion."
        ),
        "summary": {
            "parser_preview_transaction_count": len(transactions),
            "public_production_trade_count": 0,
            "review_required_transaction_count": len(transactions),
            "transaction_counts_by_official": dict(sorted(transaction_counts.items())),
            "transaction_counts_by_document": dict(sorted(Counter(row["document_id"] for row in transactions).items())),
            "asset_class_counts": dict(sorted(Counter(row["asset_class"] for row in transactions).items())),
        },
        "transactions": sorted(transactions, key=lambda row: (row["official_id"], row["trade_date"], row["id"])),
    }
    return (document_index, transaction_index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch official OGE PDFs and regenerate parser previews. Without this, existing JSON is reused.",
    )
    args = parser.parse_args()
    documents, transactions = build(refresh=args.refresh)
    DOCUMENT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DOCUMENT_OUTPUT.write_text(json.dumps(documents, indent=2, sort_keys=True) + "\n")
    TRANSACTION_OUTPUT.write_text(json.dumps(transactions, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {DOCUMENT_OUTPUT}")
    print(f"Wrote {TRANSACTION_OUTPUT}")


if __name__ == "__main__":
    main()
