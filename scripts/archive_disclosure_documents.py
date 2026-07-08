#!/usr/bin/env python3
"""Archive approved public disclosure documents with hashes and parser fixtures."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.parsers import get_parser


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "disclosures" / "oge_retrieval_manifest.json"
ARCHIVE_ROOT = ROOT / "data" / "raw_documents"
OUTPUT = ROOT / "data" / "disclosures" / "raw_document_archive_index.json"
OGE_FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "parsers" / "oge_public_sample_fixture.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "document"


def filename_from_url(url: str, fallback: str) -> str:
    parsed_name = Path(urlparse(url).path).name
    return parsed_name or fallback


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fetch(url: str) -> tuple[bytes, str | None]:
    request = Request(
        url,
        headers={
            "User-Agent": "CivicLedger research crawler/0.1 (+https://github.com/dtrezise/CivicLedger)"
        },
    )
    with urlopen(request, timeout=45) as response:
        return response.read(), response.headers.get("Content-Type")


def build_parser_fixture(archive_row: dict, content: bytes) -> dict:
    parser = get_parser(archive_row["source_id"])
    preview = parser.preview(
        content,
        filename=Path(archive_row["storage_path"]).name,
        content_type=archive_row["content_type"] or "application/octet-stream",
    )
    return {
        "generated_at": now_iso(),
        "schema_version": "oge-public-sample-parser-fixture-v1",
        "source_id": archive_row["source_id"],
        "document_id": archive_row["document_id"],
        "document_type": archive_row["document_type"],
        "file_hash": archive_row["file_hash"],
        "byte_count": archive_row["byte_count"],
        "content_type": archive_row["content_type"],
        "review_status": "parser_fixture_not_public_production",
        "normalized_record_count": preview.normalized_record_count,
        "filer_name": preview.filer_name,
        "report_type": preview.report_type,
        "filing_date": preview.filing_date,
        "transactions": [transaction.to_dict() for transaction in preview.transactions],
        "warnings": preview.warnings,
        "text_sample": preview.output.get("text_sample", "")[:1500],
    }


def archive_document(source: dict, row: dict) -> dict:
    if not row.get("auto_download_allowed"):
        return {
            "document_id": row["document_id"],
            "source_id": source["id"],
            "expected_official_id": row.get("expected_official_id"),
            "expected_official_name": row.get("expected_official_name"),
            "document_type": row["document_type"],
            "source_url": row["source_url"],
            "retrieval_mode": row["retrieval_mode"],
            "source_status": row["source_status"],
            "archive_status": "pending_manual_or_acknowledged_retrieval",
            "review_required_before_public_trade": True,
            "notes": row.get("notes"),
        }

    content, content_type = fetch(row["source_url"])
    file_hash = sha256_bytes(content)
    extension = Path(filename_from_url(row["source_url"], row["document_id"])).suffix or ".bin"
    filename = f"{file_hash[:16]}-{slugify(row['document_id'])}{extension}"
    archive_dir = ARCHIVE_ROOT / source["id"]
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / filename
    if not archive_path.exists():
        archive_path.write_bytes(content)

    archive_row = {
        "document_id": row["document_id"],
        "source_id": source["id"],
        "expected_official_id": row.get("expected_official_id"),
        "expected_official_name": row.get("expected_official_name"),
        "document_type": row["document_type"],
        "source_url": row["source_url"],
        "retrieval_mode": row["retrieval_mode"],
        "source_status": row["source_status"],
        "archive_status": "archived",
        "retrieved_at": now_iso(),
        "content_type": content_type,
        "byte_count": len(content),
        "file_hash": file_hash,
        "hash_algorithm": "sha256",
        "storage_path": str(archive_path.relative_to(ROOT)),
        "review_required_before_public_trade": True,
        "notes": row.get("notes"),
    }
    if row["document_id"] == "oge-public-278e-sample":
        OGE_FIXTURE.write_text(json.dumps(build_parser_fixture(archive_row, content), indent=2, sort_keys=True) + "\n")
    return archive_row


def build_index() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    source = manifest["source"]
    documents = [archive_document(source, row) for row in manifest["documents"]]
    archived = [row for row in documents if row["archive_status"] == "archived"]
    return {
        "generated_at": now_iso(),
        "schema_version": "raw-document-archive-index-v1",
        "context_label": (
            "Raw disclosure artifacts are archived with hashes before parser output or public trade rows. "
            "Pending rows require official-source retrieval and review."
        ),
        "source": source,
        "summary": {
            "document_count": len(documents),
            "archived_document_count": len(archived),
            "pending_document_count": len(documents) - len(archived),
            "review_required_before_public_trade": True,
        },
        "documents": documents,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    index = build_index()
    OUTPUT.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")
    if OGE_FIXTURE.exists():
        print(f"Wrote {OGE_FIXTURE}")


if __name__ == "__main__":
    main()
