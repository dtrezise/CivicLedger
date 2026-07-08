import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "public_officials" / "public_official_roles.json"
FRED_CONTEXT = ROOT / "data" / "context" / "fred_market_context.json"
MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"
TERM_INDEX = ROOT / "data" / "public_officials" / "presidential_term_index.json"
PRESIDENTIAL_OGE_STATUS = ROOT / "data" / "disclosures" / "presidential_oge_disclosure_status.json"
PRESIDENTIAL_OGE_DOCUMENTS = ROOT / "data" / "disclosures" / "presidential_oge_documents.json"
PRESIDENTIAL_OGE_TRANSACTIONS = ROOT / "data" / "disclosures" / "presidential_oge_transactions.json"
DISCLOSURE_QUEUE = ROOT / "data" / "disclosures" / "disclosure_ingestion_queue.json"
RAW_ARCHIVE_INDEX = ROOT / "data" / "disclosures" / "raw_document_archive_index.json"
REVIEWED_PROMOTIONS = ROOT / "data" / "disclosures" / "reviewed_disclosure_promotions.json"
DISCLOSURE_COMPLETENESS = ROOT / "data" / "disclosures" / "disclosure_completeness_dashboard.json"
RETRIEVAL_BATCHES = ROOT / "data" / "disclosures" / "disclosure_retrieval_batches.json"
PRODUCTION_PROMOTIONS = ROOT / "data" / "disclosures" / "production_trade_promotions.json"
SOURCE_STALENESS_ALERTS = ROOT / "data" / "disclosures" / "source_staleness_alerts.json"
EVENT_ENTITY_MAP = ROOT / "data" / "context" / "event_entity_map.json"
COMPANY_ENTITY_REFERENCE = ROOT / "data" / "context" / "company_entity_reference.json"
CONGRESS_JURISDICTION_MAP = ROOT / "data" / "context" / "congress_jurisdiction_map.json"
BRANCH_JURISDICTION_MAP = ROOT / "data" / "context" / "branch_jurisdiction_map.json"


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
    assert timeline["summary"]["presidential_oge_document_count"] >= 11
    assert timeline["summary"]["presidential_oge_parser_preview_transaction_count"] >= 300
    assert timeline["summary"]["presidential_oge_public_production_trade_count"] == 0
    assert "crypto" in timeline["asset_classes"]
    assert "fixed_income" in timeline["asset_classes"]
    assert "event_window" in timeline["axis_modes"]
    president_rows = [
        official
        for official in timeline["officials"]
        if official["id"] in timeline["default_official_ids"]
    ]
    assert president_rows
    assert all(official["timeline_group"] == "presidential_baseline" for official in president_rows)
    trump = next(official for official in president_rows if official["id"] == "exec:donald-j-trump")
    biden = next(official for official in president_rows if official["id"] == "exec:joseph-r-biden")
    obama = next(official for official in president_rows if official["id"] == "exec:barack-obama")
    assert trump["stats"]["record_status"] == "official_oge_parser_preview_not_promoted"
    assert trump["stats"]["parser_preview_trade_count"] >= 300
    assert trump["stats"]["public_production_trade_count"] == 0
    assert biden["stats"]["record_status"] == "official_oge_documents_indexed"
    assert biden["stats"]["document_count"] >= 5
    assert obama["stats"]["record_status"] == "source_status_only"


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


def test_presidential_oge_documents_add_official_disclosures_and_preview_rows():
    documents = json.loads(PRESIDENTIAL_OGE_DOCUMENTS.read_text())
    transactions = json.loads(PRESIDENTIAL_OGE_TRANSACTIONS.read_text())

    assert documents["schema_version"] == "presidential-oge-documents-v1"
    assert documents["summary"]["document_count"] >= 11
    assert documents["summary"]["document_counts_by_official"]["exec:joseph-r-biden"] >= 5
    assert documents["summary"]["document_counts_by_official"]["exec:donald-j-trump"] >= 6
    assert documents["summary"]["public_production_trade_count"] == 0
    assert documents["summary"]["fetch_failure_count"] == 0
    assert all(document["source_tier"] == "official" for document in documents["documents"])
    assert all(document["review_required_before_public_trade"] is True for document in documents["documents"])
    assert any(row["official_id"] == "exec:barack-obama" for row in documents["unavailable_documents"])

    assert transactions["schema_version"] == "presidential-oge-transactions-v1"
    assert transactions["summary"]["parser_preview_transaction_count"] >= 300
    assert transactions["summary"]["public_production_trade_count"] == 0
    assert transactions["summary"]["transaction_counts_by_official"]["exec:donald-j-trump"] >= 300
    sample = transactions["transactions"][0]
    assert sample["record_status"] == "official_oge_parser_preview_not_promoted"
    assert sample["review_required_before_public_trade"] is True
    assert sample["public_production_trade"] is False
    assert sample["trade_date"].startswith("20")


