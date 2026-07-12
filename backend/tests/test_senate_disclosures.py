import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from app.services.senate_disclosures import (
    SENATE_REPORT_DATA_URL,
    SenateDisclosurePortalClient,
    SenateReportPage,
    SenateSearchAcquisition,
    SenateTermsAcknowledgementRequired,
    build_senate_ptr_index,
    build_senate_ptr_transactions,
    load_report_page_import_manifest,
    load_search_import_manifest,
    parse_report_index_row,
    parse_senate_report_html,
    senate_roles,
    senate_roster_coverage,
)


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
FEINSTEIN_URL = (
    "https://efdsearch.senate.gov/search/view/paper/"
    "37bcc48e-e4b7-42b4-b33c-e4b8e126fb7a/"
)
FEINSTEIN_ROW = [
    "DIANNE ",
    "FEINSTEIN",
    "Former Senator",
    (
        '<a href="/search/view/paper/37bcc48e-e4b7-42b4-b33c-e4b8e126fb7a/" '
        'target="_blank">Periodic Transaction Report for 01/12/2021</a>'
    ),
    "01/12/2021",
]
PAPER_HTML = b"""
<html><head><title>eFD: View Report</title></head><body>
  <h1>Periodic Transaction Report for 01/12/2021</h1>
  <h2 class="filedReport">The Honorable Dianne Feinstein</h2>
  <p class="muted"><strong>Filed 01/12/2021 @ 10:00 AM</strong></p>
  <img class="filingImage"
       src="https://efd-media-public.senate.gov/media/2021/2/000/000/000000036.gif" />
  <img class="filingImage"
       src="https://efd-media-public.senate.gov/media/2021/2/000/000/000000037.gif" />
</body></html>
"""
STRUCTURED_URL = (
    "https://efdsearch.senate.gov/search/view/ptr/"
    "59c6f909-ad10-429d-8a8c-df81b00cf5fd/"
)
STRUCTURED_HTML = b"""
<html><head><title>eFD: View Report</title></head><body>
  <h1>Periodic Transaction Report for 06/07/2026</h1>
  <h2 class="filedReport">The Honorable James Banks (Banks, James E.)</h2>
  <p class="muted"><strong>Filed 06/07/2026 @ 10:22 AM</strong></p>
  <table>
    <thead><tr>
      <th>#</th><th>Transaction Date</th><th>Owner</th><th>Ticker</th>
      <th>Asset Name</th><th>Asset Type</th><th>Type</th><th>Amount</th><th>Comment</th>
    </tr></thead>
    <tbody><tr>
      <td>1</td><td>06/05/2026</td><td>Self</td><td><a>PTON</a></td>
      <td>Peloton Interactive, Inc. - Common Stock</td><td>Stock</td>
      <td>Sale (Full)</td><td>$1,001 - $15,000</td><td>--</td>
    </tr></tbody>
  </table>
</body></html>
"""


@pytest.fixture(scope="module")
def public_officials():
    return json.loads(PUBLIC_OFFICIALS.read_text())


def test_live_portal_requires_explicit_terms_acknowledgement():
    client = SenateDisclosurePortalClient(terms_acknowledged=False)

    with pytest.raises(SenateTermsAcknowledgementRequired, match="acknowledge-senate-terms"):
        client.ensure_access()


def test_roster_design_covers_111th_through_119th_congress(public_officials):
    roles = senate_roles(public_officials)
    coverage = senate_roster_coverage(roles)
    feinstein_congresses = {
        role["source_metadata"]["congress_number"]
        for role in roles
        if role["source_metadata"]["bioguide_id"] == "F000062"
    }

    assert coverage["congresses"] == list(range(111, 120))
    assert coverage["senator_official_count"] >= 200
    assert all(coverage["official_counts_by_congress"][str(congress)] >= 100 for congress in range(111, 120))
    assert feinstein_congresses == set(range(111, 119))


