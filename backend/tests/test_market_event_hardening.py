from datetime import date, timedelta
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.asset_resolution import (  # noqa: E402
    asset_resolution_diagnostics,
    asset_resolution_record,
)
from app.services.market_prices import (  # noqa: E402
    TickerHistoryMapping,
    diagnose_price_series,
    partition_price_points_by_symbol_year,
    resolve_ticker_history,
    symbol_year_partition_path,
    validate_ticker_history,
)
from app.services.market_reactions import (  # noqa: E402
    MarketReactionCalculator,
    load_partitioned_reaction_dataset,
)
from app.services.official_event_involvement import (  # noqa: E402
    build_official_event_involvement,
    canonical_event_source_url,
    deduplicate_event_source_urls,
    relationship_review_priority_fields,
)
from scripts.build_market_price_dataset import build_symbol_year_partition_manifest  # noqa: E402
from scripts.build_trade_market_reactions import (  # noqa: E402
    build_dataset as build_reaction_dataset,
    partition_reactions_by_symbol_year,
    write_partitioned_dataset,
)


def _history():
    return (
        TickerHistoryMapping(
            "OLD",
            "NEW",
            "2010-01-01",
            "2020-12-31",
            "Example Corp.",
            "ticker_change",
            "fixture",
        ),
        TickerHistoryMapping(
            "OLD",
            "NEWER",
            "2021-01-01",
            None,
            "Example Corp.",
            "ticker_change",
            "fixture",
        ),
    )


def _daily_series(symbol: str, start: str, day_count: int, source: str = "fixture") -> dict:
    start_date = date.fromisoformat(start)
    return {
        "symbol": symbol,
        "source": source,
        "source_url": f"https://example.test/{symbol}",
        "points": [
            {
                "symbol": symbol,
                "date": (start_date + timedelta(days=offset)).isoformat(),
                "adj_close": 100 + offset,
                "close": 1000 + offset,
                "source": source,
            }
            for offset in range(day_count)
        ],
    }


def test_date_bounded_ticker_history_is_deterministic_and_rejects_gaps_or_overlap():
    history = _history()

    first = resolve_ticker_history("old", "2020-06-01", history)
    second = resolve_ticker_history("old", "2021-06-01", reversed(history))

    assert first["market_symbol"] == "NEW"
    assert second["market_symbol"] == "NEWER"
    assert validate_ticker_history(reversed(history)) == history
    assert resolve_ticker_history("old", "2009-12-31", history)["status"] == "outside_effective_range"

    overlap = history + (
        TickerHistoryMapping(
            "OLD", "BAD", "2020-01-01", "2021-06-01", "Example Corp.", "ticker_change", "fixture"
        ),
    )
    with pytest.raises(ValueError, match="Overlapping ticker-history ranges"):
        validate_ticker_history(overlap)


def test_market_diagnostics_find_corporate_actions_staleness_order_and_duplicates():
    points = [
        {"date": "2024-01-03", "adj_close": 100, "split_factor": 2, "source": "fixture"},
        {"date": "2024-01-02", "adj_close": 50, "div_cash": 0.5, "source": "fixture"},
        {"date": "2024-01-03", "adj_close": 200, "source": "fixture"},
    ]

    diagnostics = diagnose_price_series("ABC", points, as_of="2024-02-01", stale_after_days=7)

    assert diagnostics["is_stale"] is True
    assert diagnostics["corporate_action_count"] == 2
    assert diagnostics["duplicate_date_count"] == 1
    assert diagnostics["out_of_order_count"] == 1
    assert "corporate_actions_present" in diagnostics["diagnostic_codes"]


def test_symbol_year_partition_helpers_are_stable_and_path_safe():
    series = {
        "abc": {
            "points": [
                {"date": "2024-02-01", "close": 2},
                {"date": "2023-12-31", "close": 1},
            ]
        }
    }

    partitions = partition_price_points_by_symbol_year(series)
    manifest = build_symbol_year_partition_manifest(series)

    assert list(partitions) == ["ABC:2023", "ABC:2024"]
    assert symbol_year_partition_path("abc", 2024) == "symbols/ABC/2024.json"
    assert manifest["ABC:2024"]["point_count"] == 1
    with pytest.raises(ValueError, match="Invalid market symbol"):
        symbol_year_partition_path("../ABC", 2024)


def test_calendar_windows_are_neutral_and_preserve_provider_provenance():
    market_prices = {
        "generated_at": "2024-04-15",
        "series": {
            "ABC": _daily_series("ABC", "2024-01-01", 120, "asset-provider"),
            "SPY": _daily_series("SPY", "2024-01-01", 120, "benchmark-provider"),
        },
    }

    reaction = MarketReactionCalculator(market_prices).compute(
        "ABC", "SPY", "2024-04-01", (1,), (7, 30, 90)
    )

    assert reaction["status"] == "covered"
    assert [row["day_count"] for row in reaction["calendar_pre_windows"]] == [7, 30, 90]
    assert [row["day_count"] for row in reaction["calendar_post_windows"]] == [7]
    assert reaction["calendar_pre_windows"][0]["provider_provenance"]["asset"][
        "start_provider"
    ] == "asset-provider"
    assert reaction["provider_provenance"]["benchmark_providers"] == ["benchmark-provider"]
    assert reaction["calendar_pre_windows"][0]["asset_return_pct"] > 0