def test_disclosure_ingestion_queue_covers_all_branches_and_congress_scope():
    data = json.loads(DISCLOSURE_QUEUE.read_text())
    summary = data["summary"]

    assert data["schema_version"] == "disclosure-ingestion-queue-v1"
    assert summary["queue_item_count"] >= 5800
    assert summary["counts_by_source"]["house-financial-disclosure"] >= 3900
    assert summary["counts_by_source"]["senate-public-financial-disclosure"] >= 900
    assert summary["counts_by_source"]["oge-individual-disclosures"] >= 70
    assert summary["counts_by_source"]["judicial-financial-disclosure"] >= 800
    assert set(summary["counts_by_congress"]) == {"111", "112", "113", "114", "115", "116", "117", "118", "119"}
    assert all(row["review_required"] is True for row in data["entries"][:250])
    assert all(row["promotion_status"] == "raw_document_required" for row in data["entries"][:250])


def test_raw_archive_and_reviewed_promotion_keep_fixture_boundary_clear():
    raw_archive = json.loads(RAW_ARCHIVE_INDEX.read_text())
    promotions = json.loads(REVIEWED_PROMOTIONS.read_text())

    assert raw_archive["schema_version"] == "raw-document-archive-index-v1"
    assert raw_archive["summary"]["archived_document_count"] >= 1
    sample = next(row for row in raw_archive["documents"] if row["document_id"] == "oge-public-278e-sample")
    assert sample["archive_status"] == "archived"
    assert sample["file_hash"]
    assert sample["review_required_before_public_trade"] is True

    assert promotions["schema_version"] == "reviewed-disclosure-promotions-v1"
    assert promotions["summary"]["reviewed_fixture_promotion_count"] == 1
    assert promotions["summary"]["public_production_trade_count"] == 0
    promotion = promotions["promotions"][0]
    assert promotion["record_status"] == "reviewed_fixture_not_public_production"
    assert promotion["public_production_trade"] is False
    assert promotion["review_required_before_public_trade"] is True


def test_context_maps_and_pages_completeness_are_available():
    event_map = json.loads(EVENT_ENTITY_MAP.read_text())
    company_reference = json.loads(COMPANY_ENTITY_REFERENCE.read_text())
    congress_map = json.loads(CONGRESS_JURISDICTION_MAP.read_text())
    branch_map = json.loads(BRANCH_JURISDICTION_MAP.read_text())
    completeness = json.loads(DISCLOSURE_COMPLETENESS.read_text())
    pages = json.loads((ROOT / "pages-site" / "data" / "civicledger-static.json").read_text())

    assert event_map["schema_version"] == "event-entity-map-v1"
    assert any("BTCUSD" in mapping["ticker_scope"] for mapping in event_map["event_maps"])
    assert company_reference["schema_version"] == "company-entity-reference-v1"
    assert any("NVDA" in entity["ticker_scope"] for entity in company_reference["entities"])
    assert congress_map["schema_version"] == "congress-jurisdiction-map-v1"
    assert len(congress_map["committee_maps"]) >= 12
    assert branch_map["schema_version"] == "branch-jurisdiction-map-v1"
    assert branch_map["executive_maps"]
    assert branch_map["judicial_maps"]

    assert completeness["schema_version"] == "disclosure-completeness-dashboard-v1"
    assert completeness["summary"]["branch_count"] == 3
    assert completeness["summary"]["reviewed_public_trade_count"] == 0
    assert pages["disclosure_pipeline"]["completeness_dashboard"]["summary"]["queue_item_count"] >= 5800
    assert pages["career_trade_timeline"]["events"][0]["ticker_scope"] is not None
    assert pages["career_trade_timeline"]["event_entity_map"]["company_entity_count"] >= 8


def test_retrieval_batches_and_staleness_alerts_cover_first_pass_sources():
    batches = json.loads(RETRIEVAL_BATCHES.read_text())
    production = json.loads(PRODUCTION_PROMOTIONS.read_text())
    alerts = json.loads(SOURCE_STALENESS_ALERTS.read_text())
    pages = json.loads((ROOT / "pages-site" / "data" / "civicledger-static.json").read_text())

    assert batches["schema_version"] == "disclosure-retrieval-batches-v1"
    assert batches["summary"]["batch_count"] == 4
    assert batches["summary"]["candidate_count"] == 96
    assert {batch["source_id"] for batch in batches["batches"]} == {
        "house-financial-disclosure",
        "senate-public-financial-disclosure",
        "oge-individual-disclosures",
        "judicial-financial-disclosure",
    }
    house = next(batch for batch in batches["batches"] if batch["source_id"] == "house-financial-disclosure")
    assert house["batch_status"] == "ready_for_official_source_search"
    assert house["candidates"]
    assert all(candidate["review_required"] is True for candidate in house["candidates"])

    assert production["schema_version"] == "production-trade-promotions-v1"
    assert production["summary"]["reviewed_public_trade_count"] == 0
    assert production["summary"]["blocked_non_production_review_count"] >= 1
    assert alerts["schema_version"] == "source-staleness-alerts-v1"
    assert alerts["summary"]["alert_count"] >= 4
    assert alerts["summary"]["high_alert_count"] == 0
    assert pages["disclosure_pipeline"]["retrieval_batches"]["summary"]["batch_count"] == 4
    assert pages["disclosure_pipeline"]["source_staleness_alerts"]["summary"]["open_warning_count"] >= 1
