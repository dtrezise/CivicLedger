from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.entity_reference import build_entity_reference, stable_hash
from app.services.historical_news import build_primary_source_context
from app.services.sec_edgar import (
    SecIssuerTicker,
    SecIssuerTickerResult,
    parse_company_tickers,
)
from scripts.build_sec_filing_events import requests_from_issuer_aliases
from scripts.build_sec_issuer_aliases import build_dataset as build_alias_dataset


def _ticker(cik: str, name: str, ticker: str) -> SecIssuerTicker:
    return SecIssuerTicker(
        cik=cik,
        company_name=name,
        ticker=ticker,
        exchange="Nasdaq",
        source_url="https://www.sec.gov/files/company_tickers_exchange.json",
    )


def test_company_ticker_parser_supports_tabular_and_legacy_sec_payloads():
    tabular = parse_company_tickers(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[1652044, "Alphabet Inc.", "GOOG", "Nasdaq"]],
        },
        source_url="https://www.sec.gov/files/company_tickers_exchange.json",
    )
    legacy = parse_company_tickers(
        {"0": {"cik_str": 320193, "title": "Apple Inc.", "ticker": "AAPL"}},
        source_url="https://www.sec.gov/files/company_tickers.json",
    )

    assert [(row.cik, row.ticker) for row in tabular] == [("0001652044", "GOOG")]
    assert [(row.cik, row.ticker) for row in legacy] == [("0000320193", "AAPL")]


def test_alias_evidence_requires_unique_ticker_and_exact_issuer_name_core():
    result = SecIssuerTickerResult(
        records=(
            _ticker("0001065280", "NETFLIX INC", "NFLX"),
            _ticker("000104169", "WALMART INC.", "WMT"),
            _ticker("0000000001", "CURRENT FDC ISSUER", "FDC"),
        ),
        request_url="https://www.sec.gov/files/company_tickers_exchange.json",
        retrieval_status="cache_hit",
    )
    rows = [
        {
            "id": f"nflx-{index}",
            "ticker": "NFLX",
            "asset_display_name": "Netflix, Inc.",
            "source_dataset": "senate_ptr_transactions",
            "asset_class": "stock",
        }
        for index in range(6)
    ]
    rows.extend(
        {
            "id": f"fdc-{index}",
            "ticker": "FDC",
            "asset_display_name": "First Data Corporation",
            "source_dataset": "senate_ptr_transactions",
            "asset_class": "stock",
        }
        for index in range(5)
    )

    forward = build_alias_dataset(
        result, rows, artifact_date="2025-01-01", minimum_occurrences=5
    )
    reverse = build_alias_dataset(
        result, reversed(rows), artifact_date="2025-01-01", minimum_occurrences=5
    )

    assert json.dumps(forward, sort_keys=True) == json.dumps(reverse, sort_keys=True)
    assert [row["ticker"] for row in forward["records"]] == ["NFLX"]
    assert forward["records"][0]["occurrence_count"] == 6
    assert any(
        gap["ticker"] == "FDC" and gap["gap_type"] == "issuer_name_mismatch"
        for gap in forward["gaps"]
    )