def test_reaction_builder_maps_historical_ticker_and_reports_partitions_and_coverage():
    market_prices = {
        "generated_at": "2021-01-01",
        "source": {"id": "fixture"},
        "ticker_reference": {
            "META": {
                "issuer_name": "Meta Platforms Inc.",
                "asset_class": "equity",
                "sector": "Communication Services",
                "benchmark_symbol": "QQQ",
            }
        },
        "series": {
            "META": _daily_series("META", "2019-09-01", 180, "asset-provider"),
            "QQQ": _daily_series("QQQ", "2019-09-01", 180, "benchmark-provider"),
        },
    }
    dataset = build_reaction_dataset(
        [
            {
                "id": "tx-fb",
                "source_dataset": "fixture",
                "trade_date": "2019-12-01",
                "action": "SELL",
                "asset_display_name": "Facebook Inc.",
                "asset_class": "equity",
                "ticker": "FB",
            }
        ],
        market_prices,
        window_sessions=(1,),
        window_days=(7, 30, 90),
        generated_at="2021-01-01",
    )

    row = dataset["reactions"][0]
    assert row["asset_symbol"] == "META"
    assert row["ticker_history_status"] == "date_bounded_mapping"
    assert dataset["summary"]["missing_provider_provenance_count"] == 0
    assert dataset["coverage_diagnostics"]["symbol_year_partitions"]["META:2019"][
        "reaction_count"
    ] == 1
    assert partition_reactions_by_symbol_year(dataset["reactions"])["META:2019"]["year"] == 2019


def test_reaction_dataset_writes_and_verifies_symbol_year_partitions(tmp_path):
    output = tmp_path / "context" / "trade_market_reactions.json"
    partition_root = tmp_path / "context" / "trade_market_reactions"
    reactions = [
        {"id": "two", "asset_symbol": "META", "event_date": "2020-01-02"},
        {"id": "one", "asset_symbol": "META", "event_date": "2019-12-01"},
        {"id": "three", "asset_symbol": "AAPL", "event_date": "2020-02-03"},
    ]
    dataset = {
        "schema_version": "trade-market-context-v1",
        "generated_at": "2021-01-01",
        "summary": {"market_context_row_count": len(reactions)},
        "coverage_diagnostics": {},
        "reactions": reactions,
    }

    manifest = write_partitioned_dataset(dataset, output, partition_root)
    loaded = load_partitioned_reaction_dataset(output)

    assert "reactions" not in manifest
    assert manifest["storage"]["partition_count"] == 3
    assert manifest["storage"]["reaction_count"] == 3
    assert [row["id"] for row in loaded["reactions"]] == ["one", "two", "three"]
    assert max(path.stat().st_size for path in partition_root.rglob("*.json")) < output.stat().st_size * 4

    first_record = next(iter(manifest["storage"]["partitions"].values()))
    first_path = output.parent / first_record["path"]
    first_path.write_text(first_path.read_text().replace("three", "tampered"))
    with pytest.raises(ValueError, match="hash mismatch"):
        load_partitioned_reaction_dataset(output)


def test_checked_in_reaction_manifest_reconciles_and_keeps_shards_small():
    manifest_path = ROOT / "data" / "context" / "trade_market_reactions.json"
    manifest = json.loads(manifest_path.read_text())
    loaded = load_partitioned_reaction_dataset(manifest_path)

    assert manifest["storage"]["format"] == "symbol_year_partitions"
    assert manifest["storage"]["partition_count"] >= 180
    assert len(loaded["reactions"]) == manifest["summary"]["market_context_row_count"]
    assert max(
        (manifest_path.parent / row["path"]).stat().st_size
        for row in manifest["storage"]["partitions"].values()
    ) < 2_000_000


def test_asset_resolution_diagnostics_keep_effective_date_and_unresolved_records_separate():
    resolved = asset_resolution_record(
        "Vanguard 500 Index Fund", asset_class="mutual_fund", effective_date="2020-01-02"
    )
    unresolved = asset_resolution_record(
        "Unknown Income Fund", asset_class="fund", effective_date="2020-01-02"
    )
    diagnostics = asset_resolution_diagnostics(
        [{"transaction_id": "one", **resolved}, {"transaction_id": "two", **unresolved}]
    )

    assert resolved["ticker_history_status"] == "passthrough_no_history"
    assert diagnostics["resolved_count"] == 1
    assert diagnostics["unresolved_count"] == 1
    assert diagnostics["missing_effective_date_count"] == 0


def test_event_source_dedup_and_review_priority_are_exposed_by_builder():
    url = "HTTPS://Example.GOV/event/?utm_source=email&b=2&a=1"
    canonical = canonical_event_source_url(url)
    sources, diagnostics = deduplicate_event_source_urls(
        [url, "https://example.gov/event?a=1&b=2#fragment"]
    )
    priority = relationship_review_priority_fields(
        {"relationship_type": "sponsor", "source_snapshot_ids": ["one", "two"]},
        actor={"resolution_status": "matched_public_official_role"},
    )

    assert canonical == "https://example.gov/event?a=1&b=2"
    assert sources == [canonical]
    assert diagnostics["duplicate_source_count"] == 1
    assert priority["review_priority_band"] == "high"
    assert priority["review_priority_score"] == 98

    dataset = build_official_event_involvement(
        {
            "events": [
                {
                    "id": "fixture-event",
                    "event_type": "policy",
                    "date": "2024-01-01",
                    "label": "Fixture",
                    "jurisdiction_scope": ["securities"],
                    "sources": [url, "https://example.gov/event?a=1&b=2"],
                }
            ]
        },
        {"roles": []},
        object(),
    )

    relationship = dataset["relationships"][0]
    assert relationship["review_priority_band"] == "low"
    assert relationship["review_status"] == "unreviewed"
    assert dataset["summary"]["event_source_diagnostics"]["duplicate_source_url_count"] == 1
    assert dataset["summary"]["review_priority_counts"] == {"low": 1}
