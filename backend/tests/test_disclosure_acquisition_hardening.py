import hashlib
import importlib.util
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

from app.parsers.adapters import deterministic_transaction_signature, get_parser
from app.services.house_disclosures import (
    house_document_family_key,
    match_house_member,
    parse_house_index,
    reconcile_house_amendments,
    source_row_sha256,
)
from app.services.official_sources import evaluate_source_access, source_restriction_metadata
from app.services.senate_disclosures import (
    SenateReportPage,
    build_senate_ptr_transactions,
    parse_senate_report_html,
    reconcile_senate_amendments,
    senate_document_family_key,
    senate_transaction_signature,
)
FIXTURES = Path(__file__).parent / "fixtures" / "disclosures"
ARCHIVE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "archive_disclosure_documents.py"
ARCHIVE_SPEC = importlib.util.spec_from_file_location("archive_disclosure_documents", ARCHIVE_SCRIPT)
assert ARCHIVE_SPEC and ARCHIVE_SPEC.loader
archive_module = importlib.util.module_from_spec(ARCHIVE_SPEC)
sys.modules[ARCHIVE_SPEC.name] = archive_module
ARCHIVE_SPEC.loader.exec_module(archive_module)
FetchResult = archive_module.FetchResult
archive_document = archive_module.archive_document
validate_official_url = archive_module.validate_official_url
fetch_with_retry = archive_module.fetch_with_retry
SENATE_URL = "https://efdsearch.senate.gov/search/view/ptr/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/"


