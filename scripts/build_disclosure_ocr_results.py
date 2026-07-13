#!/usr/bin/env python3
"""OCR prioritized official disclosure images into review-only evidence artifacts."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.disclosure_ocr import (  # noqa: E402
    document_quality,
    enrich_page_quality,
    official_source_url,
    page_quality,
)


PRIORITIES = ROOT / "data" / "disclosures" / "disclosure_ocr_priority_batches.json"
OUTPUT = ROOT / "data" / "disclosures" / "disclosure_ocr_results.json"
RESULT_DIR = ROOT / "data" / "disclosures" / "ocr_results"


def fetch_official(url: str) -> bytes:
    if not official_source_url(url):
        raise ValueError(f"OCR acquisition rejected non-official URL: {url}")
    request = Request(url, headers={"User-Agent": "CivicLedger/1.0 evidence-research"})
    with urlopen(request, timeout=45) as response:
        return response.read()


def tesseract_version() -> str:
    result = subprocess.run(["tesseract", "--version"], check=True, capture_output=True, text=True)
    return result.stdout.splitlines()[0].strip()


def parse_tsv(body: str) -> tuple[str, list[dict], int, int]:
    rows = list(csv.DictReader(io.StringIO(body), delimiter="\t"))
    words = []
    line_words: dict[tuple[int, int, int], list[tuple[int, str]]] = {}
    width = height = 0
    for row in rows:
        try:
            level = int(row.get("level") or 0)
            width = max(width, int(row.get("left") or 0) + int(row.get("width") or 0))
            height = max(height, int(row.get("top") or 0) + int(row.get("height") or 0))
        except ValueError:
            continue
        text = (row.get("text") or "").strip()
        if level != 5 or not text:
            continue
        confidence = float(row.get("conf") or -1)
        word = {
            "text": text,
            "confidence": confidence,
            "block": int(row.get("block_num") or 0),
            "paragraph": int(row.get("par_num") or 0),
            "line": int(row.get("line_num") or 0),
            "word": int(row.get("word_num") or 0),
            "left": int(row.get("left") or 0),
            "top": int(row.get("top") or 0),
            "width": int(row.get("width") or 0),
            "height": int(row.get("height") or 0),
        }
        words.append(word)
        key = (word["block"], word["paragraph"], word["line"])
        line_words.setdefault(key, []).append((word["word"], text))
    lines = [" ".join(text for _, text in sorted(values)) for _, values in sorted(line_words.items())]
    return "\n".join(lines).strip(), words, width, height


def ocr_image(path: Path, *, page_number: int, source_url: str, source_hash: str) -> dict:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "--psm", "6", "tsv"],
        check=True,
        capture_output=True,
        text=True,
    )
    text, words, width, height = parse_tsv(result.stdout)
    quality = page_quality(text=text, words=words, width=width, height=height)
    return {
        "page_number": page_number,
        "source_url": source_url,
        "source_sha256": source_hash,
        "ocr_text": text,
        "quality": quality,
    }


def process_house(candidate: dict, work: Path) -> list[dict]:
    source = fetch_official(candidate["source_url"])
    digest = sha256(source).hexdigest()
    if digest != candidate["source_file_sha256"]:
        raise ValueError(f"House source hash mismatch for {candidate['document_id']}")
    pdf = work / "source.pdf"
    pdf.write_bytes(source)
    prefix = work / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", "200", str(pdf), str(prefix)],
        check=True,
        capture_output=True,
    )
    images = sorted(work.glob("page-*.png"))
    if len(images) != int(candidate["source_page_count"]):
        raise ValueError(f"House page count mismatch for {candidate['document_id']}")
    return [
        ocr_image(image, page_number=index, source_url=candidate["source_url"], source_hash=digest)
        for index, image in enumerate(images, 1)
    ]


def process_senate(candidate: dict, work: Path) -> list[dict]:
    pages = []
    for index, source_url in enumerate(candidate["source_media_urls"], 1):
        source = fetch_official(source_url)
        digest = sha256(source).hexdigest()
        suffix = Path(urlparse(source_url).path).suffix or ".gif"
        image = work / f"page-{index:04d}{suffix}"
        image.write_bytes(source)
        pages.append(ocr_image(image, page_number=index, source_url=source_url, source_hash=digest))
    return pages


def safe_name(document_id: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", document_id.lower()).strip("-")


def write_result(candidate: dict, pages: list[dict], *, engine_version: str) -> dict:
    quality = document_quality(pages)
    payload = {
        "schema_version": "disclosure-ocr-evidence-v2",
        "document_id": candidate["document_id"],
        "chamber": candidate["chamber"],
        "official_id": candidate.get("official_id"),
        "official_name": candidate.get("official_name"),
        "filing_date": candidate.get("filing_date"),
        "source_id": candidate.get("source_id"),
        "source_url": candidate.get("source_url"),
        "ocr_engine": engine_version,
        "review_boundary": "OCR evidence only; no transaction rows created and human review is required.",
        "source_acquisition_status": "all_official_source_pages_acquired",
        "transaction_rows_created": 0,
        "quality": quality,
        "pages": pages,
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path = RESULT_DIR / f"{safe_name(candidate['document_id'])}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return {
        "document_id": candidate["document_id"],
        "chamber": candidate["chamber"],
        "official_id": candidate.get("official_id"),
        "official_name": candidate.get("official_name"),
        "filing_date": candidate.get("filing_date"),
        "source_url": candidate.get("source_url"),
        "result_path": str(path.relative_to(ROOT)),
        "result_sha256": sha256(encoded).hexdigest(),
        **quality,
    }


def enrich_existing_result(path: Path) -> tuple[dict, bytes]:
    payload = json.loads(path.read_text())
    for page in payload.get("pages", []):
        page["quality"] = enrich_page_quality(
            text=page.get("ocr_text") or "",
            quality=page.get("quality") or {},
        )
    payload["schema_version"] = "disclosure-ocr-evidence-v2"
    payload["source_acquisition_status"] = "all_official_source_pages_acquired"
    payload["transaction_rows_created"] = 0
    payload["quality"] = document_quality(payload.get("pages", []))
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return payload, encoded


def combined_counts(records: list[dict], field: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for record in records:
        for key, value in record.get(field, {}).items():
            output[key] = output.get(key, 0) + int(value)
    return dict(sorted(output.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-per-chamber", type=int, default=50)
    parser.add_argument("--chamber", choices=("all", "house", "senate"), default="all")
    parser.add_argument("--acknowledge-senate-terms", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.chamber in {"all", "senate"} and not args.acknowledge_senate_terms:
        parser.error("Senate OCR requires --acknowledge-senate-terms")
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        parser.error("tesseract and pdftoppm are required")

    priority = json.loads(PRIORITIES.read_text())
    engine_version = tesseract_version()
    records = []
    failures = []
    for batch in priority["batches"]:
        if args.chamber != "all" and batch["chamber"].lower() != args.chamber:
            continue
        for candidate in batch["candidates"][: max(0, args.limit_per_chamber)]:
            result_path = RESULT_DIR / f"{safe_name(candidate['document_id'])}.json"
            if result_path.exists() and not args.refresh:
                payload, encoded = enrich_existing_result(result_path)
                records.append(
                    {
                        "document_id": payload["document_id"],
                        "chamber": payload["chamber"],
                        "official_id": payload.get("official_id"),
                        "official_name": payload.get("official_name"),
                        "filing_date": payload.get("filing_date"),
                        "source_url": payload.get("source_url"),
                        "result_path": str(result_path.relative_to(ROOT)),
                        "result_sha256": sha256(encoded).hexdigest(),
                        **payload["quality"],
                    }
                )
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="civicledger-ocr-") as temp:
                    work = Path(temp)
                    pages = process_house(candidate, work) if batch["chamber"] == "House" else process_senate(candidate, work)
                records.append(write_result(candidate, pages, engine_version=engine_version))
            except Exception as exc:  # Failure is evidence; the batch must continue.
                failures.append(
                    {
                        "document_id": candidate["document_id"],
                        "chamber": batch["chamber"],
                        "source_url": candidate.get("source_url"),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

    records.sort(key=lambda row: (row["chamber"], row["filing_date"] or "", row["document_id"]))
    failures.sort(key=lambda row: (row["chamber"], row["document_id"]))
    status_counts: dict[str, int] = {}
    for row in records:
        status_counts[row["processing_status"]] = status_counts.get(row["processing_status"], 0) + 1
    manifest = {
        "generated_at": priority["generated_at"],
        "schema_version": "disclosure-ocr-results-manifest-v2",
        "ocr_engine": engine_version,
        "context_label": "Official-source OCR evidence requiring human review. OCR text is not a reviewed transaction record.",
        "summary": {
            "attempted_document_count": len(records) + len(failures),
            "completed_document_count": len(records),
            "failed_document_count": len(failures),
            "processed_page_count": sum(row["page_count"] for row in records),
            "readable_page_count": sum(row["readable_page_count"] for row in records),
            "ocr_word_count": sum(row["word_count"] for row in records),
            "ocr_character_count": sum(row["character_count"] for row in records),
            "processing_status_counts": dict(sorted(status_counts.items())),
            "completed_chamber_counts": {
                chamber: sum(row["chamber"] == chamber for row in records)
                for chamber in ("House", "Senate")
            },
            "failed_chamber_counts": {
                chamber: sum(row["chamber"] == chamber for row in failures)
                for chamber in ("House", "Senate")
            },
            "page_review_status_counts": combined_counts(records, "page_review_status_counts"),
            "human_review_required_document_count": len(records),
            "transaction_rows_created": 0,
            "quality_dimensions": [
                "page_ocr_confidence",
                "page_layout_confidence",
                "field_label_confidence",
                "document_review_quality_score",
            ],
        },
        "records": records,
        "failures": failures,
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        f"Wrote {OUTPUT}: completed={len(records)} failed={len(failures)} "
        f"pages={manifest['summary']['processed_page_count']}"
    )


if __name__ == "__main__":
    main()
