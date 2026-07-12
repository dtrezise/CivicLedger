#!/usr/bin/env python3
"""Validate the static public release contract and provenance boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA = ROOT / "pages-site" / "data"
MANIFEST = PUBLIC_DATA / "manifest.json"
HOUSE_INDEX = ROOT / "data" / "disclosures" / "house_disclosure_index.json"
HOUSE_TRANSACTIONS = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
SENATE_INDEX = ROOT / "data" / "disclosures" / "senate_disclosure_index.json"
SENATE_TRANSACTIONS = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"

INITIAL_PAYLOAD_LIMITS = {
    "overview": 500_000,
    "officials_index": 3_000_000,
    "coverage": 100_000,
    "events": 2_000_000,
    "timeline_index": 250_000,
    "market_index": 100_000,
}
AUXILIARY_FILE_LIMITS = {
    "entity_reference": 2_000_000,
}
PARTITION_LIMITS = {
    "timelines": 5_000_000,
    "roles": 8_000_000,
    "market": 5_000_000,
    "events": 2_000_000,
}
EXPECTED_FILE_SCHEMAS = {
    "coverage": "civicledger-coverage-v1",
    "entity_reference": "canonical-entity-reference-v1",
    "events": "timeline-event-index-v1",
    "market_index": "market-partition-index-v1",
    "officials_index": "official-index-v1",
    "timeline_index": "career-trade-timeline-v3",
}
EXPECTED_PARTITION_SCHEMAS = {
    "events": "timeline-events-v3",
    "roles": "official-role-details-v1",
    "timelines": "career-trade-timeline-v3",
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Unable to read valid JSON from {path}: {exc}") from exc


def require_iso_date(value: Any, context: str) -> None:
    require(isinstance(value, str), f"{context} must be an ISO date string")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{context} is not a valid ISO date: {value}") from exc


def require_https_url(value: Any, context: str) -> None:
    require(isinstance(value, str) and value.startswith("https://"), f"{context} must use HTTPS")
    parsed = urlparse(value)
    require(bool(parsed.netloc) and not parsed.username and not parsed.password, f"{context} is not a safe public URL")
    require(parsed.hostname not in {"localhost", "127.0.0.1", "0.0.0.0"}, f"{context} cannot point to localhost")


def iter_records(manifest: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for name, record in manifest.get("files", {}).items():
        yield "files", name, record
    for group, records in manifest.get("partitions", {}).items():
        for name, record in records.items():
            yield group, name, record


def validate_record(group: str, name: str, record: dict[str, Any]) -> Path:
    require(set(record) == {"path", "bytes", "sha256"}, f"Unexpected manifest fields for {group}.{name}")
    require(isinstance(record["path"], str) and record["path"], f"Missing path for {group}.{name}")
    require(isinstance(record["bytes"], int) and record["bytes"] > 0, f"Invalid byte count for {group}.{name}")
    require(isinstance(record["sha256"], str) and SHA256_PATTERN.fullmatch(record["sha256"]), f"Invalid hash for {group}.{name}")
    relative_path = Path(record["path"])
    require(not relative_path.is_absolute() and ".." not in relative_path.parts, f"Unsafe path for {group}.{name}")
    require(relative_path.parts[0] == "partitions" and relative_path.suffix == ".json", f"Unexpected public path for {group}.{name}")
    path = PUBLIC_DATA / relative_path
    require(path.is_file(), f"Missing public partition: {relative_path}")
    encoded = path.read_bytes()
    require(len(encoded) == record["bytes"], f"Byte count mismatch for {relative_path}")
    require(hashlib.sha256(encoded).hexdigest() == record["sha256"], f"Hash mismatch for {relative_path}")
    return path


def validate_source_catalog(overview: dict[str, Any], coverage: dict[str, Any]) -> int:
    sources = overview.get("sources", [])
    require(len(sources) >= 4, "Public source catalog is incomplete")
    source_ids = [source.get("id") for source in sources]
    require(len(source_ids) == len(set(source_ids)), "Public source catalog contains duplicate IDs")
    require({source.get("branch") for source in sources} == {"Executive", "Judicial", "Legislative"}, "Source catalog is missing a branch")
    for source in sources:
        source_id = source.get("id", "unknown")
        require_https_url(source.get("source_url"), f"Source {source_id}")
        require(source.get("access_mode"), f"Source {source_id} lacks an access mode")
        require(source.get("ingestion_status"), f"Source {source_id} lacks ingestion status")
        require(source.get("records_scope"), f"Source {source_id} lacks a records scope")
        require(source.get("rights_note"), f"Source {source_id} lacks its access/use notice")
        requirements = source.get("provenance_requirements", [])
        require(len(requirements) >= 3 and all(requirements), f"Source {source_id} lacks provenance requirements")
        readiness = source.get("readiness", {})
        require(readiness.get("status") and readiness.get("label"), f"Source {source_id} lacks readiness metadata")

    coverage_sources = coverage.get("sources", [])
    require({source.get("id") for source in coverage_sources} == set(source_ids), "Coverage and overview source catalogs differ")
    overview_by_id = {source["id"]: source for source in sources}
    for source in coverage_sources:
        canonical = overview_by_id[source["id"]]
        require(source.get("branch") == canonical.get("branch"), f"Coverage branch differs for {source['id']}")
        require(source.get("ingestion_status") == canonical.get("ingestion_status"), f"Coverage status differs for {source['id']}")
        require(source.get("readiness") == canonical.get("readiness"), f"Coverage readiness differs for {source['id']}")
    return len(sources)


def validate_role_partitions(
    manifest: dict[str, Any],
    validated_paths: dict[tuple[str, str], Path],
    official_ids: set[str],
) -> int:
    role_count = 0
    records = manifest.get("partitions", {}).get("roles", {})
    require(set(records) == {"Executive", "Judicial", "Legislative"}, "Role partitions must cover all branches")
    seen_officials: set[str] = set()
    for branch in sorted(records):
        payload = read_json(validated_paths[("roles", branch)])
        require(payload.get("schema_version") == EXPECTED_PARTITION_SCHEMAS["roles"], f"Wrong role schema for {branch}")
        require(payload.get("branch") == branch, f"Role partition branch mismatch for {branch}")
        roles_by_official = payload.get("roles_by_official", {})
        require(not (set(roles_by_official) - official_ids), f"Unknown official in {branch} role partition")
        require(not (seen_officials & set(roles_by_official)), f"Official appears in multiple role partitions: {branch}")
        seen_officials.update(roles_by_official)
        for official_id, roles in roles_by_official.items():
            require(roles, f"{official_id} has an empty role list")
            role_ids = [role.get("id") for role in roles]
            require(len(role_ids) == len(set(role_ids)), f"{official_id} has duplicate role IDs")
            for role in roles:
                require_https_url(role.get("source_url"), f"Role source for {official_id}")
                require(role.get("source_id") and role.get("source_tier"), f"Role provenance is incomplete for {official_id}")
                require_iso_date(role.get("service_start"), f"Role start for {official_id}")
                if role.get("service_end"):
                    require_iso_date(role["service_end"], f"Role end for {official_id}")
                    require(role["service_start"] <= role["service_end"], f"Inverted role dates for {official_id}")
            role_count += len(roles)
    require(seen_officials == official_ids, "Role partitions and official index differ")
    return role_count


def validate_market_partitions(
    manifest: dict[str, Any],
    validated_paths: dict[tuple[str, str], Path],
) -> int:
    point_count = 0
    for symbol in sorted(manifest.get("partitions", {}).get("market", {})):
        payload = read_json(validated_paths[("market", symbol)])
        require(payload.get("symbol") == symbol, f"Market symbol mismatch for {symbol}")
        source = payload.get("source")
        if isinstance(source, dict):
            require_https_url(source.get("url"), f"Market source for {symbol}")
            require(source.get("source_tier") == "market_data_provider", f"Market source tier is missing for {symbol}")
        else:
            require(source, f"Market source is missing for {symbol}")
            require_https_url(payload.get("source_url"), f"Market source for {symbol}")
        points = payload.get("points", [])
        require(points, f"Market partition is empty for {symbol}")
        dates = [point.get("date") for point in points]
        require(all(isinstance(value, str) for value in dates), f"Market dates are missing for {symbol}")
        require(dates == sorted(dates) and len(dates) == len(set(dates)), f"Market dates are not unique and sorted for {symbol}")
        require(all(point.get("symbol") == symbol for point in points), f"Market point symbol mismatch for {symbol}")
        require(all(isinstance(point.get("close"), (int, float)) for point in points), f"Market close is missing for {symbol}")
        point_count += len(points)
    return point_count


def validate_event_partitions(
    manifest: dict[str, Any],
    validated_paths: dict[tuple[str, str], Path],
    event_index: dict[str, dict[str, Any]],
) -> int:
    seen: set[str] = set()
    for year in sorted(manifest.get("partitions", {}).get("events", {})):
        payload = read_json(validated_paths[("events", year)])
        require(
            payload.get("schema_version") == EXPECTED_PARTITION_SCHEMAS["events"],
            f"Wrong event partition schema for {year}",
        )
        require(str(payload.get("year")) == year, f"Event partition year mismatch for {year}")
        for event in payload.get("events", []):
            event_id = event.get("id")
            require(event_id in event_index, f"Event partition contains unknown event: {event_id}")
            require(event_id not in seen, f"Event appears in multiple year partitions: {event_id}")
            require(str(event.get("date", ""))[:4] == year, f"Event stored in wrong year: {event_id}")
            require(event.get("source_urls"), f"Event source URLs are missing: {event_id}")
            for source_url in event.get("source_urls", []):
                require_https_url(source_url, f"Event source for {event_id}")
            seen.add(event_id)
    require(seen == set(event_index), "Event index and year partitions differ")
    return len(seen)


def validate_periods(official_id: str, periods: list[dict[str, Any]]) -> None:
    require(periods, f"{official_id} has no service period")
    prior_end = None
    prior_career_end = -1
    for period in periods:
        require(period["start"] <= period["end"], f"{official_id} has an inverted service period")
        require(
            period["career_start_day"] == prior_career_end + 1,
            f"{official_id} career periods are not cumulative",
        )
        require(period["career_end_day"] >= period["career_start_day"], f"{official_id} has invalid career days")
        if prior_end is not None:
            require(period["start"] > prior_end, f"{official_id} service periods overlap or are unsorted")
        prior_end = period["end"]
        prior_career_end = period["career_end_day"]


def date_in_period(value: str, periods: list[dict[str, Any]]) -> bool:
    return any(period["start"] <= value <= period["end"] for period in periods)


def validate_timeline(official_id: str, path: Path, event_catalog: dict[str, dict[str, Any]]) -> tuple[int, int]:
    payload = read_json(path)
    require(payload.get("schema_version") == "career-trade-timeline-v3", f"Wrong timeline schema for {official_id}")
    official = payload.get("official", {})
    require(official.get("id") == official_id, f"Timeline key does not match payload for {official_id}")
    periods = official.get("service_periods", [])
    validate_periods(official_id, periods)
    expected_days = periods[-1]["career_end_day"] + 1
    require(official.get("active_service_days") == expected_days, f"Wrong active service day count for {official_id}")

    production_count = 0
    documents_by_id = {
        document["document_id"]: document
        for document in official.get("disclosure_documents", [])
        if document.get("document_id")
    }
    trade_defaults = official.get("trade_record_defaults", {})
    for compact_trade in official.get("trades", []):
        trade = {**trade_defaults, **compact_trade}
        require(date_in_period(trade["date"], periods), f"Trade outside service periods for {official_id}: {trade['date']}")
        require(isinstance(trade.get("career_day"), int), f"Trade without career day for {official_id}")
        require(0 <= trade["career_day"] < expected_days, f"Trade career day out of range for {official_id}")
        source_url = trade.get("source_url") or documents_by_id.get(
            trade.get("document_id"), {}
        ).get("source_url", "")
        if trade.get("record_status") != "fixture_demo":
            require(source_url.startswith("https://"), f"Trade without HTTPS source for {official_id}")
        if trade.get("public_production_trade") is True:
            production_count += 1
            require("fixture" not in trade.get("record_status", ""), f"Fixture leaked into production for {official_id}")

    for event in official.get("events", []):
        catalog_event = event_catalog.get(event["id"])
        require(catalog_event is not None, f"Unknown event relationship for {official_id}: {event['id']}")
        require(event["date"] == catalog_event["date"], f"Event relationship date mismatch for {official_id}")
        require(date_in_period(event["date"], periods), f"Event outside service periods for {official_id}: {event['date']}")
        require(isinstance(event.get("career_day"), int), f"Event without career day for {official_id}")
        require(event.get("relationship_tier") in {
            "direct",
            "asset_specific",
            "jurisdictional",
            "institutional",
            "sector_context",
            "general_macro",
            "general_context",
        }, f"Unknown relationship tier for {official_id}")
        if event.get("trade_context_candidate"):
            require(
                event.get("trade_context_methodology") == "trade-window-v3",
                f"Wrong context methodology for {official_id}",
            )
            require(
                isinstance(event.get("candidate_rank"), int)
                and isinstance(event.get("candidate_score"), (int, float)),
                f"Context candidate lacks a transparent rank for {official_id}",
            )
            require(
                bool(event.get("candidate_score_components")),
                f"Context candidate lacks score components for {official_id}",
            )
            if event["candidate_rank"] <= 24:
                require(
                    event.get("display_default") is True,
                    f"Top-ranked context candidate hidden by default for {official_id}",
                )
            require(
                isinstance(event.get("nearest_trade_days"), int)
                and abs(event["nearest_trade_days"]) <= 45,
                f"Context candidate outside trade window for {official_id}",
            )
            require(event.get("nearby_trade_ids"), f"Context candidate has no linked trades for {official_id}")
        elif event.get("relationship_tier") == "general_macro":
            require(event.get("display_default") is False, f"Unlinked macro event defaults on for {official_id}")

    return len(official.get("trades", [])), production_count


def validate_house_archive() -> dict[str, int]:
    index = read_json(HOUSE_INDEX)
    manifest = read_json(HOUSE_TRANSACTIONS)
    require(index.get("schema_version") == "house-disclosure-index-v1", "Unexpected House index schema")
    require(
        manifest.get("schema_version") == "house-ptr-transactions-manifest-v2",
        "Unexpected House transaction manifest schema",
    )
    require(index.get("summary", {}).get("member_ptr_document_count", 0) >= 7_500, "House PTR index is incomplete")
    require(index.get("summary", {}).get("matched_member_ptr_document_count", 0) >= 7_500, "House roster matching regressed")

    documents = []
    transactions = []
    for year, record in manifest.get("year_partitions", {}).items():
        path = ROOT / record["path"]
        require(path.is_file(), f"Missing House year partition: {year}")
        encoded = path.read_bytes()
        require(len(encoded) == record["bytes"], f"House year byte count mismatch: {year}")
        require(hashlib.sha256(encoded).hexdigest() == record["sha256"], f"House year hash mismatch: {year}")
        require(len(encoded) <= 20_000_000, f"House year partition exceeds 20 MB: {year}")
        payload = json.loads(encoded)
        require(payload.get("filing_year") == int(year), f"House year metadata mismatch: {year}")
        documents.extend(payload.get("documents", []))
        transactions.extend(payload.get("transactions", []))

    document_ids = [document["document_id"] for document in documents]
    transaction_ids = [transaction["id"] for transaction in transactions]
    require(len(document_ids) == len(set(document_ids)), "House archive contains duplicate document IDs")
    require(len(transaction_ids) == len(set(transaction_ids)), "House archive contains duplicate transaction IDs")
    require(len(documents) == manifest["summary"]["processed_document_count"], "House document count does not reconcile")
    require(
        len(transactions) == manifest["summary"]["parser_preview_transaction_count"],
        "House transaction count does not reconcile",
    )
    require(not [document for document in documents if document.get("parser_status") == "error"], "House archive has parser errors")
    for transaction in transactions:
        require(transaction.get("source_url", "").startswith("https://"), "House transaction lacks official HTTPS source")
        require(transaction.get("source_tier") == "official", "House transaction source tier regressed")
        require(transaction.get("public_production_trade") is False, "Unreviewed House transaction entered production")
        require(transaction.get("review_required_before_public_trade") is True, "House review gate is missing")
        require(transaction.get("disclosure_lag_days", -1) >= 0, "House transaction has a negative disclosure lag")
        require(transaction.get("value_range_min") is not None, "House transaction has an unbounded minimum")

    return {"documents": len(documents), "transactions": len(transactions)}


def validate_senate_archive() -> dict[str, int]:
    index = read_json(SENATE_INDEX)
    archive = read_json(SENATE_TRANSACTIONS)
    require(
        index.get("schema_version") == "senate-disclosure-index-v1",
        "Unexpected Senate index schema",
    )
    require(
        archive.get("schema_version") == "senate-ptr-transactions-v1",
        "Unexpected Senate transaction schema",
    )
    require(
        index.get("summary", {}).get("document_count", 0) >= 2_100,
        "Senate PTR index is incomplete",
    )
    require(
        index.get("summary", {}).get("matched_document_count", 0) >= 1_800,
        "Senate roster matching regressed",
    )
    documents = archive.get("documents", [])
    transactions = archive.get("transactions", [])
    require(len(documents) >= 1_800, "Senate matched PTR acquisition is incomplete")
    require(
        len(documents) == archive.get("summary", {}).get("processed_document_count"),
        "Senate document count does not reconcile",
    )
    require(
        len(transactions) == archive.get("summary", {}).get("parser_preview_transaction_count"),
        "Senate transaction count does not reconcile",
    )
    require(
        len({document["document_id"] for document in documents}) == len(documents),
        "Senate archive contains duplicate document IDs",
    )
    require(
        len({transaction["id"] for transaction in transactions}) == len(transactions),
        "Senate archive contains duplicate transaction IDs",
    )
    for transaction in transactions:
        require(
            transaction.get("source_url", "").startswith("https://efdsearch.senate.gov/"),
            "Senate transaction lacks an official portal source",
        )
        require(transaction.get("source_tier") == "official", "Senate source tier regressed")
        require(
            transaction.get("review_required_before_public_trade") is True,
            "Senate review gate is missing",
        )
        require(
            transaction.get("public_production_trade") is False,
            "Unreviewed Senate transaction entered production",
        )
    return {"documents": len(documents), "transactions": len(transactions)}


def validate() -> dict[str, int | float]:
    house_summary = validate_house_archive()
    senate_summary = validate_senate_archive()
    manifest = read_json(MANIFEST)
    require(
        set(manifest) == {
            "dataset_version",
            "event_relationship_methodology_version",
            "files",
            "generated_at",
            "methodology_version",
            "partitions",
            "schema_version",
        },
        "Unexpected public manifest fields",
    )
    require(manifest.get("schema_version") == "civicledger-public-manifest-v1", "Unexpected public manifest schema")
    require(manifest.get("event_relationship_methodology_version") == "event-relevance-v4", "Unexpected event methodology")
    require(manifest.get("dataset_version") and manifest.get("methodology_version"), "Manifest version metadata is incomplete")
    require_iso_date(manifest.get("generated_at"), "Manifest generation date")
    require(
        set(manifest.get("files", {})) == set(INITIAL_PAYLOAD_LIMITS) | set(AUXILIARY_FILE_LIMITS),
        "Manifest public-file set changed",
    )
    require(set(manifest.get("partitions", {})) == set(PARTITION_LIMITS), "Manifest partition groups changed")

    seen_paths: set[str] = set()
    validated_paths: dict[tuple[str, str], Path] = {}
    for group, name, record in iter_records(manifest):
        require(record.get("path") not in seen_paths, f"Duplicate manifest path: {record.get('path')}")
        seen_paths.add(record.get("path"))
        validated_paths[(group, name)] = validate_record(group, name, record)

    actual_partition_paths = {
        path.relative_to(PUBLIC_DATA).as_posix()
        for path in (PUBLIC_DATA / "partitions").rglob("*.json")
    }
    require(actual_partition_paths == seen_paths, "Manifest and generated partition files differ")

    for name, expected_schema in EXPECTED_FILE_SCHEMAS.items():
        payload = read_json(validated_paths[("files", name)])
        require(payload.get("schema_version") == expected_schema, f"Unexpected schema for {name}")

    for name, limit in INITIAL_PAYLOAD_LIMITS.items():
        record = manifest["files"].get(name)
        require(record is not None, f"Missing initial payload entry: {name}")
        require(record["bytes"] <= limit, f"Initial payload {name} exceeds {limit:,} bytes")
    for name, limit in AUXILIARY_FILE_LIMITS.items():
        record = manifest["files"].get(name)
        require(record is not None and record["bytes"] <= limit, f"Auxiliary payload {name} exceeds {limit:,} bytes")
    require(
        sum(manifest["files"][name]["bytes"] for name in INITIAL_PAYLOAD_LIMITS) <= 4_750_000,
        "Combined initial public payload exceeds 4,750,000 bytes",
    )
    for group, limit in PARTITION_LIMITS.items():
        for name, record in manifest["partitions"].get(group, {}).items():
            require(record["bytes"] <= limit, f"{group} partition {name} exceeds {limit:,} bytes")

    coverage = read_json(validated_paths[("files", "coverage")])
    scope = coverage.get("historical_scope", {})
    require(scope.get("start_date") == "2009-01-20", "Historical scope must begin with the Obama administration")
    require(scope.get("congresses") == list(range(111, 120)), "Congressional scope must cover the 111th-119th Congresses")
    require(
        scope.get("presidential_terms") == ["obama-44", "trump-45", "biden-46", "trump-47"],
        "Presidential term scope is incomplete",
    )

    official_index = read_json(validated_paths[("files", "officials_index")])
    officials = official_index.get("officials", [])
    ids = [official.get("id") for official in officials]
    require(len(ids) == len(set(ids)), "Official index contains duplicate IDs")
    require(len(ids) >= 2_000, "Official index is unexpectedly small")
    require({official.get("branch") for official in officials} == {"Executive", "Judicial", "Legislative"}, "Official index is missing a branch")
    official_ids = set(ids)

    overview = read_json(validated_paths[("files", "overview")])
    require(overview.get("dataset_version") == manifest["dataset_version"], "Overview and manifest dataset versions differ")
    require(overview.get("methodology_version") == manifest["methodology_version"], "Overview and manifest methodology versions differ")
    require(overview.get("generated_at") == manifest["generated_at"], "Overview and manifest generation dates differ")
    ranking_benchmark = overview.get("event_ranking_benchmark", {})
    ranking_metrics = ranking_benchmark.get("metrics", {})
    require(
        ranking_benchmark.get("schema_version") == "trade-event-ranking-benchmark-v1",
        "Trade-event ranking benchmark is missing or has the wrong schema",
    )
    require(
        ranking_benchmark.get("methodology_version") == "trade-window-v3",
        "Trade-event ranking benchmark methodology is stale",
    )
    require(ranking_metrics.get("case_count", 0) >= 7, "Trade-event ranking benchmark is too small")
    require(ranking_metrics.get("precision", 0) >= 0.7, "Trade-event ranking precision regressed")
    require(ranking_metrics.get("recall", 0) >= 0.9, "Trade-event ranking recall regressed")
    disclosure_pipeline = overview.get("disclosure_pipeline", {})
    ocr_summary = disclosure_pipeline.get("ocr_priority_batches", {}).get("summary", {})
    amendment_summary = disclosure_pipeline.get("amendment_reconciliation", {}).get("summary", {})
    require(ocr_summary.get("backlog_document_count", 0) >= 2_500, "OCR backlog priorities are missing")
    require(ocr_summary.get("ocr_content_record_count") == 0, "Metadata-only OCR batching generated content")
    require(ocr_summary.get("transaction_rows_created") == 0, "OCR batching created unsupported trades")
    require(
        amendment_summary.get("destructive_change_count") == 0,
        "Amendment reconciliation performed a destructive change",
    )
    require(
        overview.get("sec_issuer_aliases", {}).get("summary", {}).get("supported_ticker_count", 0)
        >= 300,
        "SEC-backed issuer alias coverage regressed",
    )
    require(
        overview.get("sec_filing_context", {}).get("summary", {}).get("event_count", 0) >= 600,
        "SEC filing context coverage regressed",
    )
    require(
        overview.get("primary_source_context", {}).get("summary", {}).get("record_count", 0)
        >= 1_800,
        "Official primary-source context coverage regressed",
    )
    source_count = validate_source_catalog(overview, coverage)
    role_count = validate_role_partitions(manifest, validated_paths, official_ids)

    timeline_index = read_json(validated_paths[("files", "timeline_index")])
    default_ids = set(timeline_index.get("default_official_ids", []))
    require(default_ids == {"exec:barack-obama", "exec:donald-j-trump", "exec:joseph-r-biden"}, "Presidential baseline changed")
    require(all("vice" not in official_id for official_id in default_ids), "Vice president entered the baseline")

    timeline_records = manifest.get("partitions", {}).get("timelines", {})
    require(set(timeline_records) == {row["id"] for row in timeline_index.get("officials", [])}, "Timeline index and partitions differ")
    trade_count = 0
    production_count = 0
    events_payload = read_json(validated_paths[("files", "events")])
    event_catalog = {event["id"]: event for event in events_payload.get("events", [])}
    require(len(event_catalog) == len(events_payload.get("events", [])), "Event catalog contains duplicate IDs")
    for event in event_catalog.values():
        require_iso_date(event.get("date"), f"Event date for {event.get('id', 'unknown')}")
        require(event.get("label") and event.get("event_type"), f"Event metadata is incomplete: {event.get('id')}")
        require(event.get("source"), f"Event source is missing: {event.get('id')}")
        if event.get("editor_status") in {"curated", "source_ingested"}:
            require(event.get("source_tier"), f"Official event source tier is missing: {event.get('id')}")
    event_count = validate_event_partitions(manifest, validated_paths, event_catalog)
    for official_id, record in timeline_records.items():
        path = validated_paths[("timelines", official_id)]
        timeline_trades, timeline_production = validate_timeline(official_id, path, event_catalog)
        trade_count += timeline_trades
        production_count += timeline_production

    expected_trade_count = timeline_index.get("summary", {}).get("trade_count")
    require(trade_count == expected_trade_count, "Timeline summary trade count does not reconcile")
    expected_production = timeline_index.get("summary", {}).get("presidential_oge_public_production_trade_count", 0)
    require(production_count == expected_production, "Production trade count does not reconcile")

    market_index = read_json(validated_paths[("files", "market_index")])
    market_records = manifest.get("partitions", {}).get("market", {})
    require(set(market_index.get("symbols", [])) == set(market_records), "Market index and partitions differ")
    require({"SPY", "QQQ", "BTCUSD", "ETHUSD"} <= set(market_records), "Core market or crypto overlays are missing")
    market_point_count = validate_market_partitions(manifest, validated_paths)

    return {
        "manifest_records": len(seen_paths),
        "officials": len(officials),
        "timelines": len(timeline_records),
        "trades": trade_count,
        "production_trades": production_count,
        "market_symbols": len(market_records),
        "market_points": market_point_count,
        "roles": role_count,
        "sources": source_count,
        "events": event_count,
        "house_documents": house_summary["documents"],
        "house_transactions": house_summary["transactions"],
        "senate_documents": senate_summary["documents"],
        "senate_transactions": senate_summary["transactions"],
        "ranking_precision": ranking_metrics["precision"],
        "ranking_recall": ranking_metrics["recall"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the validation summary as JSON.")
    args = parser.parse_args()
    try:
        summary = validate()
    except ValidationError as exc:
        raise SystemExit(f"Public release validation failed: {exc}") from exc
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            "Public release validation passed: "
            + ", ".join(f"{key}={value}" for key, value in summary.items())
        )


if __name__ == "__main__":
    main()
