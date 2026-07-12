import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "build_presidential_oge_documents.py"
SPEC = importlib.util.spec_from_file_location("presidential_oge_builder", MODULE_PATH)
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def curated_document(document_id):
    return next(row for row in BUILDER.CURATED_DOCUMENTS if row["document_id"] == document_id)


def test_annual_parser_accepts_text_dates_and_preserves_trust_authority_note():
    document = curated_document("oge-trump-2020-annual-278")
    pages = [
        {
            "page": 28,
            "text": "\n".join(
                [
                    "Part 7: Transactions",
                    "10 JPMORGAN BETABUILDERS CANADA ETF Purchase 08-Apr -2019 $1 ,001 - $15 ,000",
                    "J.P. Morgan is the sole Trustee. Donald J. Trump retains an income interest only in the Family Trusts and has no investment decision authority.",
                ]
            ),
        }
    ]

    rows = BUILDER.parse_transaction_lines(document, pages)

    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2019-04-08"
    assert rows[0]["action"] == "BUY"
    assert rows[0]["decision_authority_status"] == "report_states_no_investment_decision_authority"
    assert "no investment decision authority" in rows[0]["decision_authority_note"]


def test_annual_parser_repairs_split_numeric_year_ocr():
    document = curated_document("oge-biden-2022-annual-278")
    pages = [
        {
            "page": 9,
            "text": "\n".join(
                [
                    "Part 7: Transactions",
                    "2. Guggenheim VIF SMid Cap Value sale 05/24/202 1 $1 ,001 - $15,000",
                ]
            ),
        }
    ]

    rows = BUILDER.parse_transaction_lines(document, pages)

    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2021-05-24"
    assert rows[0]["source_sequence"] == 2


def test_source_reviewed_none_is_distinct_from_unparsed_document():
    document = curated_document("oge-biden-2023-annual-278")

    assert (
        BUILDER.transaction_section_status(document, [{"page": 9, "text": ""}], [])
        == "no_reportable_transactions"
    )


def test_obama_archive_transcriptions_remain_review_gated():
    document = curated_document("oge-obama-2014-annual-278")
    rows = BUILDER.manual_transaction_rows(document)

    assert len(rows) == 8
    assert {row["trade_date"] for row in rows} == {"2014-11-18", "2014-12-15"}
    assert all(row["review_required_before_public_trade"] is True for row in rows)
    assert all(row["public_production_trade"] is False for row in rows)
    assert all(row["normalization_method"] == "manual_source_page_transcription" for row in rows)
