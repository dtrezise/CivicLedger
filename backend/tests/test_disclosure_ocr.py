import hashlib
import json
from pathlib import Path

from app.services.disclosure_ocr import (
    document_quality,
    enrich_page_quality,
    official_source_url,
    page_quality,
)
from app.services.house_disclosures import (
    house_transaction_signature,
    reconcile_house_amendments,
)
from app.services.senate_disclosures import (
    reconcile_senate_amendments,
    senate_transaction_signature,
)


ROOT = Path(__file__).resolve().parents[2]


WORDS = [
    {"text": text, "confidence": 95.0, "block": 1, "paragraph": 1, "line": line}
    for line, text in enumerate(
        ["Transaction", "Date", "Asset", "Owner", "Amount", "Notification", "Type"],
        1,
    )
]


def test_official_asset_allow_list_is_exact():
    assert official_source_url(
        "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/1.pdf"
    )
    assert official_source_url(
        "https://efd-media-public.senate.gov/media/2026/2/000/000/000000112.gif"
    )
    assert not official_source_url("https://example.com/public_disc/ptr-pdfs/2026/1.pdf")
    assert not official_source_url(
        "https://efd-media-public.senate.gov/media/2026/page.gif?redirect=1"
    )


def test_tesseract_page_metrics_preserve_mechanical_text_and_confidence():
    text = "Transaction Date\nAsset Owner\nAmount\nNotification Date\nTransaction Type"
    quality = page_quality(text=text, words=WORDS, width=1000, height=1400)

    assert quality["word_count"] == 7
    assert quality["ocr_confidence"] == 0.95
    assert quality["field_label_confidence"]["transaction_date"] == 0.95
    assert quality["field_label_confidence"]["asset"] > 0.9
    assert quality["transaction_form_candidate"] is True
    assert 0 < quality["layout_confidence"] < 1


def test_existing_ocr_evidence_can_be_enriched_without_repeating_ocr():
    legacy = {
        "mean_word_confidence": 88.0,
        "word_count": 120,
        "line_count": 25,
        "layout_block_count": 4,
        "character_count": 900,
        "quality_score": 82.0,
        "review_status": "high_quality_ocr_review_required",
    }
    enriched = enrich_page_quality(text="Asset Owner Transaction Date Amount", quality=legacy)
    document = document_quality([{"quality": enriched}])

    assert enriched["review_quality_score"] == 0.82
    assert enriched["field_label_confidence"]["asset"] == 0.88
    assert document["mean_review_quality_score"] == 0.82
    assert document["transaction_rows_created"] == 0


def senate_document(document_id: str, *, amendment: bool, signature: str) -> dict:
    suffix = " (Amendment)" if amendment else ""
    return {
        "document_id": document_id,
        "senate_report_uuid": document_id,
        "official_id": "congress:A000001",
        "portal_report_title": f"Periodic Transaction Report for 07/01/2026{suffix}",
        "report_type": "periodic_transaction_report",
        "filing_date": "2026-07-01",
        "is_amendment": amendment,
        "transaction_signatures": [signature],
    }


def test_senate_amendment_matching_uses_report_date_and_transaction_signature():
    signature = senate_transaction_signature(
        {
            "official_id": "congress:A000001",
            "trade_date": "2026-06-20",
            "action": "BUY",
            "owner": "Self",
            "asset_display_name": "Example Corp",
            "ticker": "EXM",
            "value_range_label": "$1,001 - $15,000",
        }
    )
    original = senate_document("original", amendment=False, signature=signature)
    amendment = senate_document("amendment", amendment=True, signature=signature)

    reconciled = reconcile_senate_amendments([amendment, original])
    linked = next(row for row in reconciled if row["is_amendment"])
    candidate = linked["amendment_reconciliation_evidence"][1]["candidate_evidence"][0]

    assert linked["candidate_supersedes_document_id"] == "original"
    assert linked["amendment_linkage_confidence"] == "candidate_date_and_signature_evidence"
    assert candidate["exact_report_date_match"] is True
    assert candidate["exact_transaction_signature_overlap_count"] == 1
    assert candidate["transaction_signature_jaccard_similarity"] == 1.0