def test_official_index_row_is_parsed_and_matched_to_feinstein(public_officials):
    parsed = parse_report_index_row(FEINSTEIN_ROW)
    acquisition = SenateSearchAcquisition(
        rows=[FEINSTEIN_ROW],
        response_records=[
            {
                "source_url": SENATE_REPORT_DATA_URL,
                "response_sha256": "a" * 64,
                "byte_count": 100,
                "row_count": 1,
                "records_total": 1,
                "records_filtered": 1,
                "response_body": "{}",
            }
        ],
        retrieved_at="2026-07-12T20:00:00+00:00",
    )
    dataset = build_senate_ptr_index(
        public_officials,
        acquisition,
        start_date=date(2012, 1, 1),
        end_date=date(2026, 7, 12),
        coverage_mode="selected_senator_validation",
        selected_bioguide_ids={"F000062"},
        request_interval_seconds=1.0,
    )

    assert parsed["senate_report_uuid"] == "37bcc48e-e4b7-42b4-b33c-e4b8e126fb7a"
    assert parsed["report_format"] == "paper_images"
    assert dataset["documents"][0]["official_id"] == "congress:F000062"
    assert dataset["documents"][0]["match_status"] == "matched"
    assert dataset["documents"][0]["review_required_before_public_trade"] is True
    assert dataset["validation"]["document_count"] == 1
    assert dataset["summary"]["public_production_trade_count"] == 0


def test_structured_electronic_ptr_html_is_parsed_from_semantic_table():
    report = parse_senate_report_html(STRUCTURED_HTML, source_url=STRUCTURED_URL)

    assert report.filing_date == "2026-06-07"
    assert report.filer_name.startswith("The Honorable James Banks")
    assert report.media_urls == []
    assert report.rejected_rows == []
    assert report.transactions == [
        {
            "row_number": 1,
            "transaction_date": "2026-06-05",
            "owner": "Self",
            "ticker": "PTON",
            "asset_name": "Peloton Interactive, Inc. - Common Stock",
            "asset_type": "Stock",
            "transaction_type_raw": "Sale (Full)",
            "action": "SELL",
            "amount": "$1,001 - $15,000",
            "comment": None,
        }
    ]


def test_paper_report_is_manifested_without_fabricating_transactions(public_officials):
    acquisition = SenateSearchAcquisition(
        rows=[FEINSTEIN_ROW], response_records=[], retrieved_at="2026-07-12T20:00:00+00:00"
    )
    index = build_senate_ptr_index(
        public_officials,
        acquisition,
        start_date=date(2012, 1, 1),
        end_date=date(2026, 7, 12),
        coverage_mode="selected_senator_validation",
        selected_bioguide_ids={"F000062"},
    )
    page = SenateReportPage(
        source_url=FEINSTEIN_URL,
        body=PAPER_HTML,
        content_type="text/html; charset=utf-8",
        status_code=200,
        retrieved_at="2026-07-12T20:01:00+00:00",
    )
    output = build_senate_ptr_transactions(
        index["documents"],
        {FEINSTEIN_URL: page},
        acquisition_mode="live_portal",
        request_interval_seconds=1.0,
    )

    assert output["transactions"] == []
    assert output["documents"][0]["parser_status"] == "paper_images_review_required"
    assert output["documents"][0]["source_media_page_count"] == 2
    assert output["summary"]["paper_image_review_document_count"] == 1
    assert output["summary"]["processed_official_count"] == 1
    assert output["summary"]["transaction_official_count"] == 0
    assert output["summary"]["public_production_trade_count"] == 0
    assert "OCR and human review" in output["documents"][0]["parser_warnings"][0]


