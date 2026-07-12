from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.services.house_disclosures import (
    house_ocr_priority_record,
    reconcile_house_amendments,
)
from app.services.promotion import (
    build_parser_preview_review_dataset,
    evaluate_parser_preview_record,
    evaluate_preview_artifact_evidence,
)
from app.services.senate_disclosures import (
    reconcile_senate_amendments,
    senate_ocr_priority_record,
)


HASH = "a" * 64


def test_house_ocr_priority_is_metadata_only_and_deterministic():
    document = {
        "document_id": "house-ptr-2026-1",
        "source_id": "house-financial-disclosure",
        "source_url": "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/1.pdf",
        "file_hash": HASH,
        "filing_date": "2026-07-01",
        "parser_status": "ocr_required",
        "match_status": "matched",
        "match_score": 12,
        "official_id": "congress:A000001",
        "official_name": "Alex Example",
        "page_count": 2,
        "byte_count": 1234,
    }

    first = house_ocr_priority_record(document, as_of=date(2026, 7, 12))
    second = house_ocr_priority_record(dict(document), as_of=date(2026, 7, 12))

    assert first == second
    assert first["eligible_for_ocr_batch"] is True
    assert first["priority_tier"] == "highest_confidence"
    assert first["ocr_content_present"] is False
    assert first["transaction_rows_created"] == 0
    assert "ocr_text" not in first


def test_senate_ocr_priority_requires_official_media_manifest():
    document = {
        "document_id": "senate-ptr-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "source_id": "senate-public-financial-disclosure",
        "source_url": (
            "https://efdsearch.senate.gov/search/view/paper/"
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/"
        ),
        "source_page_sha256": HASH,
        "source_media_urls": [
            "https://efd-media-public.senate.gov/media/2026/0/000/001/000001001.gif"
        ],
        "source_page_byte_count": 4567,
        "filing_date": "2026-07-01",
        "parser_status": "paper_images_review_required",
        "match_status": "matched",
        "match_score": 9,
        "official_id": "congress:A000001",
        "official_name": "Alex Example",
        "page_identity_consistent": True,
    }

    record = senate_ocr_priority_record(document, as_of=date(2026, 7, 12))

    assert record["eligible_for_ocr_batch"] is True
    assert record["source_page_count"] == 1
    assert record["processing_status"] == "metadata_prioritized_ocr_not_run"


def test_amendment_reconciliation_is_evidence_bearing_and_non_destructive():
    original = {
        "document_id": "house-a",
        "official_id": "congress:A000001",
        "report_type": "Periodic Transaction Report",
    }
    amendment = {
        **original,
        "document_id": "house-b",
        "report_type": "Periodic Transaction Report Amendment",
        "amends_document_id": "house-a",
    }
    reconciled_house = reconcile_house_amendments([original, amendment])

    assert "amendment_status" not in amendment
    assert reconciled_house[1]["supersedes_document_id"] == "house-a"
    assert reconciled_house[1]["amendment_linkage_confidence"] == "explicit_resolved"
    assert reconciled_house[1]["amendment_reconciliation_evidence"][0]["field"] == "amends_document_id"
    assert all(row["source_record_preserved"] for row in reconciled_house)

    senate_amendment_one = {
        "document_id": "senate-a",
        "senate_report_uuid": "a",
        "official_id": "congress:A000001",
        "portal_report_title": "Periodic Transaction Report for 07/01/2026 (Amendment)",
        "filing_date": "2026-07-01",
        "is_amendment": True,
    }
    senate_amendment_two = {
        **senate_amendment_one,
        "document_id": "senate-b",
        "senate_report_uuid": "b",
    }
    reconciled_senate = reconcile_senate_amendments(
        [senate_amendment_two, senate_amendment_one]
    )

    assert all(row["candidate_supersedes_document_id"] is None for row in reconciled_senate)
    assert all(row["amendment_status"] == "predecessor_not_identified" for row in reconciled_senate)