def test_entity_reference_uses_sec_alias_evidence_without_fuzzy_linking():
    evidence = {
        "records": [
            {
                "id": "sec-issuer-alias:0001065280:NFLX",
                "cik": "0001065280",
                "official_name": "NETFLIX INC",
                "ticker": "NFLX",
                "source_url": "https://www.sec.gov/files/company_tickers_exchange.json",
                "observed_asset_classes": ["stock"],
                "aliases": [
                    {
                        "alias": "Netflix, Inc.",
                        "occurrence_count": 6,
                        "source_datasets": ["senate_ptr_transactions"],
                        "sample_transaction_ids": ["tx-1"],
                    }
                ],
            }
        ]
    }
    source_ids = (
        "asset_resolution",
        "company_entity_reference",
        "sec_filing_events",
        "sec_issuer_aliases",
        "market_prices",
        "market_ticker_history",
        "disclosure_labels",
    )
    dataset = build_entity_reference(
        asset_resolution={
            "assets": [
                {
                    "id": "unresolved-netflix",
                    "resolution_status": "unresolved",
                    "observed_names": ["Netflix, Inc."],
                    "normalized_name": "NETFLIX INC",
                    "disclosed_tickers": ["NFLX"],
                    "occurrence_count": 6,
                    "source_datasets": ["senate_ptr_transactions"],
                    "transaction_ids": ["tx-1"],
                }
            ]
        },
        company_entity_reference={"entities": []},
        sec_filing_events={"events": []},
        market_prices={"ticker_reference": {}},
        disclosure_rows=[
            {
                "id": "tx-1",
                "ticker": "NFLX",
                "asset_display_name": "Netflix, Inc.",
                "source_dataset": "senate_ptr_transactions",
            }
        ],
        ticker_history=[],
        source_snapshots=[
            {
                "source_id": source_id,
                "artifact_date": "2025-01-01",
                "sha256": stable_hash(source_id),
            }
            for source_id in source_ids
        ],
        issuer_alias_evidence=evidence,
    )

    issuer = next(row for row in dataset["organizations"] if row["issuer"])
    alias = next(row for row in issuer["aliases"] if row["alias"] == "Netflix, Inc.")
    assert issuer["issuer"]["cik"] == "0001065280"
    assert alias["occurrence_count"] == 6
    assert dataset["summary"]["evidence_resolved_asset_resolution_count"] == 1
    assert not any(
        row["issue_type"] == "unresolved_asset_resolution"
        for row in dataset["quality_issues"]
    )


def test_alias_rank_drives_bounded_deterministic_sec_request_expansion():
    payload = {
        "records": [
            {"cik": "320193", "ticker": "AAPL", "official_name": "Apple", "occurrence_count": 8},
            {"cik": "1065280", "ticker": "NFLX", "official_name": "Netflix", "occurrence_count": 12},
            {"cik": "104169", "ticker": "WMT", "official_name": "Walmart", "occurrence_count": 12},
        ]
    }

    requests = requests_from_issuer_aliases(
        payload,
        start_date="2025-01-01",
        end_date="2025-12-31",
        forms=("8-K",),
        excluded_ciks={"0000320193"},
        maximum_issuers=1,
    )

    assert [(request.request_id, request.cik) for request in requests] == [
        ("alias-nflx", "0001065280")
    ]


def test_primary_source_context_is_official_deterministic_and_records_gaps():
    federal = {
        "summary": {
            "selected_federal_register_agency_document_count": 1,
            "classified_federal_register_agency_document_count": 2,
            "selected_public_law_count": 1,
            "raw_public_law_count": 3,
        },
        "scope": {"supreme_court_pre_2017_status": "official_backfill_pending"},
        "events": [
            {
                "id": "agency-1",
                "date": "2025-01-02",
                "event_type": "agency_rule",
                "label": "Official rule",
                "source": "Federal Register",
                "sources": [
                    "https://publisher.example/story",
                    "https://www.federalregister.gov/documents/rule",
                ],
            },
            {
                "id": "court-1",
                "date": "2025-01-03",
                "event_type": "court_decision",
                "label": "Court opinion",
                "source": "Supreme Court",
                "sources": [],
            },
        ],
    }
    sec = {
        "coverage_report": {
            "offline": {"status": "unavailable", "cik": "0000000001", "reason": "offline"}
        },
        "events": [
            {
                "id": "sec-filing:one",
                "date": "2025-01-04",
                "title": "Issuer filed 8-K",
                "company": {"cik": "0000000001", "name": "Issuer", "tickers": ["ONE"]},
                "filing": {"accession_number": "one", "form": "8-K"},
                "sources": [
                    {"url": "https://www.sec.gov/Archives/edgar/data/1/one-index.html"}
                ],
            }
        ],
    }

    first = build_primary_source_context(
        federal_events=federal,
        sec_filing_events=sec,
        artifact_date="2025-01-05",
    )
    second = build_primary_source_context(
        federal_events={**federal, "events": list(reversed(federal["events"]))},
        sec_filing_events=sec,
        artifact_date="2025-01-05",
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["summary"]["record_counts_by_category"] == {
        "agencies": 1,
        "courts": 1,
        "congress": 0,
        "issuer_filings": 1,
    }
    assert first["records"][0]["primary_url"].startswith("https://www.federalregister.gov/")
    assert all(row["correlation_asserted"] is False for row in first["records"])
    assert {gap["gap_type"] for gap in first["gaps"]} >= {
        "bounded_selection",
        "known_historical_backfill_gap",
        "missing_official_url",
        "sec_request_not_fully_covered",
    }