def test_transaction_builder_keeps_structured_rows_review_gated():
    document = {
        "document_id": "senate-ptr-59c6f909-ad10-429d-8a8c-df81b00cf5fd",
        "senate_report_uuid": "59c6f909-ad10-429d-8a8c-df81b00cf5fd",
        "source_id": "senate-public-financial-disclosure",
        "source_url": STRUCTURED_URL,
        "source_tier": "official",
        "report_type": "periodic_transaction_report",
        "portal_report_title": "Periodic Transaction Report for 06/07/2026",
        "filing_year": 2026,
        "filing_date": "2026-06-07",
        "filer_name": "James Banks",
        "report_format": "electronic_html",
        "is_amendment": False,
        "official_id": "congress:B001316",
        "official_name": "James E. Banks",
        "bioguide_id": "B001316",
        "match_status": "matched",
        "review_required_before_public_trade": True,
        "public_production_trade": False,
    }
    page = SenateReportPage(
        source_url=STRUCTURED_URL,
        body=STRUCTURED_HTML,
        content_type="text/html; charset=utf-8",
        status_code=200,
        retrieved_at="2026-07-12T20:01:00+00:00",
    )
    output = build_senate_ptr_transactions(
        [document], {STRUCTURED_URL: page}, acquisition_mode="live_portal"
    )
    transaction = output["transactions"][0]

    assert transaction["action"] == "SELL"
    assert transaction["asset_class"] == "equity"
    assert transaction["value_range_min"] == 1001
    assert transaction["review_required_before_public_trade"] is True
    assert transaction["public_production_trade"] is False
    assert output["summary"]["review_required_transaction_count"] == 1
    assert output["summary"]["public_production_trade_count"] == 0

    repeated_row_number_html = STRUCTURED_HTML.replace(
        b"</tbody>",
        b"""
        <tr><td>1</td><td>06/04/2026</td><td>Self</td><td><a>AAPL</a></td>
        <td>Apple Inc. - Common Stock</td><td>Stock</td><td>Purchase</td>
        <td>$1,001 - $15,000</td><td>--</td></tr></tbody>
        """,
    )
    repeated_output = build_senate_ptr_transactions(
        [document],
        {
            STRUCTURED_URL: SenateReportPage(
                source_url=STRUCTURED_URL,
                body=repeated_row_number_html,
                content_type="text/html; charset=utf-8",
                status_code=200,
                retrieved_at="2026-07-12T20:01:00+00:00",
            )
        },
        acquisition_mode="live_portal",
    )
    repeated_ids = [row["id"] for row in repeated_output["transactions"]]
    assert len(repeated_ids) == 2
    assert len(set(repeated_ids)) == 2


def test_hash_verified_import_manifest_supports_search_and_report_pages():
    response_body = json.dumps(
        {"draw": 1, "recordsTotal": 1, "recordsFiltered": 1, "data": [FEINSTEIN_ROW], "result": "ok"},
        separators=(",", ":"),
    )
    response_sha256 = hashlib.sha256(response_body.encode()).hexdigest()
    report_body = PAPER_HTML.decode()
    report_sha256 = hashlib.sha256(report_body.encode()).hexdigest()
    manifest = {
        "schema_version": "senate-disclosure-import-v1",
        "source_id": "senate-public-financial-disclosure",
        "source_url": "https://efdsearch.senate.gov/search/",
        "portal_terms_acknowledged": True,
        "terms_url": "https://efdsearch.senate.gov/search/home/",
        "retrieved_at": "2026-07-12T20:00:00+00:00",
        "search_responses": [
            {
                "source_url": SENATE_REPORT_DATA_URL,
                "request": {"start": 0, "length": 100},
                "response_sha256": response_sha256,
                "response_body": response_body,
            }
        ],
        "report_pages": [
            {
                "source_url": FEINSTEIN_URL,
                "response_sha256": report_sha256,
                "response_body": report_body,
            }
        ],
    }
    encoded = json.dumps(manifest, sort_keys=True).encode()

    search = load_search_import_manifest(encoded)
    pages, page_manifest_sha256 = load_report_page_import_manifest(encoded)

    assert search.rows == [FEINSTEIN_ROW]
    assert search.acquisition_mode == "import_manifest"
    assert search.import_manifest_sha256 == hashlib.sha256(encoded).hexdigest()
    assert pages[FEINSTEIN_URL].sha256 == report_sha256
    assert page_manifest_sha256 == hashlib.sha256(encoded).hexdigest()

    manifest["search_responses"][0]["response_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_search_import_manifest(json.dumps(manifest, sort_keys=True).encode())
