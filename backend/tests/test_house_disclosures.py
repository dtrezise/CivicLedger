from datetime import date

from app.services.house_disclosures import (
    HOUSE_PTR_DOCUMENT_URL,
    document_url,
    normalize_district,
    parse_house_index,
    split_state_district,
)


def test_house_index_parser_and_ptr_url():
    content = (
        "Prefix\tLast\tFirst\tSuffix\tFilingType\tStateDst\tYear\tFilingDate\tDocID\r\n"
        "Hon.\tAderholt\tRobert B.\t\tP\tAL04\t2025\t9/10/2025\t20032062\r\n"
    ).encode()
    rows = parse_house_index(content)

    assert len(rows) == 1
    assert rows[0]["Last"] == "Aderholt"
    assert document_url(rows[0]) == HOUSE_PTR_DOCUMENT_URL.format(year="2025", document_id="20032062")


def test_house_state_and_district_normalization():
    assert split_state_district("AL04") == ("AL", "4")
    assert split_state_district("VT00") == ("VT", "0")
    assert normalize_district("At Large") == "0"
    assert normalize_district(7) == "7"