def test_senate_amendment_matching_refuses_tied_candidates():
    signature = "a" * 64
    originals = [
        senate_document("original-a", amendment=False, signature=signature),
        senate_document("original-b", amendment=False, signature=signature),
    ]
    amendment = senate_document("amendment", amendment=True, signature=signature)

    linked = next(
        row for row in reconcile_senate_amendments([*originals, amendment]) if row["is_amendment"]
    )

    assert linked["candidate_supersedes_document_id"] is None
    assert linked["amendment_status"] == "ambiguous_predecessor_candidates"
    assert linked["amendment_linkage_confidence"] == "ambiguous_scored_candidates"


def test_house_explicit_amendment_link_records_date_and_signature_evidence():
    signature = house_transaction_signature(
        {
            "official_id": "congress:A000001",
            "trade_date": "2026-06-20",
            "action": "BUY",
            "owner": "Self",
            "asset_display_name": "Example Corp",
            "ticker": "EXM",
            "value_range_label": "$1,001 - $15,000",
        }
    )
    original = {
        "document_id": "house-original",
        "official_id": "congress:A000001",
        "report_type": "periodic_transaction_report",
        "filing_date": "2026-07-01",
        "transaction_signatures": [signature],
    }
    amendment = {
        **original,
        "document_id": "house-amendment",
        "filing_date": "2026-07-02",
        "amends_document_id": "house-original",
    }

    linked = reconcile_house_amendments([original, amendment])[1]
    date_evidence = linked["amendment_reconciliation_evidence"][1]
    signature_evidence = linked["amendment_reconciliation_evidence"][2]

    assert date_evidence["day_gap"] == 1
    assert date_evidence["chronologically_consistent"] is True
    assert signature_evidence["exact_overlap_count"] == 1
    assert signature_evidence["jaccard_similarity"] == 1.0


def test_checked_in_ocr_manifest_and_shards_preserve_evidence_boundaries():
    manifest = json.loads(
        (ROOT / "data/disclosures/disclosure_ocr_results.json").read_text()
    )

    assert manifest["schema_version"] == "disclosure-ocr-results-manifest-v2"
    assert manifest["summary"]["completed_document_count"] == 100
    assert manifest["summary"]["failed_document_count"] == 0
    assert manifest["summary"]["processed_page_count"] >= 500
    assert manifest["summary"]["transaction_rows_created"] == 0
    assert manifest["summary"]["completed_chamber_counts"] == {"House": 50, "Senate": 50}

    page_count = 0
    for record in manifest["records"]:
        path = ROOT / record["result_path"]
        encoded = path.read_bytes()
        assert hashlib.sha256(encoded).hexdigest() == record["result_sha256"]
        document = json.loads(encoded)
        assert document["transaction_rows_created"] == 0
        assert document["source_acquisition_status"] == "all_official_source_pages_acquired"
        assert document["quality"]["human_review_required"] is True
        for page in document["pages"]:
            page_count += 1
            quality = page["quality"]
            assert hashlib.sha256(page["ocr_text"].encode()).hexdigest() == quality[
                "ocr_text_sha256"
            ]
            assert set(quality["field_label_confidence"]) == {
                "amount",
                "asset",
                "notification_date",
                "owner",
                "transaction_date",
                "transaction_type",
            }
            assert all(
                0 <= quality[field] <= 1
                for field in ("ocr_confidence", "layout_confidence", "review_quality_score")
            )
    assert page_count == manifest["summary"]["processed_page_count"]


def test_checked_in_amendment_reconciliation_is_non_destructive_and_evidence_scored():
    dataset = json.loads(
        (ROOT / "data/disclosures/disclosure_amendment_reconciliation.json").read_text()
    )
    records = dataset["reconciliations"]
    linked = [record for record in records if record["candidate_supersedes_document_id"]]

    assert dataset["schema_version"] == "disclosure-amendment-reconciliation-v2"
    assert dataset["summary"]["destructive_change_count"] == 0
    assert dataset["summary"]["source_record_preserved_count"] == len(records)
    assert dataset["summary"]["linked_candidate_count"] == len(linked)
    assert dataset["summary"]["transaction_signature_evidence_link_count"] > 0
    assert all(record["reconciliation_action"] == "annotate_only" for record in records)
    assert all(record["source_record_preserved"] for record in records)
