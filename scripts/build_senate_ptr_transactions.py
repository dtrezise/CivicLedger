#!/usr/bin/env python3
"""Acquire indexed Senate PTR pages into review-gated transaction previews."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.senate_disclosures import (  # noqa: E402
    MIN_REQUEST_INTERVAL_SECONDS,
    SenateDisclosurePortalClient,
    SenatePortalAccessError,
    SenateReportPage,
    SenateTermsAcknowledgementRequired,
    VALIDATION_BIOGUIDE_ID,
    build_senate_ptr_transactions,
    load_report_page_import_manifest,
    report_page_import_manifest,
)


INDEX = ROOT / "data" / "disclosures" / "senate_disclosure_index.json"
OUTPUT = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"
CACHE = ROOT / ".cache" / "senate-report-pages"


def cached_page_path(source_url: str) -> Path:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    return CACHE / f"{digest}.json"


def load_cached_page(source_url: str) -> SenateReportPage | None:
    path = cached_page_path(source_url)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        body = base64.b64decode(payload["body_base64"], validate=True)
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return None
    if payload.get("source_url") != source_url:
        return None
    if hashlib.sha256(body).hexdigest() != payload.get("sha256"):
        return None
    return SenateReportPage(
        source_url=source_url,
        body=body,
        content_type=payload.get("content_type") or "text/html",
        status_code=int(payload.get("status_code") or 200),
        retrieved_at=payload.get("retrieved_at"),
    )


def save_cached_page(page: SenateReportPage) -> None:
    path = cached_page_path(page.source_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_url": page.source_url,
        "content_type": page.content_type,
        "status_code": page.status_code,
        "retrieved_at": page.retrieved_at,
        "sha256": page.sha256,
        "body_base64": base64.b64encode(page.body).decode("ascii"),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Paper-image reports are indexed as review work and never converted into transaction rows without "
            "OCR and human review. Use --export-manifest to create a hash-backed offline import."
        ),
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--bioguide-id",
        action="append",
        help=f"Process a matched Senator Bioguide ID; repeat as needed (default: {VALIDATION_BIOGUIDE_ID}).",
    )
    scope.add_argument(
        "--all-indexed",
        action="store_true",
        help="Process every matched document in the Senate disclosure index.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--request-interval",
        type=float,
        default=MIN_REQUEST_INTERVAL_SECONDS,
        help=f"Seconds between portal requests; cannot be below {MIN_REQUEST_INTERVAL_SECONDS:.1f}.",
    )
    parser.add_argument(
        "--acknowledge-senate-terms",
        action="store_true",
        help="Confirm review and acceptance of the official portal's prohibited-use acknowledgement.",
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore hash-verified cached report pages.")
    parser.add_argument(
        "--import-manifest",
        type=Path,
        help="Use captured official report HTML instead of live portal access.",
    )
    parser.add_argument(
        "--export-manifest",
        type=Path,
        help="Write exact live report HTML and hashes in the reproducible import format.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.request_interval < MIN_REQUEST_INTERVAL_SECONDS:
        parser.error(
            f"--request-interval cannot be below {MIN_REQUEST_INTERVAL_SECONDS:.1f} seconds"
        )
    if args.import_manifest and args.export_manifest:
        parser.error("--export-manifest is only available for live acquisition")
    if not INDEX.exists():
        parser.error(f"Senate disclosure index does not exist: {INDEX}")

    index = json.loads(INDEX.read_text())
    bioguide_ids = None if args.all_indexed else set(
        args.bioguide_id or [VALIDATION_BIOGUIDE_ID]
    )
    documents = [
        document
        for document in index.get("documents", [])
        if document.get("match_status") == "matched"
        and (bioguide_ids is None or document.get("bioguide_id") in bioguide_ids)
    ]
    documents.sort(key=lambda row: (row["filing_date"], row["senate_report_uuid"]))
    if args.limit is not None:
        documents = documents[: args.limit]
    if not documents:
        parser.error("No matched Senate PTR documents satisfy the selected scope")

    try:
        import_manifest_sha256 = None
        if args.import_manifest:
            imported_pages, import_manifest_sha256 = load_report_page_import_manifest(
                args.import_manifest.read_bytes()
            )
            missing = [
                document["source_url"]
                for document in documents
                if document["source_url"] not in imported_pages
            ]
            if missing:
                raise ValueError(
                    f"Import manifest is missing {len(missing)} selected report page(s); first missing URL: {missing[0]}"
                )
            pages = {document["source_url"]: imported_pages[document["source_url"]] for document in documents}
            acquisition_mode = "import_manifest"
        else:
            client = SenateDisclosurePortalClient(
                terms_acknowledged=args.acknowledge_senate_terms,
                request_interval_seconds=args.request_interval,
            )
            pages = {}
            for completed, document in enumerate(documents, start=1):
                page = None if args.refresh else load_cached_page(document["source_url"])
                if page is None:
                    page = client.fetch_report_page(document["source_url"])
                    save_cached_page(page)
                pages[page.source_url] = page
                if completed % 10 == 0 or completed == len(documents):
                    print(f"Acquired {completed}/{len(documents)} Senate PTR report pages")
            acquisition_mode = "live_portal"

        dataset = build_senate_ptr_transactions(
            documents,
            pages,
            acquisition_mode=acquisition_mode,
            request_interval_seconds=None if args.import_manifest else args.request_interval,
            import_manifest_sha256=import_manifest_sha256,
        )
    except (OSError, ValueError, SenatePortalAccessError, SenateTermsAcknowledgementRequired) as exc:
        raise SystemExit(
            f"Senate PTR acquisition failed: {type(exc).__name__}: {exc}\n"
            "No synthetic transaction rows were written. Use --import-manifest with a hash-backed "
            "senate-disclosure-import-v1 capture if acknowledged browser access is required."
        ) from exc

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")
    if args.export_manifest:
        args.export_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.export_manifest.write_text(
            json.dumps(report_page_import_manifest(pages), indent=2, sort_keys=True) + "\n"
        )
        print(f"Wrote {args.export_manifest}")


if __name__ == "__main__":
    main()
