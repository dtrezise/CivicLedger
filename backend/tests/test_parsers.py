from pathlib import Path
import json

import pytest

from app.parsers import get_parser, get_supported_source_ids


FIXTURES = Path(__file__).parent / "fixtures" / "parsers"


@pytest.mark.parametrize(
    ("source_id", "fixture_name", "expected_action", "expected_branch"),
    [
        ("house-financial-disclosure", "house_ptr.csv", "BUY", "Legislative"),
        ("senate-public-financial-disclosure", "senate_ptr.txt", "SELL", "Legislative"),
        ("oge-individual-disclosures", "oge_278t.csv", "BUY", "Executive"),
        ("judicial-financial-disclosure", "judicial_ao10t.txt", "EXCHANGE", "Judicial"),
    ],
)
def test_source_specific_parser_extracts_transaction(
    source_id, fixture_name, expected_action, expected_branch
):
    parser = get_parser(source_id)
    fixture = FIXTURES / fixture_name

    preview = parser.preview(
        fixture.read_bytes(),
        filename=fixture.name,
        content_type="text/csv" if fixture.suffix == ".csv" else "text/plain",
    )

    assert preview.source_id == source_id
    assert preview.output["branch"] == expected_branch
    assert preview.normalized_record_count == 1
    assert preview.transactions[0].transaction_type == expected_action
    assert preview.transactions[0].asset.startswith("Example")
    assert preview.transactions[0].amount
    assert preview.transactions[0].confidence >= 0.8
    assert preview.transactions[0].field_confidence["asset"] >= 0.9
    assert preview.output["record_status"] == "parser_preview"
    assert preview.output["review_required_before_promotion"] is True
    assert preview.warnings[0].startswith("Parser preview only")


def test_supported_source_ids_cover_all_branches():
    assert get_supported_source_ids() == [
        "house-financial-disclosure",
        "judicial-financial-disclosure",
        "oge-individual-disclosures",
        "senate-public-financial-disclosure",
    ]


def test_real_oge_public_sample_fixture_is_hash_backed_parser_preview():
    fixture = json.loads((FIXTURES / "oge_public_sample_fixture.json").read_text())

    assert fixture["schema_version"] == "oge-public-sample-parser-fixture-v1"
    assert fixture["source_id"] == "oge-individual-disclosures"
    assert fixture["file_hash"]
    assert fixture["byte_count"] > 1000
    assert fixture["review_status"] == "parser_fixture_not_public_production"
    assert "review" in " ".join(fixture["warnings"]).lower()
