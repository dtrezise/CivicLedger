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


def test_annual_parser_preserves_investment_account_context():
    document = curated_document("oge-trump-2026-annual-278")
    pages = [
        {
            "page": 159,
            "text": "\n".join(
                [
                    "Part 7: Transactions",
                    "1 APPLE INC purchase 9/18/2025 $1,000,001 - $5,000,000",
                    "INVESTMENT ACCOUNT #1",
                ]
            ),
        }
    ]

    rows = BUILDER.parse_transaction_lines(document, pages)

    assert len(rows) == 1
    assert rows[0]["source_account_label"] == "Investment account #1"


def test_cross_filing_reconciliation_suppresses_only_strict_periodic_matches():
    periodic = {
        "id": "periodic-1",
        "official_id": "exec:donald-j-trump",
        "filing_type": "periodic_transaction_278t",
        "trade_date": "2025-08-28",
        "action": "BUY",
        "asset_display_name": "Broadcom Inc. 4.75% due 04/15/29",
        "value_range_min": 1_000_001,
        "value_range_max": 5_000_000,
    }
    annual_match = {
        **periodic,
        "id": "annual-match",
        "filing_type": "annual_278e",
        "asset_display_name": "BROADCOM INC 4.75 DUE 04 15 29",
    }
    annual_distinct = {
        **annual_match,
        "id": "annual-distinct",
        "asset_display_name": "Meta Platforms 4.75% due 08/15/34",
    }

    summary = BUILDER.reconcile_cross_filing_duplicates(
        [periodic, annual_match, annual_distinct]
    )

    assert summary["cross_filing_duplicate_count"] == 1
    assert annual_match["timeline_inclusion"] is False
    assert annual_match["duplicate_of_transaction_id"] == "periodic-1"
    assert annual_distinct["timeline_inclusion"] is True


def test_ticker_inference_does_not_treat_company_suffix_words_as_symbols():
    assert BUILDER.ticker_for("THE GOLDMAN SACHS GROUP INC", "equity") == "GS"
    assert BUILDER.ticker_for("VISA INC", "equity") == "V"
    assert BUILDER.ticker_for("JOHNSON & JOHNSON", "equity") == "JNJ"
    assert BUILDER.ticker_for("GENERAL MILLS INC", "equity") is None
    assert BUILDER.ticker_for("NORTHERN TRUST CORP", "equity") is None


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


def test_obama_termination_report_closes_archive_gap_with_reviewed_none_finding():
    document = curated_document("oge-obama-2017-termination-278")

    assert document["coverage_start"] == "2016-01-01"
    assert document["coverage_end"] == "2017-01-20"
    assert document["source_reviewed_without_live_pdf"] is True
    assert document["source_transaction_section_status"] == (
        "source_reviewed_no_reportable_transactions"
    )
    assert BUILDER.UNAVAILABLE_DOCUMENTS == []