def test_restricted_judiciary_source_is_explicit_and_never_retrieved(tmp_path):
    calls = []
    source = {"id": "judicial-financial-disclosure"}
    row = {
        "document_id": "judicial-example",
        "document_type": "judicial_financial_disclosure",
        "source_url": "https://pub.jefs.uscourts.gov/example",
        "retrieval_mode": "public_portal",
        "source_status": "identified",
        "auto_download_allowed": True,
    }

    output = archive_document(
        source,
        row,
        archive_root=tmp_path,
        fetcher=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert calls == []
    assert output["archive_status"] == "source_restriction_review_required"
    assert output["retrieval_attempted"] is False
    assert set(output["access_decision"]["restriction_reasons"]) == {
        "automated_retrieval_not_permitted",
        "terms_acknowledgement_required",
        "requester_identity_required",
    }


def test_source_policy_and_host_validation_are_machine_readable():
    senate = evaluate_source_access(
        "senate-public-financial-disclosure", automated=True, terms_acknowledged=False
    )
    assert senate["access_status"] == "restricted"
    assert senate["restriction_reasons"] == ["terms_acknowledgement_required"]
    assert source_restriction_metadata("house-financial-disclosure")["automated_retrieval_allowed"] is True
    with pytest.raises(ValueError, match="outside the configured"):
        validate_official_url("https://example.com/report.pdf", ["disclosures-clerk.house.gov"])


def test_content_addressed_archive_is_hash_verified_and_idempotent(tmp_path):
    content = b"%PDF-1.7 deterministic fixture"
    result = FetchResult(
        content=content,
        content_type="application/pdf; charset=binary",
        final_url="https://www.oge.gov/report.pdf",
        status_code=200,
        attempts=[{"attempt": 1, "status": "success", "status_code": 200}],
        response_metadata={"etag": '"fixture"', "last_modified": None, "content_length": str(len(content))},
    )
    source = {"id": "oge-individual-disclosures"}
    row = {
        "document_id": "oge-example",
        "document_type": "executive_financial_disclosure",
        "source_url": "https://www.oge.gov/report.pdf",
        "retrieval_mode": "direct_public_document",
        "source_status": "official",
        "auto_download_allowed": True,
        "expected_sha256": hashlib.sha256(content).hexdigest(),
    }
    fetcher = lambda *args, **kwargs: result

    first = archive_document(source, row, archive_root=tmp_path, fetcher=fetcher)
    second = archive_document(source, row, archive_root=tmp_path, fetcher=fetcher)

    assert first["archive_status"] == "archived"
    assert second["archive_status"] == "archived"
    assert first["archive_object_status"] == "new"
    assert second["archive_object_status"] == "reused"
    assert first["storage_path"] == second["storage_path"]
    assert first["content_hashes"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert first["content_hashes"]["sha512"] == hashlib.sha512(content).hexdigest()
    assert len(list(tmp_path.rglob("*.pdf"))) == 1


def test_transient_fetch_retry_history_is_preserved():
    class Response:
        status = 200
        headers = {"Content-Type": "application/pdf", "ETag": '"ok"'}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"%PDF-1.7 retry fixture"

        def geturl(self):
            return "https://www.oge.gov/report.pdf"

    attempts = []

    def opener(request, timeout):
        attempts.append((request.full_url, timeout))
        if len(attempts) == 1:
            raise HTTPError(request.full_url, 503, "Unavailable", {"Retry-After": "1"}, None)
        return Response()

    delays = []
    result = fetch_with_retry(
        "https://www.oge.gov/report.pdf",
        allowed_hosts=["www.oge.gov"],
        opener=opener,
        sleep=delays.append,
    )

    assert len(attempts) == 2
    assert delays == [1.0]
    assert result.attempts[0]["status_code"] == 503
    assert result.attempts[0]["retry_after"] == "1"
    assert result.attempts[1]["status"] == "success"


def test_expected_hash_mismatch_is_rejected_before_archive_write(tmp_path):
    result = FetchResult(
        content=b"%PDF-1.7 mismatched fixture",
        content_type="application/pdf",
        final_url="https://www.oge.gov/report.pdf",
        status_code=200,
        attempts=[{"attempt": 1, "status": "success", "status_code": 200}],
        response_metadata={},
    )
    row = {
        "document_id": "oge-mismatch",
        "document_type": "executive_financial_disclosure",
        "source_url": "https://www.oge.gov/report.pdf",
        "retrieval_mode": "direct_public_document",
        "source_status": "official",
        "auto_download_allowed": True,
        "expected_sha256": "0" * 64,
    }

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        archive_document(
            {"id": "oge-individual-disclosures"},
            row,
            archive_root=tmp_path,
            fetcher=lambda *args, **kwargs: result,
        )

    assert list(tmp_path.rglob("*")) == []


def test_oge_and_judiciary_layout_variants_preserve_source_metadata():
    oge = get_parser("oge-individual-disclosures").preview(
        (FIXTURES / "oge_278t_variant.tsv").read_bytes(),
        filename="oge.tsv",
        content_type="text/tab-separated-values",
    )
    judicial = get_parser("judicial-financial-disclosure").preview(
        (FIXTURES / "judicial_ao10t_variant.txt").read_bytes(),
        filename="ao10t.txt",
        content_type="text/plain",
    )

    assert oge.normalized_record_count == 1
    assert oge.transactions[0].transaction_type == "BUY"
    assert oge.output["metadata"]["agency"] == "Department of Example Affairs"
    assert oge.output["metadata"]["is_amendment"] is True
    assert oge.output["metadata"]["form_family"] == "OGE Form 278-T"
    assert oge.output["source_layout"]["delimiter"] == "\t"
    assert judicial.normalized_record_count == 1
    assert judicial.output["metadata"]["court"].startswith("U.S. Court of Appeals")
    assert judicial.output["metadata"]["report_year"] == "2025"
    assert judicial.output["metadata"]["form_family"] == "AO 10T"


def test_senate_alias_layout_is_parsed_without_losing_headers():
    report = parse_senate_report_html(
        (FIXTURES / "senate_ptr_variant.html").read_bytes(), source_url=SENATE_URL
    )

    assert report.transactions[0]["row_number"] == 7
    assert report.transactions[0]["action"] == "BUY"
    assert report.transactions[0]["owner"] == "Spouse"
    assert report.layout_metadata["table_headers"][1] == "Date of Transaction"


def test_unresolved_senate_identity_withholds_structured_rows():
    page = SenateReportPage(
        source_url=SENATE_URL,
        body=(FIXTURES / "senate_ptr_variant.html").read_bytes(),
        content_type="text/html",
        status_code=200,
        retrieved_at="2025-02-11T12:00:00+00:00",
    )
    document = {
        "document_id": "senate-ptr-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "senate_report_uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "source_id": "senate-public-financial-disclosure",
        "source_url": SENATE_URL,
        "source_tier": "official",
        "report_type": "periodic_transaction_report",
        "filing_year": 2025,
        "filing_date": "2025-02-11",
        "filer_name": "Avery Example",
        "report_format": "electronic_html",
        "is_amendment": True,
        "match_status": "ambiguous",
        "identity_resolution": "ambiguous_manual_review_required",
        "review_required_before_public_trade": True,
        "public_production_trade": False,
    }

    output = build_senate_ptr_transactions([document], {SENATE_URL: page}, acquisition_mode="fixture")

    assert output["transactions"] == []
    assert output["documents"][0]["parser_status"] == "identity_review_required"
    assert output["summary"]["withheld_invalid_structured_row_count"] == 1


def test_senate_page_identity_mismatch_cannot_create_transactions():
    page = SenateReportPage(
        source_url=SENATE_URL,
        body=(FIXTURES / "senate_ptr_variant.html").read_bytes(),
        content_type="text/html",
        status_code=200,
        retrieved_at="2025-02-11T12:00:00+00:00",
    )
    document = {
        "document_id": "senate-ptr-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "senate_report_uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "source_id": "senate-public-financial-disclosure",
        "source_url": SENATE_URL,
        "source_tier": "official",
        "report_type": "periodic_transaction_report",
        "filing_year": 2025,
        "filing_date": "2025-02-11",
        "filer_name": "Different Person",
        "report_format": "electronic_html",
        "is_amendment": False,
        "match_status": "matched",
        "identity_resolution": "deterministic_match",
        "official_id": "congress:D000001",
        "official_name": "Different Person",
        "review_required_before_public_trade": True,
        "public_production_trade": False,
    }

    output = build_senate_ptr_transactions([document], {SENATE_URL: page}, acquisition_mode="fixture")

    assert output["transactions"] == []
    assert output["documents"][0]["page_identity_consistent"] is False
    assert "portal_page_filer_identity_mismatch" in output["documents"][0]["data_quality_flags"]


def test_ambiguous_house_identity_returns_candidates_instead_of_guessing():
    row = {
        "First": "Alex",
        "Last": "Example",
        "StateDst": "CA07",
        "FilingDate": "02/14/2025",
    }
    role = {
        "full_name": "Alex Example",
        "service_start": "2024-01-01",
        "service_end": None,
        "source_metadata": {"state": "CA", "district": "7", "bioguide_id": "E000001"},
    }
    result = match_house_member(
        row,
        [
            {**role, "external_person_id": "congress:E000001"},
            {**role, "external_person_id": "congress:E000002"},
        ],
    )

    assert result["match_status"] == "ambiguous"
    assert result["identity_resolution"] == "ambiguous_manual_review_required"
    assert [candidate["official_id"] for candidate in result["identity_candidates"]] == [
        "congress:E000001",
        "congress:E000002",
    ]


def test_house_index_preserves_unknown_fields_and_hashes_deterministically():
    rows = parse_house_index((FIXTURES / "house_index_variant.tsv").read_bytes())
    assert rows[0]["UnexpectedField"] == "Preserved source value"
    assert source_row_sha256(rows[0]) == source_row_sha256(dict(reversed(list(rows[0].items()))))


def test_amendment_and_duplicate_helpers_are_deterministic_and_non_destructive():
    house = {
        "document_id": "house-a",
        "official_id": "congress:E000001",
        "report_type": "Periodic Transaction Report Amendment",
    }
    house_amendment = {**house, "document_id": "house-b", "amends_document_id": "house-a"}
    reconciled_house = reconcile_house_amendments([house, house_amendment])
    assert reconciled_house[1]["supersedes_document_id"] == "house-a"
    assert house_document_family_key(house_amendment) == house_document_family_key(house_amendment)

    senate_original = {
        "document_id": "senate-a",
        "senate_report_uuid": "a",
        "official_id": "congress:E000001",
        "portal_report_title": "Periodic Transaction Report for 02/11/2025",
        "filing_date": "2025-02-11",
        "is_amendment": False,
    }
    senate_amendment = {
        **senate_original,
        "document_id": "senate-b",
        "senate_report_uuid": "b",
        "portal_report_title": "Periodic Transaction Report for 02/11/2025 Amendment",
        "is_amendment": True,
    }
    reconciled_senate = reconcile_senate_amendments([senate_amendment, senate_original])
    assert senate_document_family_key(senate_original) == senate_document_family_key(senate_amendment)
    assert reconciled_senate[1]["candidate_supersedes_document_id"] == "senate-a"

    transaction = {
        "official_id": "congress:E000001",
        "trade_date": "2025-02-03",
        "action": "BUY",
        "owner": "Self",
        "asset_display_name": " Example  Fund ",
        "ticker": "EXM",
        "value_range_label": "$1,001 - $15,000",
    }
    assert senate_transaction_signature(transaction) == senate_transaction_signature(dict(transaction))
    parser_transaction = {
        "owner": "Self",
        "asset": "Example Fund",
        "ticker": "EXM",
        "transaction_type": "BUY",
        "transaction_date": "2025-02-03",
        "amount": "$1,001 - $15,000",
    }
    assert deterministic_transaction_signature(parser_transaction) == deterministic_transaction_signature(
        dict(parser_transaction)
    )
