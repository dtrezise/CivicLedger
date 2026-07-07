import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "public_officials" / "public_official_roles.json"
FRED_CONTEXT = ROOT / "data" / "context" / "fred_market_context.json"
MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"
TERM_INDEX = ROOT / "data" / "public_officials" / "presidential_term_index.json"
PRESIDENTIAL_OGE_STATUS = ROOT / "data" / "disclosures" / "presidential_oge_disclosure_status.json"


def test_public_officials_dataset_has_expected_initial_scope():
    data = json.loads(DATASET.read_text())
    summary = data["summary"]

    assert summary["person_count"] >= 2100
    assert summary["role_count"] >= 5900
    assert summary["role_counts_by_branch"]["Executive"] >= 50
    assert summary["role_counts_by_branch"]["Judicial"] >= 800
    assert summary["role_counts_by_branch"]["Legislative"] >= 4900
    assert summary["role_counts_by_category"]["representative"] >= 3800
    assert summary["role_counts_by_category"]["senator"] >= 900
    assert set(summary["role_counts_by_term"]) == {"obama-44", "trump-45", "biden-46", "trump-47"}


def test_public_officials_dataset_roles_are_source_backed():
    data = json.loads(DATASET.read_text())

    assert data["sources"]
    for role in data["roles"]:
        assert role["external_role_id"]
        assert role["external_person_id"]
        assert role["full_name"]
        assert role["source_url"].startswith("https://")
        assert role["source_tier"] in {"official", "official_archive"}


def test_congressional_dataset_has_111th_to_119th_counts():
    data = json.loads((ROOT / "data" / "public_officials" / "congressional_service_terms.json").read_text())
    summary = data["summary"]

    assert data["scope"]["congress_numbers"] == [111, 112, 113, 114, 115, 116, 117, 118, 119]
    assert summary["person_count"] >= 1200
    assert summary["role_count"] >= 4900
    assert set(summary["role_counts_by_congress"]) == {
        "111",
        "112",
        "113",
        "114",
        "115",
        "116",
        "117",
        "118",
        "119",
    }
    assert all(count >= 540 for count in summary["role_counts_by_congress"].values())
    assert summary["role_counts_by_chamber"]["House"] >= 3900
    assert summary["role_counts_by_chamber"]["Senate"] >= 900
    assert summary["role_counts_by_term"]["obama-44"] >= 2200


def test_fred_context_dataset_has_trade_relevant_macro_scope():
    data = json.loads(FRED_CONTEXT.read_text())

    assert data["summary"]["series_count"] == 6
    assert data["summary"]["observation_count"] >= 1000
    assert data["summary"]["release_event_count"] >= 20
    assert {"FEDFUNDS", "CPIAUCSL", "DGS10", "DGS2", "UNRATE", "USREC"} <= set(data["series"])
    assert data["summary"]["active_context_source"] == "FRED"
    assert set(data["summary"]["deferred_sources"]) == {"FEC", "USAspending"}
    assert data["context_label"].startswith("Context only")


def test_market_price_dataset_uses_tiingo_adjusted_close_scope():
    data = json.loads(MARKET_PRICES.read_text())

    assert any(
        provider in data["summary"]["active_market_price_provider"]
        for provider in ["Tiingo", "Nasdaq"]
    )
    assert data["summary"]["series_count"] >= 20
    assert data["summary"]["covered_symbol_count"] >= 20
    assert data["summary"]["missing_symbol_count"] == 0
    assert data["summary"]["price_point_count"] >= 15000
    assert {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "JNJ"} <= set(
        data["scope"]["symbols"]
    )
    assert {"SPY", "QQQ", "IWM", "BND", "VFIAX", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI"} <= set(
        data["scope"]["symbols"]
    )
    assert data["ticker_reference"]["AAPL"]["issuer_name"] == "Apple Inc."
    assert data["ticker_reference"]["AAPL"]["benchmark_symbol"] == "XLK"
    assert data["coverage_report"]["AAPL"]["status"] in {"covered", "cached"}
    assert data["series"]["SPY"]["price_field_for_overlays"] in {"adj_close", "close"}
    assert data["context_label"].startswith("Market-price overlays prefer Tiingo")


def test_pages_career_trade_timeline_defaults_to_presidents():
    data = json.loads((ROOT / "pages-site" / "data" / "civicledger-static.json").read_text())
    timeline = data["career_trade_timeline"]

    assert timeline["schema_version"] == "career-trade-timeline-v1"
    assert {"exec:barack-obama", "exec:donald-j-trump", "exec:joseph-r-biden"} <= set(
        timeline["default_official_ids"]
    )
    assert "exec:kamala-harris" not in set(timeline["default_official_ids"])
    assert "exec:michael-r-pence" not in set(timeline["default_official_ids"])
    assert timeline["summary"]["default_official_count"] >= 3
    assert timeline["summary"]["event_count"] >= 20
    assert timeline["summary"]["trade_cluster_count"] >= 20
    assert timeline["summary"]["presidential_oge_status_count"] == 4
    assert "crypto" in timeline["asset_classes"]
    assert "event_window" in timeline["axis_modes"]
    president_rows = [
        official
        for official in timeline["officials"]
        if official["id"] in timeline["default_official_ids"]
    ]
    assert president_rows
    assert all(official["timeline_group"] == "presidential_baseline" for official in president_rows)
    assert all(official["stats"]["record_status"] == "source_status_only" for official in president_rows)


def test_presidential_term_index_supports_historical_slices():
    data = json.loads(TERM_INDEX.read_text())

    assert data["schema_version"] == "presidential-term-index-v1"
    assert data["summary"]["term_count"] == 4
    assert data["summary"]["static_term_count"] == 3
    assert data["summary"]["active_term_count"] == 1
    obama = next(term for term in data["terms"] if term["term_id"] == "obama-44")
    assert obama["static_after_term_end"] is True
    assert obama["role_counts_by_branch"]["Legislative"] >= 2200


def test_presidential_oge_status_tracks_source_readiness_without_trade_claims():
    data = json.loads(PRESIDENTIAL_OGE_STATUS.read_text())

    assert data["schema_version"] == "presidential-oge-disclosure-status-v1"
    assert data["summary"]["official_status_count"] == 4
    assert data["summary"]["reviewed_trade_count"] == 0
    assert data["ingestion_policy"]["review_required_before_public_trade"] is True
    assert {"OGE Form 278e", "OGE Form 278-T"} <= set(data["ingestion_policy"]["supported_forms"])
