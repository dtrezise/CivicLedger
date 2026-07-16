#!/usr/bin/env python3
"""Archive approved disclosure artifacts without bypassing source restrictions."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.parsers import get_parser
from app.services.official_sources import evaluate_source_access, source_restriction_metadata


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "disclosures" / "oge_retrieval_manifest.json"
ARCHIVE_ROOT = ROOT / "data" / "raw_documents"
OUTPUT = ROOT / "data" / "disclosures" / "raw_document_archive_index.json"
OGE_FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "parsers" / "oge_public_sample_fixture.json"
USER_AGENT = "CivicLedger research crawler/0.3 (+https://civic-ledger.dan-a2c.workers.dev/)"
TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/json": ".json",
    "text/csv": ".csv",
    "text/html": ".html",
    "text/plain": ".txt",
}


@dataclass(frozen=True)
class FetchResult:
    content: bytes
    content_type: str | None
    final_url: str
    status_code: int
    attempts: list[dict]
    response_metadata: dict


class OfficialHostRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: list[str]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_official_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def content_hashes(content: bytes) -> dict[str, str]:
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "sha512": hashlib.sha512(content).hexdigest(),
    }


def validate_official_url(url: str, allowed_hosts: list[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in set(allowed_hosts):
        raise ValueError(f"URL is outside the configured official-source hosts: {url}")
    if parsed.username or parsed.password:
        raise ValueError("Official-source URLs must not contain credentials")


def normalized_content_type(value: str | None) -> str | None:
    return value.split(";", 1)[0].strip().lower() if value else None


def extension_for(content_type: str | None, source_url: str) -> str:
    normalized = normalized_content_type(content_type)
    if normalized in CONTENT_TYPE_EXTENSIONS:
        return CONTENT_TYPE_EXTENSIONS[normalized]
    suffix = Path(urlparse(source_url).path).suffix.lower()
    if suffix and re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    guessed = mimetypes.guess_extension(normalized or "")
    return guessed or ".bin"


def fetch_with_retry(
    url: str,
    *,
    allowed_hosts: list[str],
    max_attempts: int = 3,
    timeout_seconds: float = 45,
    opener: Callable | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    validate_official_url(url, allowed_hosts)
    if opener is None:
        opener = build_opener(OfficialHostRedirectHandler(allowed_hosts)).open
    attempts = []
    for attempt_number in range(1, max_attempts + 1):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html,*/*"})
        try:
            with opener(request, timeout=timeout_seconds) as response:
                content = response.read()
                final_url = response.geturl()
                validate_official_url(final_url, allowed_hosts)
                if not content:
                    raise ValueError("Official source returned an empty response")
                content_type = response.headers.get("Content-Type")
                if urlparse(final_url).path.lower().endswith(".pdf"):
                    if normalized_content_type(content_type) != "application/pdf" or not content.startswith(b"%PDF"):
                        raise ValueError("Official PDF URL did not return a PDF payload")
                status_code = int(getattr(response, "status", 200))
                attempts.append({"attempt": attempt_number, "status": "success", "status_code": status_code})
                return FetchResult(
                    content=content,
                    content_type=content_type,
                    final_url=final_url,
                    status_code=status_code,
                    attempts=attempts,
                    response_metadata={
                        "etag": response.headers.get("ETag"),
                        "last_modified": response.headers.get("Last-Modified"),
                        "content_length": response.headers.get("Content-Length"),
                    },
                )
        except HTTPError as exc:
            retryable = exc.code in TRANSIENT_HTTP_STATUS_CODES
            attempts.append(
                {
                    "attempt": attempt_number,
                    "status": "http_error",
                    "status_code": exc.code,
                    "retryable": retryable,
                    "retry_after": exc.headers.get("Retry-After") if exc.headers else None,
                }
            )
            if not retryable or attempt_number == max_attempts:
                raise
        except URLError as exc:
            attempts.append(
                {"attempt": attempt_number, "status": "network_error", "retryable": True, "reason": str(exc.reason)}
            )
            if attempt_number == max_attempts:
                raise
        if attempt_number < max_attempts:
            sleep(float(2 ** (attempt_number - 1)))
    raise RuntimeError("Disclosure retrieval exhausted retries without a result")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


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


def restricted_archive_row(source: dict, row: dict, access: dict) -> dict:
    return {
        "document_id": row["document_id"],
        "source_id": source["id"],
        "expected_official_id": row.get("expected_official_id"),
        "expected_official_name": row.get("expected_official_name"),
        "identity_status": row.get("identity_status", "expected_identity_unverified"),
        "document_type": row["document_type"],
        "source_url": row["source_url"],
        "retrieval_mode": row["retrieval_mode"],
        "source_status": row["source_status"],
        "archive_status": "source_restriction_review_required",
        "access_decision": access,
        "retrieval_attempted": False,
        "review_required_before_public_trade": True,
        "notes": row.get("notes"),
    }


def archive_document(
    source: dict,
    row: dict,
    *,
    archive_root: Path = ARCHIVE_ROOT,
    fetcher: Callable[..., FetchResult] = fetch_with_retry,
) -> dict:
    restriction = source_restriction_metadata(source["id"])
    automated = bool(row.get("auto_download_allowed"))
    access = evaluate_source_access(
        source["id"],
        automated=automated,
        terms_acknowledged=bool(row.get("terms_acknowledged")),
        requester_identity_supplied=bool(row.get("requester_identity_supplied")),
    )
    if not automated or access["access_status"] != "allowed":
        if not automated and not access["restriction_reasons"]:
            access["restriction_reasons"] = ["manifest_requires_manual_or_acknowledged_retrieval"]
            access["access_status"] = "restricted"
        return restricted_archive_row(source, row, access)

    result = fetcher(row["source_url"], allowed_hosts=restriction["allowed_hosts"])
    hashes = content_hashes(result.content)
    expected_sha256 = row.get("expected_sha256")
    if expected_sha256 and expected_sha256.lower() != hashes["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {row['document_id']}")
    extension = extension_for(result.content_type, result.final_url)
    archive_path = archive_root / source["id"] / hashes["sha256"][:2] / f"{hashes['sha256']}{extension}"
    object_reused = archive_path.exists()
    if object_reused:
        if sha256_bytes(archive_path.read_bytes()) != hashes["sha256"]:
            raise ValueError(f"Existing archive object failed hash verification: {archive_path}")
    else:
        atomic_write(archive_path, result.content)

    try:
        storage_path = str(archive_path.relative_to(ROOT))
    except ValueError:
        storage_path = str(archive_path)
    archive_row = {
        "document_id": row["document_id"],
        "source_id": source["id"],
        "expected_official_id": row.get("expected_official_id"),
        "expected_official_name": row.get("expected_official_name"),
        "identity_status": row.get("identity_status", "expected_identity_unverified"),
        "document_type": row["document_type"],
        "source_url": row["source_url"],
        "final_url": result.final_url,
        "retrieval_mode": row["retrieval_mode"],
        "source_status": row["source_status"],
        "archive_status": "archived",
        "archive_object_status": "reused" if object_reused else "new",
        "retrieved_at": now_iso(),
        "retrieval_attempted": True,
        "retrieval_attempts": result.attempts,
        "http_status_code": result.status_code,
        "content_type": normalized_content_type(result.content_type),
        "byte_count": len(result.content),
        "file_hash": hashes["sha256"],
        "hash_algorithm": "sha256",
        "content_hashes": hashes,
        "storage_path": storage_path,
        "content_addressed": True,
        "object_reused": object_reused,
        "response_metadata": result.response_metadata,
        "access_decision": access,
        "review_required_before_public_trade": True,
        "notes": row.get("notes"),
    }
    if row["document_id"] == "oge-public-278e-sample":
        OGE_FIXTURE.write_text(json.dumps(build_parser_fixture(archive_row, result.content), indent=2, sort_keys=True) + "\n")
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
            "Raw disclosure artifacts use content-addressed storage and remain review-gated. "
            "Restricted rows record policy decisions without attempting retrieval."
        ),
        "source": source,
        "summary": {
            "document_count": len(documents),
            "archived_document_count": len(archived),
            "restricted_document_count": len(documents) - len(archived),
            "pending_document_count": len(documents) - len(archived),
            "reused_archive_object_count": sum(row.get("object_reused", False) for row in archived),
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
