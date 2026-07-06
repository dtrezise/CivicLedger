from pathlib import Path

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
    assert preview.warnings[0].startswith("Parser preview only")


def test_supported_source_ids_cover_all_branches():
    assert get_supported_source_ids() == [
        "house-financial-disclosure",
        "judicial-financial-disclosure",
        "oge-individual-disclosures",
        "senate-public-financial-disclosure",
    ]
