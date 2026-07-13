import hashlib
from datetime import date

from app.services.house_disclosures import HouseIndexFetch
from app.services.house_historical_disclosures import build_house_historical_transaction_index


def _row(**overrides):
    row = {
        "Prefix": "HONORABLE",
        "Last": "Example",
        "First": "Alex",
        "Suffix": "",
        "FilingType": "O",
        "StateDst": "VA01",
        "Year": "2012",
        "Filing Year": "2012",
        "FilingDate": "05/15/2012",
        "DocID": "2000001",
        "DisclosureType": "PTR",
    }
    row.update(overrides)
    return row


def test_historical_index_recognizes_legacy_ptr_encoding_and_declares_gaps():
    rows_by_year = {
        2009: [
            _row(
                Year="2009",
                **{"Filing Year": "2008", "DisclosureType": "FD", "DocID": "1000001"},
            )
        ],
        2010: [],
        2011: [],
        2012: [_row()],
        2013: [
            _row(
                Prefix="",
                First="Taylor",
                Last="Staffer",
                Year="2013",
                **{"Filing Year": "2013", "DocID": "2000002"},
            )
        ],
        2014: [],
    }

    def index_fetcher(year):
        content = f"fixture-{year}".encode()
        return HouseIndexFetch(
            year=year,
            source_url=f"https://disclosures-clerk.house.gov/{year}FD.txt",
            sha256=hashlib.sha256(content).hexdigest(),
            byte_count=len(content),
            rows=rows_by_year[year],
        )

    dataset = build_house_historical_transaction_index(
        as_of=date(2026, 7, 12),
        index_fetcher=index_fetcher,
        binary_fetcher=lambda url: url.encode(),
    )

    assert dataset["generated_at"] == "2026-07-12"
    assert dataset["summary"]["indexed_ptr_document_count"] == 2
    assert dataset["summary"]["indexed_member_ptr_document_count"] == 1
    assert dataset["summary"]["indexed_member_financial_report_count"] == 1
    ptr = next(row for row in dataset["documents"] if row["document_id"] == "2000001")
    assert ptr["report_type"] == "periodic_transaction_report"
    assert ptr["source_url"].endswith("/ptr-pdfs/2012/2000001.pdf")
    gaps = dataset["coverage"]["declared_gaps"]
    assert gaps[0]["status"] == "separate_ptr_reporting_not_applicable_pre_stock_act"
    assert gaps[-1]["status"] == "official_bulk_index_known_incomplete"
    assert all(
        evidence["bulk_index_membership"] is False
        for evidence in gaps[-1]["evidence_documents"]
    )
    assert dataset["summary"]["transaction_row_count"] == 0


def test_historical_index_rejects_years_outside_bounded_scope():
    try:
        build_house_historical_transaction_index(2008, 2014)
    except ValueError as error:
        assert "2009 through 2014" in str(error)
    else:
        raise AssertionError("Expected a bounded historical-year validation error")
