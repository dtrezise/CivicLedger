import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.asset_resolution import (  # noqa: E402
    asset_resolution_record,
    is_target_asset,
    resolve_asset_name,
)
from app.services.market_reactions import (  # noqa: E402
    MARKET_CONTEXT_LABEL,
    MarketReactionCalculator,
    build_price_index,
)
from scripts.build_asset_resolution_dataset import build_dataset as build_asset_dataset  # noqa: E402
from scripts.build_trade_market_reactions import build_dataset as build_reaction_dataset  # noqa: E402


def _series(symbol, values):
    dates = [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
        "2024-01-09",
        "2024-01-10",
    ]
    return {
        "symbol": symbol,
        "source": "fixture",
        "points": [
            {
                "symbol": symbol,
                "date": point_date,
                "adj_close": value,
                "close": value * 10,
            }
            for point_date, value in zip(dates, values)
        ],
    }


def _market_prices():
    return {
        "generated_at": "2024-01-11",
        "source": {"id": "fixture"},
        "ticker_reference": {
            "VFIAX": {
                "issuer_name": "Vanguard 500 Index Fund Admiral Shares",
                "asset_class": "mutual_fund",
                "sector": "Broad Market",
                "benchmark_symbol": "SPY",
            }
        },
        "series": {
            "VFIAX": _series("VFIAX", [100, 101, 99, 102, 103, 106, 104]),
            "SPY": _series("SPY", [200, 202, 200, 204, 206, 208, 210]),
        },
    }


def test_curated_529_resolution_preserves_underlying_identifier_and_benchmark():
    resolution = resolve_asset_name(
        "Bright Directions College Savings 529 Plan (DC) "
        "(PIMCO Total Return 529 Portfolio PTTRX)",
        asset_class="equity",
    )

    assert resolution["identifier"] == "PTTRX"
    assert resolution["identifier_type"] == "underlying_fund_symbol"
    assert resolution["fund_family"] == "PIMCO"
    assert resolution["asset_class"] == "529_portfolio"
    assert resolution["sector"] == "Fixed Income"
    assert resolution["benchmark_symbol"] == "BND"


def test_etf_resolution_handles_disclosure_suffixes_and_rejects_unsafe_guesses():
    resolution = resolve_asset_name(
        "iShares Core MSCI EAFE ETF (IEFA) [ST] FILING STATUS: New SUBHOLDING OF: Trust",
        asset_class="etf",
    )
    beta_builders = resolve_asset_name(
        "JPMORGAN BETABUILDERS CANADA ETF",
        disclosed_ticker="JPM",
        asset_class="etf",
    )

    assert resolution["identifier"] == "IEFA"
    assert resolution["match_method"] == "curated_explicit_symbol"
    assert beta_builders["identifier"] == "BBCA"
    assert resolve_asset_name("Vanguard retirement mutual fund", asset_class="mutual_fund") is None
    assert resolve_asset_name("CALL SPDR S&P 500 ETF [OT]", asset_class="etf") is None
    assert not is_target_asset("Royce Value Trust account X529", "equity")


def test_unresolved_record_is_explicit_and_does_not_reuse_disclosed_ticker():
    resolution = asset_resolution_record(
        "Unmapped Example Income Fund",
        disclosed_ticker="JPM",
        asset_class="fund",
    )

    assert resolution["resolution_status"] == "unresolved"
    assert resolution["identifier"] is None
    assert resolution["benchmark_symbol"] is None


def test_market_reaction_uses_common_sessions_and_adjusted_close():
    market_prices = _market_prices()
    index = build_price_index(market_prices)
    reaction = MarketReactionCalculator(market_prices).compute(
        "VFIAX",
        "SPY",
        "2024-01-06",
        (1, 2),
    )

    assert index["VFIAX"][0]["value"] == 100
    assert index["VFIAX"][0]["price_field"] == "adj_close"
    assert reaction["status"] == "covered"
    assert reaction["anchor_date"] == "2024-01-08"
    assert [row["session_count"] for row in reaction["pre_windows"]] == [1, 2]
    assert [row["session_count"] for row in reaction["post_windows"]] == [1, 2]
    assert reaction["pre_windows"][1]["asset_return_pct"] == 4.040404
    assert reaction["pre_windows"][1]["benchmark_return_pct"] == 3.0
    assert reaction["pre_windows"][1]["benchmark_adjusted_return_pct"] == 1.040404
    assert reaction["post_windows"][0]["benchmark_adjusted_return_pct"] == 1.941747
    assert reaction["context_label"] == MARKET_CONTEXT_LABEL


def test_asset_builder_keeps_resolved_and_unresolved_target_rows_separate():
    dataset = build_asset_dataset(
        [
            {
                "id": "tx-529",
                "source_dataset": "fixture_transactions",
                "asset_display_name": "PIMCO Total Return 529 Portfolio PTTRX",
                "asset_class": "fund",
                "ticker": None,
            },
            {
                "id": "tx-unknown",
                "source_dataset": "fixture_transactions",
                "asset_display_name": "Unmapped Example Income Fund",
                "asset_class": "mutual_fund",
                "ticker": None,
            },
            {
                "id": "tx-equity",
                "source_dataset": "fixture_transactions",
                "asset_display_name": "Apple Inc.",
                "asset_class": "equity",
                "ticker": "AAPL",
            },
        ],
        generated_at="2024-01-11",
    )

    assert dataset["summary"]["target_transaction_count"] == 2
    assert dataset["summary"]["resolved_transaction_count"] == 1
    assert dataset["summary"]["unresolved_transaction_count"] == 1
    assert dataset["summary"]["unique_asset_name_count"] == 2
    assert dataset["methodology"]["fuzzy_matching"] is False
    assert {row["transaction_id"] for row in dataset["transaction_resolutions"]} == {
        "tx-529",
        "tx-unknown",
    }


def test_reaction_builder_reports_coverage_without_action_direction_inference():
    dataset = build_reaction_dataset(
        [
            {
                "id": "tx-covered",
                "source_dataset": "fixture_transactions",
                "document_id": "doc-1",
                "official_id": "official-1",
                "trade_date": "2024-01-04",
                "action": "SELL",
                "asset_display_name": "Vanguard 500 Index Fund (Retirement)",
                "asset_class": "fund",
                "ticker": None,
                "record_status": "parser_preview",
                "review_required_before_public_trade": True,
            },
            {
                "id": "tx-no-series",
                "source_dataset": "fixture_transactions",
                "trade_date": "2024-01-04",
                "action": "BUY",
                "asset_display_name": "PIMCO Total Return 529 Portfolio PTTRX",
                "asset_class": "fund",
                "ticker": None,
            },
        ],
        _market_prices(),
        window_sessions=(1, 2),
        generated_at="2024-01-11",
    )

    assert dataset["summary"]["market_context_row_count"] == 1
    assert dataset["summary"]["skip_counts_by_reason"] == {"missing_asset_series": 1}
    row = dataset["reactions"][0]
    assert row["transaction_id"] == "tx-covered"
    assert row["action"] == "SELL"
    assert row["asset_symbol"] == "VFIAX"
    assert row["benchmark_symbol"] == "SPY"
    assert row["post_windows"][0]["asset_return_pct"] > 0
    assert dataset["context_label"].startswith("Descriptive price context only.")
