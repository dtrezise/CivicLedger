#!/usr/bin/env python3
"""Fetch and parse indexed House PTRs into review-gated transaction previews."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from threading import Lock
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.parsers import get_parser  # noqa: E402
from app.services.house_disclosures import USER_AGENT  # noqa: E402


INDEX = ROOT / "data" / "disclosures" / "house_disclosure_index.json"
OUTPUT = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
PARTITION_DIR = ROOT / "data" / "disclosures" / "house_ptr"
CACHE = ROOT / ".cache" / "house-ptr"
PRINT_LOCK = Lock()

VALUE_RANGES = {
    "$1,001 - $15,000": (1001, 15000),
    "$15,001 - $50,000": (15001, 50000),
    "$50,001 - $100,000": (50001, 100000),
    "$100,001 - $250,000": (100001, 250000),
    "$250,001 - $500,000": (250001, 500000),
    "$500,001 - $1,000,000": (500001, 1000000),
    "$1,000,001 - $5,000,000": (1000001, 5000000),
    "$5,000,001 - $25,000,000": (5000001, 25000000),
    "$25,000,001 - $50,000,000": (25000001, 50000000),
    "Over $50,000,000": (50000001, None),
}


def canonical_amount(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = value.replace("$ ", "$").replace("S", "$")
    numbers = re.findall(r"\d[\d,]*", value)
    if len(numbers) >= 2:
        return f"${numbers[0]} - ${numbers[1]}"
    if numbers and re.search(r"over|more than|\+", value, re.IGNORECASE):
        return f"Over ${numbers[0]}"
    return value


def value_range(value: str) -> tuple[int | None, int | None, str]:
    label = canonical_amount(value)
    if label in VALUE_RANGES:
        minimum, maximum = VALUE_RANGES[label]
        return minimum, maximum, label
    numbers = [int(number.replace(",", "")) for number in re.findall(r"\d[\d,]*", label)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1], label
    if numbers and label.lower().startswith("over"):
        return numbers[0] + 1, None, label
    return None, None, label


def asset_class(asset: str, ticker: str | None) -> str:
    value = asset.upper()
    code_match = re.search(r"\[([A-Z]{2,4})\]", value)
    code = code_match.group(1) if code_match else ""
    if code in {"CR", "CO", "CT"} or any(token in value for token in ["BITCOIN", "ETHEREUM", "CRYPTOCURRENCY"]):
        return "crypto"
    if code in {"EF", "ETF"} or " ETF" in value or "EXCHANGE TRADED FUND" in value:
        return "etf"
    if code in {"MF", "CEF"} or "MUTUAL FUND" in value:
        return "mutual_fund"
    if code in {"DB", "DO", "GS", "MB", "CS"} or any(token in value for token in [" BOND", " NOTE", "TREASURY"]):
        return "fixed_income"
    if code == "OP" or " OPTION" in value:
        return "option"
    if code == "ST" or ticker:
        return "equity"
    return "unknown"


def asset_display_name(value: str) -> str:
    source_owner = re.search(r"\s+S\s+O:\s*", value, re.IGNORECASE)
    if source_owner and source_owner.start() > 3:
        value = value[: source_owner.start()]
    return re.sub(r"\s+", " ", value).strip()


def fetch_document(document: dict, redownload: bool) -> bytes:
    cache_path = CACHE / str(document["filing_year"]) / f"{document['clerk_document_id']}.pdf"
    if cache_path.exists() and not redownload:
        return cache_path.read_bytes()
    request = Request(document["source_url"], headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        content = response.read()
        content_type = response.headers.get("Content-Type", "")
    if not content.startswith(b"%PDF") and "pdf" not in content_type.lower():
        raise ValueError(f"Official source did not return a PDF ({content_type or 'unknown content type'})")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(content)
    return content


def parse_document(document: dict, redownload: bool) -> tuple[dict, list[dict]]:
    content = fetch_document(document, redownload)
    digest = hashlib.sha256(content).hexdigest()
    parser = get_parser("house-financial-disclosure")
    preview = parser.preview(
        content,
        filename=f"{document['clerk_document_id']}.pdf",
        content_type="application/pdf",
    )
    metadata = preview.output.get("metadata", {})
    if preview.normalized_record_count:
        status = "parser_preview"
    elif metadata.get("ocr_required"):
        status = "ocr_required"
    else:
        status = "no_transactions_detected"

    document_result = {
        **document,
        "file_hash": digest,
        "byte_count": len(content),
        "page_count": metadata.get("page_count"),
        "embedded_text_character_count": metadata.get("embedded_text_character_count", 0),
        "parser_status": status,
        "parser_version": "house-ptr-position-v1",
        "parser_transaction_count": preview.normalized_record_count,
        "parser_warnings": preview.warnings,
        "record_status": "official_house_parser_preview_not_promoted",
        "review_required_before_public_trade": True,
        "public_production_trade": False,
    }
    transactions = []
    rejected_rows = 0
    for row_number, row in enumerate(preview.transactions, start=1):
        minimum, maximum, amount_label = value_range(row.amount)
        if minimum is None:
            rejected_rows += 1
            continue
        source_page = (row.field_confidence or {}).get("source_page")
        reported_date = document["filing_date"]
        trade_date = row.transaction_date
        disclosure_lag = (date.fromisoformat(reported_date) - date.fromisoformat(trade_date)).days
        if disclosure_lag < 0:
            rejected_rows += 1
            continue
        display_name = asset_display_name(row.asset)
        row_asset_class = asset_class(display_name, row.ticker)
        quality_flags = []
        if disclosure_lag > 45:
            quality_flags.append("reported_after_45_days")
        if disclosure_lag > 365:
            quality_flags.append("amendment_or_date_review_required")
        if row_asset_class == "unknown":
            quality_flags.append("asset_class_unresolved")
        transactions.append(
            {
                "id": f"{document['document_id']}-row-{row_number:04d}",
                "document_id": document["document_id"],
                "official_id": document["official_id"],
                "full_name": document["official_name"],
                "branch": "Legislative",
                "chamber": "House",
                "trade_date": trade_date,
                "reported_date": reported_date,
                "action": row.transaction_type,
                "owner": row.owner,
                "raw_asset_text": row.asset,
                "asset_display_name": display_name,
                "ticker": row.ticker,
                "asset_class": row_asset_class,
                "value_range_label": amount_label,
                "value_range_min": minimum,
                "value_range_max": maximum,
                "disclosure_lag_days": disclosure_lag,
                "parsing_confidence": row.confidence,
                "field_confidence": row.field_confidence or {},
                "source_url": document["source_url"],
                "source_page": source_page,
                "source_file_hash": digest,
                "source_tier": "official",
                "record_status": "official_house_parser_preview_not_promoted",
                "confidence_label": "Official House Clerk PTR parser preview; review required",
                "review_required_before_public_trade": True,
                "public_production_trade": False,
                "data_quality_flags": quality_flags,
            }
        )
    document_result["parser_rejected_transaction_count"] = rejected_rows
    if rejected_rows:
        document_result["parser_warnings"] = [
            *document_result["parser_warnings"],
            f"{rejected_rows} extracted row(s) were withheld because the disclosure amount range was not recognized.",
        ]
    return document_result, transactions


def existing_output() -> dict:
    if not OUTPUT.exists():
        return {"documents": [], "transactions": []}
    manifest = json.loads(OUTPUT.read_text())
    if manifest.get("schema_version") != "house-ptr-transactions-manifest-v2":
        return manifest
    documents = []
    transactions = []
    for record in manifest.get("year_partitions", {}).values():
        partition = json.loads((ROOT / record["path"]).read_text())
        documents.extend(partition.get("documents", []))
        transactions.extend(partition.get("transactions", []))
    return {"documents": documents, "transactions": transactions}


def build_output(documents: list[dict], transactions: list[dict]) -> dict:
    duplicate_groups = {}
    for row in transactions:
        row.pop("duplicate_candidate", None)
        row.pop("duplicate_candidate_group_id", None)
        row["data_quality_flags"] = [
            flag for flag in row.get("data_quality_flags", []) if flag != "possible_duplicate"
        ]
        signature = "|".join(
            str(value or "").lower()
            for value in [
                row.get("official_id"),
                row.get("trade_date"),
                row.get("action"),
                row.get("owner"),
                row.get("asset_display_name"),
                row.get("value_range_label"),
            ]
        )
        duplicate_groups.setdefault(signature, []).append(row)
    duplicate_candidate_count = 0
    duplicate_group_count = 0
    for signature, rows in duplicate_groups.items():
        if len(rows) < 2:
            continue
        duplicate_group_count += 1
        duplicate_candidate_count += len(rows)
        group_id = f"house-duplicate-{hashlib.sha256(signature.encode()).hexdigest()[:16]}"
        for row in rows:
            row["duplicate_candidate"] = True
            row["duplicate_candidate_group_id"] = group_id
            row["data_quality_flags"] = [*row.get("data_quality_flags", []), "possible_duplicate"]

    document_statuses = Counter(document.get("parser_status", "unknown") for document in documents)
    action_counts = Counter(row["action"] for row in transactions)
    asset_counts = Counter(row["asset_class"] for row in transactions)
    years = Counter(str(document["filing_year"]) for document in documents)
    return {
        "schema_version": "house-ptr-transactions-v1",
        "generated_at": date.today().isoformat(),
        "source": {
            "id": "house-financial-disclosure",
            "name": "Office of the Clerk, U.S. House of Representatives",
            "url": "https://disclosures-clerk.house.gov/financialdisclosure",
            "source_tier": "official",
        },
        "summary": {
            "processed_document_count": len(documents),
            "document_status_counts": dict(sorted(document_statuses.items())),
            "parser_preview_transaction_count": len(transactions),
            "official_count": len({row["official_id"] for row in transactions}),
            "action_counts": dict(sorted(action_counts.items())),
            "asset_class_counts": dict(sorted(asset_counts.items())),
            "document_counts_by_year": dict(sorted(years.items())),
            "review_required_transaction_count": len(transactions),
            "public_production_trade_count": 0,
            "withheld_unrecognized_amount_row_count": sum(
                document.get("parser_rejected_transaction_count", 0) for document in documents
            ),
            "duplicate_candidate_group_count": duplicate_group_count,
            "duplicate_candidate_transaction_count": duplicate_candidate_count,
        },
        "documents": sorted(documents, key=lambda row: (row["filing_date"], row["clerk_document_id"])),
        "transactions": sorted(transactions, key=lambda row: (row["trade_date"], row["id"])),
        "context_label": (
            "Official House Clerk PTR parser previews. Every row remains review-gated and is not a "
            "reviewed public-production trade. Image-only filings are reported as OCR required."
        ),
    }


def write_partitioned_output(
    documents: list[dict],
    transactions: list[dict],
    *,
    latest_batch_selected_document_count: int,
    latest_batch_error_count: int,
) -> None:
    global_output = build_output(documents, transactions)
    documents_by_year = {}
    transactions_by_year = {}
    for document in documents:
        documents_by_year.setdefault(int(document["filing_year"]), []).append(document)
    document_year_by_id = {document["document_id"]: int(document["filing_year"]) for document in documents}
    for row in transactions:
        year = document_year_by_id[row["document_id"]]
        transactions_by_year.setdefault(year, []).append(row)

    PARTITION_DIR.mkdir(parents=True, exist_ok=True)
    year_partitions = {}
    expected_paths = set()
    for year in sorted(documents_by_year):
        relative_path = Path("data") / "disclosures" / "house_ptr" / f"{year}.json"
        path = ROOT / relative_path
        expected_paths.add(path)
        payload = {
            "schema_version": "house-ptr-year-partition-v1",
            "generated_at": date.today().isoformat(),
            "filing_year": year,
            "summary": {
                "processed_document_count": len(documents_by_year[year]),
                "parser_preview_transaction_count": len(transactions_by_year.get(year, [])),
                "official_count": len({row["official_id"] for row in transactions_by_year.get(year, [])}),
                "public_production_trade_count": 0,
            },
            "documents": sorted(
                documents_by_year[year], key=lambda row: (row["filing_date"], row["clerk_document_id"])
            ),
            "transactions": sorted(
                transactions_by_year.get(year, []), key=lambda row: (row["trade_date"], row["id"])
            ),
        }
        encoded = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
        path.write_bytes(encoded)
        year_partitions[str(year)] = {
            "path": str(relative_path),
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            **payload["summary"],
        }

    for stale_path in PARTITION_DIR.glob("*.json"):
        if stale_path not in expected_paths:
            stale_path.unlink()

    manifest = {
        "schema_version": "house-ptr-transactions-manifest-v2",
        "generated_at": date.today().isoformat(),
        "source": global_output["source"],
        "summary": {
            **global_output["summary"],
            "latest_batch_selected_document_count": latest_batch_selected_document_count,
            "latest_batch_error_count": latest_batch_error_count,
        },
        "year_partitions": year_partitions,
        "context_label": global_output["context_label"],
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true", help="Reparse selected documents using the local cache.")
    parser.add_argument("--redownload", action="store_true", help="Redownload and reparse selected documents.")
    args = parser.parse_args()
    index = json.loads(INDEX.read_text())
    existing = existing_output()
    existing_documents = {document["document_id"]: document for document in existing.get("documents", [])}
    existing_transactions = existing.get("transactions", [])

    selected = [
        document
        for document in index["documents"]
        if document.get("match_status") == "matched"
        and args.start_year <= document["filing_year"] <= args.end_year
        and (args.refresh or args.redownload or document["document_id"] not in existing_documents)
    ]
    if args.limit is not None:
        selected = selected[: args.limit]
    refreshed_ids = {document["document_id"] for document in selected}
    transaction_rows = [
        row for row in existing_transactions if row.get("document_id") not in refreshed_ids
    ]
    document_rows = {
        document_id: document
        for document_id, document in existing_documents.items()
        if document_id not in refreshed_ids
    }

    failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(parse_document, document, args.redownload): document for document in selected}
        for completed, future in enumerate(as_completed(futures), start=1):
            document = futures[future]
            try:
                result, rows = future.result()
                document_rows[result["document_id"]] = result
                transaction_rows.extend(rows)
            except Exception as exc:
                failure = {
                    **document,
                    "parser_status": "error",
                    "parser_error": f"{type(exc).__name__}: {exc}",
                    "record_status": "official_house_document_parse_error",
                    "review_required_before_public_trade": True,
                    "public_production_trade": False,
                }
                document_rows[document["document_id"]] = failure
                failures.append(failure)
            if completed % 50 == 0 or completed == len(selected):
                with PRINT_LOCK:
                    print(f"Processed {completed}/{len(selected)} House PTR documents")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    write_partitioned_output(
        list(document_rows.values()),
        transaction_rows,
        latest_batch_selected_document_count=len(selected),
        latest_batch_error_count=len(failures),
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