def preview_document() -> dict:
    return {
        "document_id": "senate-ptr-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "source_id": "senate-public-financial-disclosure",
        "source_tier": "official",
        "source_url": (
            "https://efdsearch.senate.gov/search/view/ptr/"
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/"
        ),
        "source_page_sha256": HASH,
        "filing_date": "2026-07-02",
        "parser_status": "parser_preview",
        "match_status": "matched",
        "official_id": "congress:A000001",
    }


def preview_transaction() -> dict:
    return {
        "id": "senate-row-1",
        "document_id": "senate-ptr-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "official_id": "congress:A000001",
        "trade_date": "2026-07-01",
        "reported_date": "2026-07-02",
        "action": "BUY",
        "asset_display_name": "Example Corp.",
        "value_range_label": "$1,001 - $15,000",
        "source_url": (
            "https://efdsearch.senate.gov/search/view/ptr/"
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/"
        ),
        "source_file_hash": HASH,
        "source_tier": "official",
        "source_row": 1,
        "parsing_confidence": 0.99,
        "field_confidence": {
            "transaction_date": 1.0,
            "asset": 1.0,
            "transaction_type": 1.0,
            "amount": 1.0,
        },
        "data_quality_flags": [],
        "public_production_trade": False,
    }


def test_systematic_preview_review_preserves_zero_production_without_attestation():
    dataset = build_parser_preview_review_dataset(
        [preview_document()],
        [preview_transaction()],
        generated_at="2026-07-12",
    )

    assert dataset["summary"]["evaluated_record_count"] == 1
    assert dataset["summary"]["automated_source_criteria_pass_count"] == 1
    assert dataset["summary"]["evidence_review_queue_count"] == 1
    assert dataset["summary"]["public_production_trade_count"] == 0
    assert dataset["promotions"] == []
    assert "explicit_public_production_decision" in dataset["evidence_review_queue"][0]["failed_criteria"]


def test_preview_promotes_only_when_review_evidence_matches_source():
    document = preview_document()
    transaction = preview_transaction()
    transaction["review_evidence"] = {
        "decision": "approve_public_production",
        "reviewed_by": "reviewer@example.test",
        "reviewed_at": "2026-07-12T12:00:00Z",
        "source_file_hash": HASH,
        "document_id": document["document_id"],
    }

    evaluation = evaluate_parser_preview_record(transaction, document)
    dataset = build_parser_preview_review_dataset(
        [document],
        [transaction],
        generated_at="2026-07-12",
    )

    assert evaluation["eligible_for_public_production"] is True
    assert dataset["summary"]["public_production_trade_count"] == 1
    assert dataset["promotions"][0]["public_production_trade"] is True


def test_database_preview_gate_requires_matching_review_attestation():
    raw_id = uuid4()
    raw_document = SimpleNamespace(
        id=raw_id,
        provenance_complete=True,
        file_hash=HASH,
        retrieval_source="oge-individual-disclosures",
        source_url="https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures",
    )
    preview = SimpleNamespace(
        source_id="oge-individual-disclosures",
        parser_output={
            "normalized_record_count": 1,
            "transactions": [
                {
                    "asset": "Example Corp.",
                    "transaction_type": "BUY",
                    "transaction_date": "2026-07-01",
                    "amount": "$1,001 - $15,000",
                    "confidence": 0.99,
                }
            ],
        },
    )

    blockers = evaluate_preview_artifact_evidence(
        preview,
        raw_document,
        reviewer="reviewer@example.test",
    )
    assert "explicit_public_production_decision_missing" in blockers

    preview.parser_output["review_evidence"] = {
        "decision": "approve_public_production",
        "reviewed_by": "reviewer@example.test",
        "reviewed_at": "2026-07-12T12:00:00Z",
        "raw_document_id": str(raw_id),
        "source_file_hash": HASH,
        "transaction_count": 1,
        "person_name": "Alex Example",
        "branch": "Executive",
    }
    assert evaluate_preview_artifact_evidence(
        preview,
        raw_document,
        reviewer="reviewer@example.test",
        person_name="Alex Example",
        branch="Executive",
    ) == []
