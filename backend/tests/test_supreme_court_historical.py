import io
import json
import zipfile
from datetime import date

from app.services.supreme_court_historical import (
    build_supreme_court_historical_decisions,
    build_volume_records,
    historical_decisions_for_range,
    parse_case_header,
)


MODS = b"""<?xml version="1.0" encoding="UTF-8"?>
<mods xmlns="http://www.loc.gov/mods/v3">
  <extension><courtTerm>2016</courtTerm></extension>
  <relatedItem type="constituent" ID="id-USREPORTS-580-5">
    <titleInfo><title>Example Corp. v. United States, 580 U.S. 5 (2016)</title></titleInfo>
    <extension>
      <granuleClass>CASE</granuleClass><accessId>USREPORTS-580-5</accessId>
      <reportNumber>5</reportNumber><decisionDate>2016-11-29</decisionDate>
      <courtTerm>2016</courtTerm><usCitation>580 U.S. 5</usCitation>
      <fullCitation>580 U.S. 5 (2016)</fullCitation>
      <subject><topic>Securities</topic><topic>Financial Markets</topic></subject>
    </extension>
  </relatedItem>
</mods>
"""


def _package() -> bytes:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("USREPORTS-580/mods.xml", MODS)
        archive.writestr("USREPORTS-580/pdf/USREPORTS-580-5.pdf", b"official-pdf-fixture")
    return content.getvalue()


def test_case_header_parser_preserves_consolidated_docket_and_decision_date():
    docket, decision_date = parse_case_header(
        "Syllabus Nos. 15-1500 and 16-120. Argued October 4, 2016-Decided November 29, 2016"
    )

    assert docket == "15-1500 and 16-120"
    assert decision_date == "2016-11-29"


def test_case_header_parser_handles_letter_spaced_bound_volume_text():
    docket, decision_date = parse_case_header(
        "N o. 1 1 - 1 1 8 4. D e ci d e d S e pt e m b e r 2 5, 2 0 1 2"
    )

    assert docket == "11-1184"
    assert decision_date == "2012-09-25"


def test_volume_builder_preserves_citation_date_docket_urls_and_provenance():
    snapshot, records = build_volume_records(
        580,
        _package(),
        pdf_text_extractor=lambda content: (
            "EXAMPLE CORP. v. UNITED STATES No. 15-537. "
            "Argued October 4, 2016-Decided November 29, 2016"
        ),
    )

    assert snapshot["case_count"] == 1
    assert len(snapshot["package_sha256"]) == 64
    assert records[0]["case_name"] == "Example Corp. v. United States"
    assert records[0]["citation"] == "580 U.S. 5"
    assert records[0]["docket_number"] == "15-537"
    assert records[0]["decision_date"] == "2016-11-29"
    assert records[0]["source_url"].endswith("/USREPORTS-580-5.pdf")
    assert records[0]["provenance"]["source_tier"] == "official"


def test_dataset_filters_by_calendar_date_and_reports_no_fixture_gaps():
    dataset = build_supreme_court_historical_decisions(
        "2016-01-01",
        "2016-12-31",
        as_of=date(2026, 7, 12),
        volumes=(580,),
        binary_fetcher=lambda url: _package(),
        pdf_text_extractor=lambda content: (
            "No. 15-537. Argued October 4, 2016-Decided November 29, 2016"
        ),
    )

    assert dataset["generated_at"] == "2026-07-12"
    assert dataset["summary"]["decision_count"] == 1
    assert dataset["summary"]["docket_number_missing_count"] == 0
    assert dataset["summary"]["decisions_by_calendar_year"] == {"2016": 1}


def test_historical_artifact_loader_maps_official_provenance_for_federal_events(tmp_path):
    dataset = build_supreme_court_historical_decisions(
        "2016-01-01",
        "2016-12-31",
        as_of=date(2026, 7, 12),
        volumes=(580,),
        binary_fetcher=lambda url: _package(),
        pdf_text_extractor=lambda content: (
            "No. 15-537. Argued October 4, 2016-Decided November 29, 2016"
        ),
    )
    path = tmp_path / "historical.json"
    path.write_text(json.dumps(dataset))

    rows, snapshot = historical_decisions_for_range(path, "2016-01-01", "2016-12-31")

    assert rows[0]["docket_number"] == "15-537"
    assert rows[0]["citation"] == "580 U.S. 5"
    assert rows[0]["historical_provenance"]["collection"] == "United States Reports"
    assert snapshot["decision_count"] == 1
    assert snapshot["path"] == "historical.json"
    assert len(snapshot["source_artifact_sha256"]) == 64
