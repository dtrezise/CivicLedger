import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.build_house_ptr_transactions import asset_class, build_output, canonical_amount, value_range  # noqa: E402


def test_house_amount_ranges_are_normalized():
    assert canonical_amount("$1,001   -   $15,000") == "$1,001 - $15,000"
    assert value_range("$1,001 - $15,000") == (1001, 15000, "$1,001 - $15,000")
    assert value_range("Over $50,000,000") == (50000001, None, "Over $50,000,000")


def test_house_asset_class_uses_form_code_before_guessing():
    assert asset_class("Apple Inc. (AAPL) [ST]", "AAPL") == "equity"
    assert asset_class("Example S&P 500 ETF [EF]", None) == "etf"
    assert asset_class("U.S. Treasury Note [GS]", None) == "fixed_income"


def test_duplicate_flags_are_rebuilt_without_accumulating_stale_flags():
    transactions = [
        {
            "id": f"trade-{index}",
            "official_id": "congress:A000001",
            "trade_date": "2025-01-02",
            "action": "BUY",
            "owner": "Self",
            "asset_display_name": "Example Corp. [ST]",
            "value_range_label": "$1,001 - $15,000",
            "asset_class": "equity",
            "data_quality_flags": ["possible_duplicate"],
            "duplicate_candidate": True,
            "duplicate_candidate_group_id": "stale-group",
        }
        for index in range(2)
    ]

    first = build_output([], transactions)
    second = build_output([], first["transactions"])

    assert first["summary"]["duplicate_candidate_group_count"] == 1
    assert second["summary"]["duplicate_candidate_group_count"] == 1
    assert all(row["data_quality_flags"].count("possible_duplicate") == 1 for row in second["transactions"])
    assert all(row["duplicate_candidate_group_id"] != "stale-group" for row in second["transactions"])
