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
FEDERAL_EVENTS = ROOT / "data" / "context" / "federal_events.json"
HOUSE_DISCLOSURE_INDEX = ROOT / "data" / "disclosures" / "house_disclosure_index.json"
HOUSE_PTR_TRANSACTIONS = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
SENATE_DISCLOSURE_INDEX = ROOT / "data" / "disclosures" / "senate_disclosure_index.json"
SENATE_PTR_TRANSACTIONS = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"


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


def test_congressional_chambers_follow_historical_terms_not_current_chamber():
    data = json.loads((ROOT / "data" / "public_officials" / "congressional_service_terms.json").read_text())

    peter_welch = [role for role in data["roles"] if role["external_person_id"] == "congress:W000800"]
    adam_schiff = [role for role in data["roles"] if role["external_person_id"] == "congress:S001150"]
    welch_by_congress = {role["source_metadata"]["congress_number"]: role for role in peter_welch}
    schiff_by_congress = {role["source_metadata"]["congress_number"]: role for role in adam_schiff}

    assert welch_by_congress[114]["source_metadata"]["chamber"] == "House"
    assert welch_by_congress[118]["source_metadata"]["chamber"] == "Senate"
    assert schiff_by_congress[118]["source_metadata"]["chamber"] == "House"
    assert schiff_by_congress[119]["source_metadata"]["chamber"] == "Senate"


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


def test_house_archive_is_source_backed_review_gated_and_partitioned():
    index = json.loads(HOUSE_DISCLOSURE_INDEX.read_text())
    archive = json.loads(HOUSE_PTR_TRANSACTIONS.read_text())

    assert index["summary"]["source_index_count"] >= 18
    assert index["summary"]["source_index_row_count"] >= 47_000
    assert index["summary"]["member_ptr_document_count"] >= 7_500
    assert index["summary"]["ambiguous_member_ptr_document_count"] == 0
    assert archive["schema_version"] == "house-ptr-transactions-manifest-v2"
    assert archive["summary"]["processed_document_count"] >= 7_500
    assert archive["summary"]["parser_preview_transaction_count"] >= 53_000
    assert archive["summary"]["document_status_counts"]["parser_preview"] >= 5_500
    assert archive["summary"]["document_status_counts"]["ocr_required"] >= 1_900
    assert archive["summary"]["public_production_trade_count"] == 0
    assert set(archive["year_partitions"]) == {str(year) for year in range(2015, 2027)}


def test_senate_archive_indexes_all_senators_and_preserves_feinstein_images():
    index = json.loads(SENATE_DISCLOSURE_INDEX.read_text())
    archive = json.loads(SENATE_PTR_TRANSACTIONS.read_text())

    assert index["schema_version"] == "senate-disclosure-index-v1"
    assert index["summary"]["document_count"] >= 2_100
    assert index["summary"]["matched_document_count"] >= 1_800
    assert index["summary"]["report_format_counts"]["electronic_html"] >= 1_500
    assert index["summary"]["report_format_counts"]["paper_images"] >= 550
    assert index["validation"]["matched_document_count"] == 40

    assert archive["schema_version"] == "senate-ptr-transactions-v1"
    assert archive["summary"]["processed_document_count"] >= 1_800
    assert archive["summary"]["processed_official_count"] >= 60
    assert archive["summary"]["parser_preview_transaction_count"] > 0
    assert archive["summary"]["public_production_trade_count"] == 0
    assert archive["validation"]["processed_document_count"] == 40
    assert archive["validation"]["paper_image_review_document_count"] == 40
    assert archive["validation"]["parser_preview_transaction_count"] == 0


def test_federal_event_context_spans_all_branches_with_official_sources():
    data = json.loads(FEDERAL_EVENTS.read_text())
    summary = data["summary"]

    assert summary["raw_public_law_count"] >= 2_800
    assert summary["raw_executive_order_count"] >= 900
    assert summary["raw_supreme_court_opinion_count"] >= 500
    assert summary["event_count"] >= 900
    assert summary["counts_by_type"]["legislation"] >= 400
    assert summary["counts_by_type"]["executive_order"] >= 250
    assert summary["counts_by_type"]["court_decision"] >= 100
    assert data["scope"]["start_date"] == "2009-01-20"
    assert data["scope"]["structured_supreme_court_term_range"][0] == 2017
    assert data["scope"]["supreme_court_pre_2017_status"] == "official_bound_volume_backfill_pending"
    assert all(event["source_tier"] == "official" for event in data["events"])
    assert all(event["sources"] and event["sources"][0].startswith("https://") for event in data["events"])


