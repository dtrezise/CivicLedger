from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.entity_reference import (  # noqa: E402
    build_entity_reference,
    canonical_json,
    stable_hash,
)


def _snapshots():
    return [
        {
            "source_id": source_id,
            "path": f"fixture:{source_id}",
            "sha256": stable_hash(source_id),
            "schema_version": "fixture-v1",
            "artifact_date": "2025-01-10",
            "source_tier": "fixture",
        }
        for source_id in (
            "asset_resolution",
            "company_entity_reference",
            "sec_filing_events",
            "market_prices",
            "market_ticker_history",
            "disclosure_labels",
            "house_ptr_transactions:2024",
        )
    ]


def _inputs():
    return {
        "asset_resolution": {
            "assets": [
                {
                    "id": "asset-resolution-vfiax",
                    "resolution_status": "resolved",
                    "issuer_name": "Vanguard 500 Index Fund",
                    "canonical_name": "Vanguard 500 Index Fund Admiral Shares",
                    "asset_class": "mutual_fund",
                    "symbol": "VFIAX",
                    "identifier": "VFIAX",
                    "sectors": ["Broad Market"],
                    "observed_names": ["Vanguard 500 Index Fund"],
                    "occurrence_count": 2,
                    "source_datasets": ["house_ptr_transactions"],
                    "transaction_ids": ["tx-fund-1", "tx-fund-2"],
                },
                {
                    "id": "asset-resolution-unknown",
                    "resolution_status": "unresolved",
                    "normalized_name": "UNMAPPED FUND",
                    "observed_names": ["Unmapped Fund"],
                    "occurrence_count": 3,
                    "source_datasets": ["house_ptr_transactions"],
                    "transaction_ids": ["tx-u-1", "tx-u-2", "tx-u-3"],
                },
            ]
        },
        "company_entity_reference": {
            "entities": [
                {
                    "entity_id": "meta-platforms",
                    "issuer_name": "Meta Platforms Inc.",
                    "aliases": ["Meta", "META", "social media"],
                    "ticker_scope": ["META", "QQQ"],
                    "sector_scope": ["Communication Services"],
                }
            ]
        },
        "sec_filing_events": {
            "events": [
                {
                    "id": "sec-filing:0000320193:one",
                    "company": {
                        "cik": "0000320193",
                        "name": "Apple Inc.",
                        "tickers": ["AAPL"],
                        "exchanges": ["Nasdaq"],
                        "sic": "3571",
                        "sic_description": "Electronic Computers",
                    },
                    "source_urls": [
                        "https://data.sec.gov/submissions/CIK0000320193.json"
                    ],
                }
            ]
        },
        "market_prices": {
            "ticker_reference": {
                "AAPL": {
                    "issuer_name": "Apple Inc.",
                    "asset_class": "equity",
                    "sector": "Information Technology",
                },
                "META": {
                    "issuer_name": "Meta Platforms Inc.",
                    "asset_class": "equity",
                    "sector": "Communication Services",
                },
                "VFIAX": {
                    "issuer_name": "Vanguard 500 Index Fund Admiral Shares",
                    "asset_class": "mutual_fund",
                    "sector": "Broad Market",
                },
            }
        },
        "disclosure_rows": [
            {
                "id": "tx-apple",
                "source_dataset": "house_ptr_transactions",
                "_source_snapshot_id": "house_ptr_transactions:2024",
                "asset_display_name": "APPLE INC. COMMON STOCK",
                "ticker": "AAPL",
            },
            {
                "id": "tx-unknown-ticker",
                "source_dataset": "house_ptr_transactions",
                "_source_snapshot_id": "house_ptr_transactions:2024",
                "asset_display_name": "Unknown Example",
                "ticker": "ZZZZ",
            },
        ],
        "ticker_history": [
            {
                "disclosed_symbol": "FB",
                "market_symbol": "META",
                "valid_from": "2012-05-18",
                "valid_to": "2022-06-08",
                "issuer_name": "Meta Platforms Inc.",
                "change_type": "ticker_change",
                "provenance": "issuer_ticker_history",
            },
            {
                "disclosed_symbol": "META",
                "market_symbol": "META",
                "valid_from": "2022-06-09",
                "valid_to": None,
                "issuer_name": "Meta Platforms Inc.",
                "change_type": "current_symbol",
                "provenance": "issuer_ticker_history",
            },
        ],
        "source_snapshots": _snapshots(),
    }


