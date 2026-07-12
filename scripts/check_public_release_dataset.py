#!/usr/bin/env python3
"""Validate the static public release contract and provenance boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


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
    "events": 1_200_000,
    "timeline_index": 200_000,
    "market_index": 100_000,
}
PARTITION_LIMITS = {
    "timelines": 5_000_000,
    "roles": 8_000_000,
    "market": 5_000_000,
}


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


def iter_records(manifest: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for name, record in manifest.get("files", {}).items():
        yield "files", name, record
    for group, records in manifest.get("partitions", {}).items():
        for name, record in records.items():
            yield group, name, record


def validate_record(group: str, name: str, record: dict[str, Any]) -> Path:
    require(set(record) == {"path", "bytes", "sha256"}, f"Unexpected manifest fields for {group}.{name}")
    relative_path = Path(record["path"])
    require(not relative_path.is_absolute() and ".." not in relative_path.parts, f"Unsafe path for {group}.{name}")
    path = PUBLIC_DATA / relative_path
    require(path.is_file(), f"Missing public partition: {relative_path}")
    encoded = path.read_bytes()
    require(len(encoded) == record["bytes"], f"Byte count mismatch for {relative_path}")
    require(hashlib.sha256(encoded).hexdigest() == record["sha256"], f"Hash mismatch for {relative_path}")
    return path


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
                event.get("trade_context_methodology") == "trade-window-v2",
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


def validate() -> dict[str, int]:
    house_summary = validate_house_archive()
    senate_summary = validate_senate_archive()
    manifest = read_json(MANIFEST)
    require(manifest.get("schema_version") == "civicledger-public-manifest-v1", "Unexpected public manifest schema")
    require(manifest.get("event_relationship_methodology_version") == "event-relevance-v4", "Unexpected event methodology")

    seen_paths: set[str] = set()
    validated_paths: dict[tuple[str, str], Path] = {}
    for group, name, record in iter_records(manifest):
        require(record.get("path") not in seen_paths, f"Duplicate manifest path: {record.get('path')}")
        seen_paths.add(record.get("path"))
        validated_paths[(group, name)] = validate_record(group, name, record)

    for name, limit in INITIAL_PAYLOAD_LIMITS.items():
        record = manifest["files"].get(name)
        require(record is not None, f"Missing initial payload entry: {name}")
        require(record["bytes"] <= limit, f"Initial payload {name} exceeds {limit:,} bytes")
    require(
        sum(manifest["files"][name]["bytes"] for name in INITIAL_PAYLOAD_LIMITS) <= 4_000_000,
        "Combined initial public payload exceeds 4,000,000 bytes",
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
        if event.get("editor_status") in {"curated", "source_ingested"}:
            require(
                any((source_url or "").startswith("https://") for source_url in event.get("source_urls", [])),
                f"Official event lacks an HTTPS source: {event['id']}",
            )
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

    return {
        "manifest_records": len(seen_paths),
        "officials": len(officials),
        "timelines": len(timeline_records),
        "trades": trade_count,
        "production_trades": production_count,
        "market_symbols": len(market_records),
        "house_documents": house_summary["documents"],
        "house_transactions": house_summary["transactions"],
        "senate_documents": senate_summary["documents"],
        "senate_transactions": senate_summary["transactions"],
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