def test_pages_career_trade_timeline_defaults_to_presidents():
    data = json.loads((ROOT / "pages-site" / "data" / "civicledger-static.json").read_text())
    timeline = data["career_trade_timeline"]
    manifest = json.loads((ROOT / "pages-site" / "data" / "manifest.json").read_text())
    timeline_index = json.loads(
        (ROOT / "pages-site" / "data" / manifest["files"]["timeline_index"]["path"]).read_text()
    )
    timeline["summary"] = timeline_index["summary"]
    president_rows = []
    for official_id in timeline_index["default_official_ids"]:
        record = manifest["partitions"]["timelines"][official_id]
        official = json.loads((ROOT / "pages-site" / "data" / record["path"]).read_text())["official"]
        defaults = official.get("trade_record_defaults", {})
        official["trades"] = [{**defaults, **trade} for trade in official.get("trades", [])]
        president_rows.append(official)
    timeline["officials"] = president_rows

    assert timeline["schema_version"] == "career-trade-timeline-v3"
    assert timeline["event_relationship_methodology_version"] == "event-relevance-v4"
    assert timeline["trade_context_methodology"]["version"] == "trade-window-v2"
    assert {"exec:barack-obama", "exec:donald-j-trump", "exec:joseph-r-biden"} <= set(
        timeline["default_official_ids"]
    )
    assert "exec:kamala-harris" not in set(timeline["default_official_ids"])
    assert "exec:michael-r-pence" not in set(timeline["default_official_ids"])
    assert timeline["summary"]["default_official_count"] >= 3
    assert timeline["summary"]["event_count"] >= 1_100
    assert timeline["summary"]["trade_cluster_count"] >= 20
    assert timeline["summary"]["presidential_oge_status_count"] == 4
    assert timeline["summary"]["presidential_oge_document_count"] >= 19
    assert timeline["summary"]["presidential_oge_parser_preview_transaction_count"] >= 7_100
    assert timeline["summary"]["trade_context_candidate_count"] >= 1
    assert timeline["summary"]["presidential_oge_public_production_trade_count"] == 0
    assert timeline["summary"]["official_count"] >= 298
    assert timeline["summary"]["trade_count"] >= 54_000
    assert timeline["summary"]["house_ptr_timeline_transaction_count"] >= 53_000
    assert timeline["summary"]["house_ptr_out_of_service_trade_count"] >= 1
    assert "crypto" in timeline["asset_classes"]
    assert "fixed_income" in timeline["asset_classes"]
    assert "event_window" in timeline["axis_modes"]
    assert president_rows
    assert all(official["timeline_group"] == "presidential_baseline" for official in president_rows)
    trump = next(official for official in president_rows if official["id"] == "exec:donald-j-trump")
    biden = next(official for official in president_rows if official["id"] == "exec:joseph-r-biden")
    obama = next(official for official in president_rows if official["id"] == "exec:barack-obama")
    assert trump["stats"]["record_status"] == "official_oge_parser_preview_not_promoted"
    assert trump["stats"]["parser_preview_trade_count"] >= 7_100
    assert trump["stats"]["public_production_trade_count"] == 0
    assert any(trade["date"].startswith("2019-") for trade in trump["trades"])
    assert any(trade["date"].startswith("2020-") for trade in trump["trades"])
    assert any(
        trade["decision_authority_status"] == "report_states_no_investment_decision_authority"
        for trade in trump["trades"]
    )
    assert biden["stats"]["record_status"] == "official_oge_parser_preview_not_promoted"
    assert biden["stats"]["document_count"] >= 5
    assert biden["stats"]["parser_preview_trade_count"] == 13
    assert {trade["date"] for trade in biden["trades"]} == {"2021-05-24"}
    assert obama["stats"]["record_status"] == "official_oge_parser_preview_not_promoted"
    assert obama["stats"]["document_count"] >= 8
    assert obama["stats"]["parser_preview_trade_count"] == 16
    assert len(trump["service_periods"]) == 2
    assert trump["service_periods"][0]["end"] == "2021-01-20"
    assert trump["service_periods"][1]["start"] == "2025-01-20"
    assert all(trade["career_day"] is not None for trade in trump["trades"])
    assert all(
        not ("2021-01-21" <= event["date"] <= "2025-01-19")
        for event in trump["events"]
    )
    assert all(
        event.get("trade_context_candidate") is True
        and abs(event["nearest_trade_days"]) <= 7
        for event in trump["events"]
        if event["relationship_tier"] == "general_macro" and event["display_default"] is True
    )
    assert all(
        event.get("candidate_basis")
        == "source_specificity_temporal_proximity_and_descriptive_market_context"
        for event in trump["events"]
        if event.get("trade_context_candidate")
    )
    assert all(
        event.get("candidate_score_components") and event.get("candidate_rank")
        for event in trump["events"]
        if event.get("trade_context_candidate")
    )
    assert all(
        trade["record_status"] != "fixture"
        for official in timeline["officials"]
        for trade in official["trades"]
    )


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
    assert documents["summary"]["document_count"] >= 19
    assert documents["summary"]["document_counts_by_official"]["exec:barack-obama"] >= 8
    assert documents["summary"]["document_counts_by_official"]["exec:joseph-r-biden"] >= 5
    assert documents["summary"]["document_counts_by_official"]["exec:donald-j-trump"] >= 6
    assert documents["summary"]["public_production_trade_count"] == 0
    assert documents["summary"]["fetch_failure_count"] == 0
    assert all(document["source_tier"] == "official" for document in documents["documents"])
    assert all(
        document["review_required_before_public_trade"] is True
        or document.get("transaction_section_status") == "no_reportable_transactions"
        for document in documents["documents"]
    )
    assert documents["unavailable_documents"] == []
    assert any(
        row["document_id"] == "oge-obama-2017-termination-278"
        and row["transaction_section_status"] == "no_reportable_transactions"
        for row in documents["documents"]
    )

    assert transactions["schema_version"] == "presidential-oge-transactions-v1"
    assert transactions["summary"]["parser_preview_transaction_count"] >= 7_100
    assert transactions["summary"]["public_production_trade_count"] == 0
    assert transactions["summary"]["transaction_counts_by_official"]["exec:barack-obama"] == 16
    assert transactions["summary"]["transaction_counts_by_official"]["exec:joseph-r-biden"] == 13
    assert transactions["summary"]["transaction_counts_by_official"]["exec:donald-j-trump"] >= 7_100
    sample = transactions["transactions"][0]
    assert "preview" in sample["record_status"]
    assert sample["review_required_before_public_trade"] is True
    assert sample["public_production_trade"] is False
    assert sample["trade_date"].startswith("20")