def _build():
    return build_entity_reference(**_inputs())


def test_sec_and_market_records_merge_on_source_backed_ticker_and_keep_cik():
    dataset = _build()
    apple = next(row for row in dataset["organizations"] if row["issuer"] and row["issuer"]["cik"])

    assert apple["canonical_name"] == "Apple Inc."
    assert apple["issuer"]["cik"] == "0000320193"
    assert [row["value"] for row in apple["identifiers"] if row["scheme"] == "SEC_CIK"] == [
        "0000320193"
    ]
    assert {row["source_id"] for row in dataset["source_snapshots"]} >= {
        "sec_filing_events",
        "market_prices",
    }
    assert any(
        alias["alias"] == "APPLE INC. COMMON STOCK"
        and alias["occurrence_count"] == 1
        for alias in apple["aliases"]
    )


def test_contextual_ticker_scope_does_not_create_false_issuer_history():
    dataset = _build()
    meta = next(row for row in dataset["organizations"] if row["canonical_name"] == "Meta Platforms Inc.")
    meta_tickers = {
        row["symbol"]
        for row in dataset["ticker_histories"]
        if row["organization_id"] == meta["id"]
    }

    assert meta_tickers == {"FB", "META"}
    assert "QQQ" not in meta_tickers
    assert dataset["relationships"] == []


def test_only_explicit_ticker_ranges_receive_dates():
    dataset = _build()
    history = {row["symbol"]: row for row in dataset["ticker_histories"]}

    assert history["FB"]["valid_from"] == "2012-05-18"
    assert history["FB"]["valid_to"] == "2022-06-08"
    assert history["META"]["date_precision"] == "source_bounded"
    assert history["AAPL"]["valid_from"] is None
    assert history["AAPL"]["date_precision"] == "undated_source_observation"


def test_unresolved_assets_and_tickers_remain_quality_issues():
    dataset = _build()
    issues = dataset["quality_issues"]

    assert any(row["issue_type"] == "unresolved_asset_resolution" for row in issues)
    assert any(
        row["issue_type"] == "unresolved_disclosed_ticker" and row["ticker"] == "ZZZZ"
        for row in issues
    )
    assert not any(
        row["canonical_name"] == "Unknown Example" for row in dataset["organizations"]
    )


def test_fund_asset_resolution_merges_with_same_supported_symbol():
    dataset = _build()
    vfiax_assets = [row for row in dataset["assets"] if row["primary_symbol"] == "VFIAX"]

    assert len(vfiax_assets) == 1
    assert "Vanguard 500 Index Fund" in vfiax_assets[0]["aliases"]
    fund_org = next(
        row for row in dataset["organizations"] if row["id"] == vfiax_assets[0]["organization_id"]
    )
    assert fund_org["organization_type"] == "fund"
    assert fund_org["issuer"]["cik"] is None
    assert fund_org["issuer"]["identifier_status"] == "no_cik_in_sources"


def test_output_ids_hashes_and_order_are_deterministic():
    first = _build()
    reversed_inputs = _inputs()
    reversed_inputs["disclosure_rows"] = list(reversed(reversed_inputs["disclosure_rows"]))
    reversed_inputs["source_snapshots"] = list(reversed(reversed_inputs["source_snapshots"]))
    second = build_entity_reference(**reversed_inputs)

    assert canonical_json(first) == canonical_json(second)
    assert first["dataset_hash"] == stable_hash(
        {key: value for key, value in first.items() if key != "dataset_hash"}
    )
    assert all(uuid.UUID(row["id"]).version == 5 for row in first["organizations"])
    json.dumps(first, sort_keys=True)


def test_missing_provenance_snapshot_is_rejected():
    inputs = _inputs()
    inputs["source_snapshots"] = [
        row for row in inputs["source_snapshots"] if row["source_id"] != "market_prices"
    ]

    try:
        build_entity_reference(**inputs)
    except ValueError as exc:
        assert "market_prices" in str(exc)
    else:
        raise AssertionError("missing source snapshot should fail the build")


def test_stable_ids_do_not_depend_on_mutating_input_objects():
    inputs = _inputs()
    original = copy.deepcopy(inputs)
    build_entity_reference(**inputs)

    assert inputs == original