def test_disclosure_ingestion_queue_covers_all_branches_and_congress_scope():
    data = json.loads(DISCLOSURE_QUEUE.read_text())
    summary = data["summary"]

    assert data["schema_version"] == "disclosure-ingestion-queue-v2"
    assert summary["queue_item_count"] >= 5800
    assert summary["counts_by_source"]["house-financial-disclosure"] >= 3900
    assert summary["counts_by_source"]["senate-public-financial-disclosure"] >= 900
    assert summary["counts_by_source"]["oge-individual-disclosures"] >= 70
    assert summary["counts_by_source"]["judicial-financial-disclosure"] >= 800
    assert set(summary["counts_by_congress"]) == {"111", "112", "113", "114", "115", "116", "117", "118", "119"}
    assert all(row["review_required"] is True for row in data["entries"][:250])
    assert all(row["promotion_status"] == "raw_document_required" for row in data["entries"][:250])
    assert summary["unique_official_count"] == 2159
    assert all(row.get("absence_inference_allowed") is False for row in data["entries"])
    president_terms = [
        (row["official_id"], row.get("presidential_term"))
        for row in data["entries"]
        if row.get("role_category") == "elected_executive"
        and row["official_id"] in {"exec:barack-obama", "exec:donald-j-trump", "exec:joseph-r-biden"}
    ]
    assert len(president_terms) == len(set(president_terms))


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
    overview = json.loads((ROOT / "pages-site" / "data" / "partitions" / "overview.json").read_text())
    public_events = json.loads((ROOT / "pages-site" / "data" / "partitions" / "events.json").read_text())

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
    branch_map = {row["branch"]: row for row in completeness["branches"]}
    assert branch_map["Legislative"]["official_count"] == 1265
    assert branch_map["Legislative"]["parser_preview_transaction_count"] >= 64_000
    assert branch_map["Executive"]["indexed_document_count"] == 19
    assert branch_map["Judicial"]["official_count"] == 822
    assert branch_map["Judicial"]["readiness_status"] == "roster_manifest_ready"
    assert overview["disclosure_pipeline"]["completeness_dashboard"]["summary"]["queue_item_count"] >= 5800
    assert public_events["events"][0]["ticker_scope"] is not None
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
