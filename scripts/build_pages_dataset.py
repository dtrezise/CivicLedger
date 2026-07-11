#!/usr/bin/env python3
"""Build the static data snapshot used by the GitHub Pages edition."""

from __future__ import annotations

import json
import hashlib
import random
import re
import shutil
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.config import settings
from app.seed import (
    FIXTURES,
    create_filings_and_trades,
    create_people,
    generate_market_series,
    source_id_for_person,
)
from app.services.official_sources import OFFICIAL_SOURCES
from app.services.market_prices import crypto_reference, normalize_asset_symbol, ticker_reference


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "pages-site" / "data" / "civicledger-static.json"
PUBLIC_MANIFEST = ROOT / "pages-site" / "data" / "manifest.json"
PUBLIC_PARTITIONS = ROOT / "pages-site" / "data" / "partitions"
PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
FRED_CONTEXT = ROOT / "data" / "context" / "fred_market_context.json"
MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"
CRYPTO_PRICES = ROOT / "data" / "context" / "crypto_prices.json"
CURATED_TIMELINE_EVENTS = ROOT / "data" / "context" / "timeline_events.json"
FEDERAL_EVENTS = ROOT / "data" / "context" / "federal_events.json"
EVENT_ENTITY_MAP = ROOT / "data" / "context" / "event_entity_map.json"
CONGRESS_JURISDICTION_MAP = ROOT / "data" / "context" / "congress_jurisdiction_map.json"
BRANCH_JURISDICTION_MAP = ROOT / "data" / "context" / "branch_jurisdiction_map.json"
COMPANY_ENTITY_REFERENCE = ROOT / "data" / "context" / "company_entity_reference.json"
PRESIDENTIAL_OGE_STATUS = ROOT / "data" / "disclosures" / "presidential_oge_disclosure_status.json"
PRESIDENTIAL_OGE_DOCUMENTS = ROOT / "data" / "disclosures" / "presidential_oge_documents.json"
PRESIDENTIAL_OGE_TRANSACTIONS = ROOT / "data" / "disclosures" / "presidential_oge_transactions.json"
HOUSE_DISCLOSURE_INDEX = ROOT / "data" / "disclosures" / "house_disclosure_index.json"
HOUSE_PTR_TRANSACTIONS = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
DISCLOSURE_QUEUE = ROOT / "data" / "disclosures" / "disclosure_ingestion_queue.json"
RAW_ARCHIVE_INDEX = ROOT / "data" / "disclosures" / "raw_document_archive_index.json"
REVIEWED_PROMOTIONS = ROOT / "data" / "disclosures" / "reviewed_disclosure_promotions.json"
PRODUCTION_PROMOTIONS = ROOT / "data" / "disclosures" / "production_trade_promotions.json"
RETRIEVAL_BATCHES = ROOT / "data" / "disclosures" / "disclosure_retrieval_batches.json"
SOURCE_STALENESS_ALERTS = ROOT / "data" / "disclosures" / "source_staleness_alerts.json"
DISCLOSURE_COMPLETENESS = ROOT / "data" / "disclosures" / "disclosure_completeness_dashboard.json"
MARKET_SYMBOLS = ["SPY", "QQQ", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI"]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def number(value) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def public_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()


def median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2)


def grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def scorecard(branch: str, filing_count: int, trades: list[dict]) -> dict:
    elevated, high = {
        "Legislative": (45, 90),
        "Executive": (60, 120),
        "Judicial": (60, 120),
    }.get(branch, (45, 90))
    lags = [trade["disclosure_lag_days"] for trade in trades]
    median_lag = median(lags)
    score = 100
    deductions = []
    if filing_count == 0:
        score -= 30
        deductions.append("No filings found")
    if median_lag is not None and median_lag > high:
        score -= 25
        deductions.append(f"Median lag above {high} days")
    elif median_lag is not None and median_lag > elevated:
        score -= 15
        deductions.append(f"Median lag above {elevated} days")
    low_confidence = [
        trade for trade in trades if trade.get("parsing_confidence") is not None and trade["parsing_confidence"] < 0.5
    ]
    if low_confidence:
        score -= 10
        deductions.append("Low parser confidence records")
    score = max(0, min(100, score))
    return {
        "score": score,
        "grade": grade(score),
        "median_lag_days": median_lag,
        "deductions": deductions,
        "thresholds": {"elevated_lag_days": elevated, "high_lag_days": high},
    }


def value_midpoint(trade: dict) -> float | None:
    minimum = trade.get("value_range_min")
    maximum = trade.get("value_range_max")
    if minimum is None or maximum is None:
        return None
    return round((float(minimum) + float(maximum)) / 2, 2)


def asset_reference(symbol: str | None, asset_class: str | None = None) -> dict:
    normalized = normalize_asset_symbol(symbol)
    reference = crypto_reference(normalized) if asset_class == "crypto" else ticker_reference(normalized)
    if reference:
        return reference
    return {
        "symbol": normalized,
        "issuer_name": normalized or "Unmapped asset",
        "asset_class": asset_class or "unknown",
        "sector": "Unmapped",
        "benchmark_symbol": "SPY",
    }


def generate_fixture_market_series() -> list[dict]:
    seed_points = generate_market_series()
    by_date = defaultdict(dict)
    for point in seed_points:
        by_date[point.date][point.symbol] = float(point.value)

    baselines = {
        "QQQ": 270.0,
        "XLK": 126.0,
        "XLF": 34.0,
        "XLE": 85.0,
        "XLV": 134.0,
        "XLI": 98.0,
    }
    drift = {
        "QQQ": 0.00055,
        "XLK": 0.00062,
        "XLF": 0.00032,
        "XLE": 0.00018,
        "XLV": 0.00028,
        "XLI": 0.00036,
    }
    volatility = {
        "QQQ": 0.015,
        "XLK": 0.016,
        "XLF": 0.012,
        "XLE": 0.017,
        "XLV": 0.009,
        "XLI": 0.011,
    }
    prices = baselines.copy()
    rows = []
    for day in sorted(by_date):
        rows.append({"symbol": "SPY", "date": day, "value": by_date[day]["SPY"], "source": "fixture_market"})
        rows.append({"symbol": "DIA", "date": day, "value": by_date[day]["DIA"], "source": "fixture_market"})
        for symbol in baselines:
            prices[symbol] *= 1 + random.gauss(drift[symbol], volatility[symbol])
            rows.append({"symbol": symbol, "date": day, "value": round(prices[symbol], 2), "source": "fixture_market"})
    return rows


def load_market_prices() -> tuple[list[dict], dict]:
    if not MARKET_PRICES.exists():
        return generate_fixture_market_series(), {
            "provider": "fixture",
            "context_label": "Market overlays are fixture data in this public demo.",
            "summary": {"active_market_price_provider": "fixture", "price_point_count": 0},
        }
    data = json.loads(MARKET_PRICES.read_text())
    rows = []
    for symbol, series in data.get("series", {}).items():
        for point in series.get("points", []):
            value = point.get("adj_close") if point.get("adj_close") is not None else point.get("close")
            if value is None:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "date": parse_iso_date(point["date"]),
                    "value": value,
                    "source": "tiingo",
                }
            )
    return rows, {
        "provider": data.get("source", {}).get("id", "tiingo-eod"),
        "context_label": data.get("context_label", "Market overlays use production market-price data."),
        "summary": data.get("summary", {}),
        "source": data.get("source", {}),
        "ticker_reference": data.get("ticker_reference", {}),
        "coverage_report": data.get("coverage_report", {}),
        "anomaly_report": data.get("anomaly_report", []),
    }


def load_crypto_prices() -> dict:
    if not CRYPTO_PRICES.exists():
        return {
            "provider": "not_configured",
            "context_label": "Crypto price overlays are not refreshed in this snapshot.",
            "summary": {"active_crypto_price_provider": "not_configured", "price_point_count": 0},
            "source": {},
            "crypto_reference": {},
            "coverage_report": {},
            "series": {},
        }
    data = json.loads(CRYPTO_PRICES.read_text())
    return {
        "provider": data.get("source", {}).get("id", "tiingo-crypto"),
        "context_label": data.get("context_label", "Crypto overlays use production crypto price data."),
        "summary": data.get("summary", {}),
        "source": data.get("source", {}),
        "crypto_reference": data.get("crypto_reference", {}),
        "coverage_report": data.get("coverage_report", {}),
        "series": data.get("series", {}),
    }


def crypto_price_window(symbol: str | None, trade_date: str | None, points_by_symbol: dict[str, list[dict]]) -> dict | None:
    if not symbol or not trade_date:
        return None
    points = points_by_symbol.get(normalize_asset_symbol(symbol), [])
    if not points:
        return None
    trade_day = parse_iso_date(trade_date)
    rows = []
    for point in points:
        point_day = parse_iso_date(point["date"])
        if abs((point_day - trade_day).days) <= 7:
            rows.append(
                {
                    "date": point["date"],
                    "close": point.get("close"),
                    "days_from_trade": (point_day - trade_day).days,
                    "source": point.get("source", "tiingo_crypto"),
                }
            )
    if not rows:
        return None
    closest = sorted(rows, key=lambda row: (abs(row["days_from_trade"]), row["date"]))[0]
    return {
        "provider": "Tiingo Crypto",
        "window_days": 7,
        "closest_close": closest.get("close"),
        "closest_date": closest["date"],
        "points": sorted(rows, key=lambda row: row["date"]),
    }


def market_snapshot(series: list[dict], metadata: dict) -> dict:
    monthly = defaultdict(dict)
    for point in series:
        month = point["date"].strftime("%Y-%m")
        monthly[month][point["symbol"]] = float(point["value"])
    return {
        "symbols": MARKET_SYMBOLS,
        "provider": metadata["provider"],
        "context_label": metadata["context_label"],
        "summary": metadata["summary"],
        "source": metadata.get("source", {}),
        "coverage_report": metadata.get("coverage_report", {}),
        "anomaly_report": metadata.get("anomaly_report", []),
        "monthly": [
            {"month": month, **values}
            for month, values in sorted(monthly.items())
            if all(symbol in values for symbol in MARKET_SYMBOLS)
        ]
    }


def load_events() -> list[dict]:
    curated = load_json_file(CURATED_TIMELINE_EVENTS, {"events": []}).get("events", [])
    federal = load_json_file(FEDERAL_EVENTS, {"events": []}).get("events", [])
    rows = []
    seen_ids = set()
    seen_primary_urls = set()
    for event in [*curated, *federal]:
        event_id = event.get("id")
        primary_url = next(iter(event.get("sources", [])), None)
        if event_id and event_id in seen_ids:
            continue
        if primary_url and primary_url in seen_primary_urls:
            continue
        rows.append(event)
        if event_id:
            seen_ids.add(event_id)
        if primary_url:
            seen_primary_urls.add(primary_url)
    return rows


def load_json_file(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text())


def load_event_entity_map() -> dict:
    return load_json_file(
        EVENT_ENTITY_MAP,
        {
            "schema_version": "event-entity-map-v1",
            "context_label": "Event-to-entity mappings have not been generated.",
            "default_ticker_scope": ["SPY", "QQQ", "DIA"],
            "event_maps": [],
        },
    )


def event_mapping_for(event: dict, event_entity_map: dict) -> dict:
    label = event.get("label", "")
    lowered = label.lower()
    for mapping in event_entity_map.get("event_maps", []):
        labels = [item.lower() for item in mapping.get("match_labels", [])]
        if lowered in labels or any(item and item in lowered for item in labels):
            return mapping
    return {}


def company_entities_for_event(event: dict, company_reference: dict) -> list[dict]:
    text = " ".join(
        [
            event.get("label", ""),
            event.get("description", ""),
            " ".join(event.get("jurisdiction_scope", []) or []),
            " ".join(event.get("sector_scope", []) or []),
        ]
    ).lower()
    matches = []
    for entity in company_reference.get("entities", []):
        aliases = [str(alias).lower() for alias in entity.get("aliases", [])]
        if any(alias and alias in text for alias in aliases):
            matches.append(
                {
                    "entity_id": entity.get("entity_id"),
                    "issuer_name": entity.get("issuer_name"),
                    "ticker_scope": entity.get("ticker_scope", []),
                    "sector_scope": entity.get("sector_scope", []),
                }
            )
    return matches


def load_context_maps() -> dict:
    return {
        "event_entity_map": load_event_entity_map(),
        "congress_jurisdiction_map": load_json_file(
            CONGRESS_JURISDICTION_MAP,
            {"schema_version": "congress-jurisdiction-map-v1", "committee_maps": []},
        ),
        "branch_jurisdiction_map": load_json_file(
            BRANCH_JURISDICTION_MAP,
            {"schema_version": "branch-jurisdiction-map-v1", "executive_maps": [], "judicial_maps": []},
        ),
        "company_entity_reference": load_json_file(
            COMPANY_ENTITY_REFERENCE,
            {"schema_version": "company-entity-reference-v1", "entities": []},
        ),
    }


def load_disclosure_artifacts() -> dict:
    return {
        "ingestion_queue": load_json_file(
            DISCLOSURE_QUEUE,
            {"schema_version": "disclosure-ingestion-queue-v1", "summary": {}, "entries": []},
        ),
        "raw_archive_index": load_json_file(
            RAW_ARCHIVE_INDEX,
            {"schema_version": "raw-document-archive-index-v1", "summary": {}, "documents": []},
        ),
        "reviewed_promotions": load_json_file(
            REVIEWED_PROMOTIONS,
            {"schema_version": "reviewed-disclosure-promotions-v1", "summary": {}, "promotions": []},
        ),
        "production_promotions": load_json_file(
            PRODUCTION_PROMOTIONS,
            {"schema_version": "production-trade-promotions-v1", "summary": {}, "public_trade_rows": []},
        ),
        "retrieval_batches": load_json_file(
            RETRIEVAL_BATCHES,
            {"schema_version": "disclosure-retrieval-batches-v1", "summary": {}, "batches": []},
        ),
        "source_staleness_alerts": load_json_file(
            SOURCE_STALENESS_ALERTS,
            {"schema_version": "source-staleness-alerts-v1", "summary": {}, "alerts": []},
        ),
        "completeness_dashboard": load_json_file(
            DISCLOSURE_COMPLETENESS,
            {"schema_version": "disclosure-completeness-dashboard-v1", "summary": {}, "branches": [], "rows": []},
        ),
    }


def public_disclosure_artifacts(artifacts: dict) -> dict:
    queue = artifacts["ingestion_queue"]
    raw_archive = artifacts["raw_archive_index"]
    promotions = artifacts["reviewed_promotions"]
    return {
        "ingestion_queue": {
            "schema_version": queue.get("schema_version"),
            "context_label": queue.get("context_label"),
            "generated_at": queue.get("generated_at"),
            "summary": queue.get("summary", {}),
        },
        "raw_archive_index": {
            "schema_version": raw_archive.get("schema_version"),
            "context_label": raw_archive.get("context_label"),
            "generated_at": raw_archive.get("generated_at"),
            "summary": raw_archive.get("summary", {}),
            "documents": raw_archive.get("documents", []),
        },
        "reviewed_promotions": {
            "schema_version": promotions.get("schema_version"),
            "context_label": promotions.get("context_label"),
            "generated_at": promotions.get("generated_at"),
            "summary": promotions.get("summary", {}),
            "promotions": promotions.get("promotions", []),
        },
        "production_promotions": artifacts["production_promotions"],
        "retrieval_batches": artifacts["retrieval_batches"],
        "source_staleness_alerts": artifacts["source_staleness_alerts"],
        "completeness_dashboard": artifacts["completeness_dashboard"],
    }


def load_presidential_oge_status() -> dict:
    if not PRESIDENTIAL_OGE_STATUS.exists():
        return {
            "context_label": "Presidential OGE disclosure source status has not been generated.",
            "summary": {"official_status_count": 0, "reviewed_trade_count": 0},
            "officials": [],
            "source": {},
        }
    return json.loads(PRESIDENTIAL_OGE_STATUS.read_text())


def load_presidential_oge_documents() -> dict:
    if not PRESIDENTIAL_OGE_DOCUMENTS.exists():
        return {
            "context_label": "Presidential OGE disclosure documents have not been generated.",
            "summary": {
                "document_count": 0,
                "parser_preview_transaction_count": 0,
                "public_production_trade_count": 0,
            },
            "documents": [],
            "unavailable_documents": [],
            "source": {},
        }
    return json.loads(PRESIDENTIAL_OGE_DOCUMENTS.read_text())


def load_presidential_oge_transactions() -> dict:
    if not PRESIDENTIAL_OGE_TRANSACTIONS.exists():
        return {
            "context_label": "Presidential OGE parser-preview transactions have not been generated.",
            "summary": {
                "parser_preview_transaction_count": 0,
                "public_production_trade_count": 0,
                "review_required_transaction_count": 0,
            },
            "transactions": [],
        }
    return json.loads(PRESIDENTIAL_OGE_TRANSACTIONS.read_text())


def load_house_ptr_transactions() -> dict:
    if not HOUSE_PTR_TRANSACTIONS.exists():
        return {
            "manifest": {},
            "documents": [],
            "transactions": [],
            "summary": {"processed_document_count": 0, "parser_preview_transaction_count": 0},
        }
    manifest = json.loads(HOUSE_PTR_TRANSACTIONS.read_text())
    documents = []
    transactions = []
    if manifest.get("schema_version") == "house-ptr-transactions-manifest-v2":
        for record in manifest.get("year_partitions", {}).values():
            partition = json.loads((ROOT / record["path"]).read_text())
            documents.extend(partition.get("documents", []))
            transactions.extend(partition.get("transactions", []))
    else:
        documents = manifest.get("documents", [])
        transactions = manifest.get("transactions", [])
    return {
        "manifest": manifest,
        "documents": documents,
        "transactions": transactions,
        "summary": manifest.get("summary", {}),
    }


def load_public_officials() -> dict:
    if not PUBLIC_OFFICIALS.exists():
        return {
            "summary": {
                "person_count": 0,
                "role_count": 0,
                "role_counts_by_branch": {},
                "role_counts_by_term": {},
                "role_counts_by_category": {},
            },
            "people": [],
            "roles": [],
            "sources": [],
        }
    with PUBLIC_OFFICIALS.open() as handle:
        return json.load(handle)


def load_fred_context() -> dict:
    if not FRED_CONTEXT.exists():
        return {
            "summary": {"series_count": 0, "observation_count": 0, "release_event_count": 0},
            "series": {},
            "release_events": [],
            "source_priorities": [],
            "context_label": "Context only - no inference of causation, intent, legality, ethics, or investment performance.",
        }
    with FRED_CONTEXT.open() as handle:
        return json.load(handle)


def latest_observation_at_or_before(observations: list[dict], target: date) -> dict | None:
    latest = None
    for row in observations:
        row_date = parse_iso_date(row["date"])
        if row_date > target:
            break
        if row.get("value") is not None:
            latest = row
    return latest


def market_point_at_or_after(points: list[dict], target: date) -> dict | None:
    for point in points:
        if point["date"] >= target:
            return point
    return None


def market_point_at_or_before(points: list[dict], target: date) -> dict | None:
    for point in reversed(points):
        if point["date"] <= target:
            return point
    return None


def market_move(points_by_symbol: dict[str, list[dict]], symbol: str, start: str, horizon_days: int) -> dict | None:
    points = points_by_symbol.get(symbol, [])
    if not points:
        return None
    start_date = parse_iso_date(start)
    start_point = market_point_at_or_after(points, start_date)
    end_point = market_point_at_or_before(points, start_date + timedelta(days=horizon_days))
    if not start_point or not end_point or start_point["value"] == 0:
        return None
    pct_change = ((end_point["value"] - start_point["value"]) / start_point["value"]) * 100
    return {
        "symbol": symbol,
        "horizon_days": horizon_days,
        "start_date": iso(start_point["date"]),
        "end_date": iso(end_point["date"]),
        "start_value": start_point["value"],
        "end_value": end_point["value"],
        "pct_change": round(pct_change, 2),
    }


def market_move_between(
    points_by_symbol: dict[str, list[dict]],
    symbol: str,
    start: str,
    end: str,
    label: str,
) -> dict | None:
    points = points_by_symbol.get(symbol, [])
    if not points:
        return None
    start_point = market_point_at_or_after(points, parse_iso_date(start))
    end_point = market_point_at_or_before(points, parse_iso_date(end))
    if not start_point or not end_point or start_point["value"] == 0:
        return None
    pct_change = ((end_point["value"] - start_point["value"]) / start_point["value"]) * 100
    return {
        "symbol": symbol,
        "label": label,
        "start_date": iso(start_point["date"]),
        "end_date": iso(end_point["date"]),
        "start_value": start_point["value"],
        "end_value": end_point["value"],
        "pct_change": round(pct_change, 2),
    }


def price_window(points_by_symbol: dict[str, list[dict]], symbol: str, center: str, days: int = 30) -> list[dict]:
    points = points_by_symbol.get(symbol, [])
    if not points:
        return []
    center_date = parse_iso_date(center)
    start = center_date - timedelta(days=days)
    end = center_date + timedelta(days=days)
    return [
        {"date": iso(point["date"]), "value": round(point["value"], 4)}
        for point in points
        if start <= point["date"] <= end
    ][::2][:32]


def nearby_context_events(fred_context: dict, civic_events: list[dict], target: date, window_days: int = 14) -> list[dict]:
    rows = []
    for event in civic_events:
        event_date = parse_iso_date(event["date"])
        delta = (event_date - target).days
        if abs(delta) <= window_days:
            rows.append(
                {
                    "date": event["date"],
                    "label": event["label"],
                    "event_type": event["event_type"],
                    "source": "CivicLedger fixture event",
                    "days_from_trade": delta,
                }
            )
    for event in fred_context.get("release_events", []):
        event_date = parse_iso_date(event["date"])
        delta = (event_date - target).days
        if abs(delta) <= window_days:
            rows.append(
                {
                    "date": event["date"],
                    "label": event["label"],
                    "event_type": event["event_type"],
                    "source": event["source"],
                    "days_from_trade": delta,
                }
            )
    return sorted(rows, key=lambda item: (abs(item["days_from_trade"]), item["date"]))[:5]


def public_roles_by_person(public_officials: dict) -> dict[str, list[dict]]:
    roles = defaultdict(list)
    for role in public_officials.get("roles", []):
        roles[role["external_person_id"]].append(role)
    for role_rows in roles.values():
        role_rows.sort(key=lambda role: (role.get("service_start") or "9999-12-31", role.get("role_title") or ""))
    return roles


def timeline_event_rows(
    fred_context: dict,
    civic_events: list[dict],
    event_entity_map: dict,
    company_reference: dict,
) -> list[dict]:
    rows = []
    for index, event in enumerate(civic_events, start=1):
        mapped = event_mapping_for(event, event_entity_map)
        matched_entities = company_entities_for_event(event, company_reference)
        company_tickers = sorted({ticker for entity in matched_entities for ticker in entity.get("ticker_scope", [])})
        rows.append(
            {
                "id": event.get("id") or f"curated-event-{index:03d}",
                "date": event["date"],
                "label": event["label"],
                "event_type": event["event_type"],
                "description": event.get("description") or "",
                "source": event.get("source") or "CivicLedger fixture event",
                "relevance": "general",
                "source_urls": event.get("sources", []),
                "branch_scope": event.get("branch_scope", []),
                "sector_scope": sorted(set(event.get("sector_scope", []) + mapped.get("sector_scope", []))),
                "asset_scope": event.get("asset_scope", []),
                "jurisdiction_scope": sorted(
                    set(event.get("jurisdiction_scope", []) + mapped.get("jurisdiction_scope", []))
                ),
                "entity_scope": mapped.get("entity_scope", []),
                "ticker_scope": sorted(set(mapped.get("ticker_scope", []) + company_tickers)),
                "company_entity_scope": matched_entities,
                "market_topic_ids": event.get("market_topic_ids", []),
                "editor_status": event.get("editor_status", "fixture"),
                "market_relevance": event.get("market_relevance"),
                "announcement_date": event.get("announcement_date"),
                "effective_date": event.get("effective_date"),
                "publication_date": event.get("publication_date"),
                "source_tier": event.get("source_tier", "official"),
                "law_number": event.get("law_number"),
                "executive_order_number": event.get("executive_order_number"),
                "docket_number": event.get("docket_number"),
                "citation": event.get("citation"),
                "term_year": event.get("term_year"),
            }
        )
    for index, event in enumerate(fred_context.get("release_events", []), start=1):
        rows.append(
            {
                "id": f"fred-release-{index:03d}",
                "date": event["date"],
                "label": event["label"],
                "event_type": event.get("event_type", "macro_release"),
                "description": event.get("description") or event.get("label") or "",
                "source": event.get("source", "FRED"),
                "relevance": "macro",
                "source_urls": event.get("source_urls")
                or ([event["source_url"]] if event.get("source_url") else []),
                "branch_scope": ["Executive", "Legislative", "Judicial"],
                "sector_scope": ["Broad Market"],
                "asset_scope": [],
                "jurisdiction_scope": ["macro"],
                "entity_scope": ["Federal Reserve", "Bureau of Labor Statistics", "Treasury"],
                "ticker_scope": event_entity_map.get("default_ticker_scope", ["SPY", "QQQ", "DIA"]),
                "company_entity_scope": [],
                "market_topic_ids": [],
                "editor_status": "system_generated",
            }
        )
    return sorted(rows, key=lambda item: (item["date"], item["id"]))


def service_periods(roles: list[dict], trades: list[dict]) -> list[dict]:
    periods = []
    today = date.today().isoformat()
    for role in roles:
        start = role.get("service_start")
        if not start:
            continue
        periods.append(
            {
                "start": start,
                "end": role.get("service_end") or today,
                "active": not bool(role.get("service_end")),
                "role_title": role.get("role_title"),
                "presidential_term": role.get("presidential_term"),
                "source_tier": role.get("source_tier"),
            }
        )
    if not periods and trades:
        trade_dates = sorted(trade.get("trade_date") for trade in trades if trade.get("trade_date"))
        if trade_dates:
            periods.append(
                {
                    "start": trade_dates[0],
                    "end": trade_dates[-1],
                    "active": False,
                    "role_title": "Disclosure activity",
                    "presidential_term": None,
                    "source_tier": "derived",
                }
            )

    merged = []
    for period in sorted(periods, key=lambda row: (row["start"], row["end"])):
        if not merged:
            merged.append({**period})
            continue
        previous = merged[-1]
        gap = (parse_iso_date(period["start"]) - parse_iso_date(previous["end"])).days
        if gap <= 1:
            previous["end"] = max(previous["end"], period["end"])
            previous["active"] = previous["active"] or period["active"]
            previous["role_title"] = previous.get("role_title") or period.get("role_title")
            continue
        merged.append({**period})

    cumulative_days = 0
    for period in merged:
        period["career_start_day"] = cumulative_days
        duration = max(0, (parse_iso_date(period["end"]) - parse_iso_date(period["start"])).days)
        period["career_end_day"] = cumulative_days + duration
        cumulative_days += duration + 1
    return merged


def service_bounds(periods: list[dict]) -> tuple[str | None, str | None]:
    if not periods:
        return None, None
    return periods[0]["start"], periods[-1]["end"]


def active_service_day(value: str | None, periods: list[dict]) -> int | None:
    if not value:
        return None
    target = parse_iso_date(value)
    for period in periods:
        start = parse_iso_date(period["start"])
        end = parse_iso_date(period["end"])
        if start <= target <= end:
            return period["career_start_day"] + (target - start).days
    return None


def market_price_window(
    symbol: str | None,
    trade_date: str | None,
    points_by_symbol: dict[str, list[dict]],
    provider: str,
) -> dict | None:
    if not symbol or not trade_date:
        return None
    points = points_by_symbol.get(normalize_asset_symbol(symbol), [])
    if not points:
        return None
    trade_day = parse_iso_date(trade_date)
    rows = []
    for point in points:
        point_date = point["date"] if isinstance(point["date"], date) else parse_iso_date(point["date"])
        days_from_trade = (point_date - trade_day).days
        if abs(days_from_trade) <= 30:
            rows.append(
                {
                    "date": point_date.isoformat(),
                    "value": round(float(point["value"]), 4),
                    "days_from_trade": days_from_trade,
                }
            )
    if not rows:
        return None
    closest = min(rows, key=lambda row: (abs(row["days_from_trade"]), row["date"]))
    return {
        "provider": provider,
        "symbol": normalize_asset_symbol(symbol),
        "window_days": 30,
        "closest_close": closest["value"],
        "closest_date": closest["date"],
    }


def timeline_trade_row(
    trade: dict,
    periods: list[dict],
    market_points_by_symbol: dict[str, list[dict]],
    crypto_points_by_symbol: dict[str, list[dict]],
) -> dict:
    reference = asset_reference(trade.get("ticker"), trade.get("asset_class"))
    midpoint = value_midpoint(trade)
    row = {
        "id": trade["id"],
        "date": trade["trade_date"],
        "career_day": active_service_day(trade.get("trade_date"), periods),
        "reported_date": trade["reported_date"],
        "action": trade["action"],
        "ticker": normalize_asset_symbol(trade.get("ticker")),
        "asset_display_name": trade["asset_display_name"],
        "asset_class": reference.get("asset_class") or trade.get("asset_class") or "unknown",
        "sector": reference.get("sector", "Unmapped"),
        "value_range_label": trade["value_range_label"],
        "value_range_min": trade.get("value_range_min"),
        "value_range_max": trade.get("value_range_max"),
        "value_midpoint": midpoint,
        "disclosure_lag_days": trade.get("disclosure_lag_days"),
        "record_status": trade.get("record_status", "fixture_demo"),
        "confidence_label": trade.get("confidence_label", "Fixture/demo trade"),
        "parsing_confidence": trade.get("parsing_confidence"),
        "document_id": trade.get("document_id"),
        "source_url": trade.get("source_url"),
        "source_page": trade.get("source_page"),
        "review_required_before_public_trade": trade.get("review_required_before_public_trade", False),
        "public_production_trade": trade.get("public_production_trade"),
        "benchmark_symbol": reference.get("benchmark_symbol", "SPY"),
    }
    if row["asset_class"] == "crypto":
        row["price_window"] = crypto_price_window(row["ticker"], row["date"], crypto_points_by_symbol)
    else:
        row["price_window"] = market_price_window(
            row["ticker"], row["date"], market_points_by_symbol, "Tiingo"
        )
    row["benchmark_price_window"] = market_price_window(
        row["benchmark_symbol"], row["date"], market_points_by_symbol, "Tiingo"
    )
    return row


def event_relevance(event: dict, official: dict, trades: list[dict]) -> dict:
    reasons = []
    event_type = event.get("event_type", "")
    branch = official.get("branch")
    sectors = {trade.get("sector") for trade in trades if trade.get("sector")}
    asset_classes = {trade.get("asset_class") for trade in trades if trade.get("asset_class")}
    tickers = {trade.get("ticker") for trade in trades if trade.get("ticker")}
    branch_scope = set(event.get("branch_scope") or [])
    sector_scope = set(event.get("sector_scope") or [])
    asset_scope = set(event.get("asset_scope") or [])
    ticker_scope = set(event.get("ticker_scope") or [])
    jurisdiction_scope = {str(item).lower() for item in event.get("jurisdiction_scope") or []}
    entity_scope = {str(item).lower() for item in event.get("entity_scope") or []}
    roles = official.get("roles") or []
    role_text = " ".join(
        str(value)
        for role in roles
        for value in [
            role.get("role_title"),
            role.get("office"),
            role.get("agency"),
            role.get("court"),
            role.get("source_metadata", {}).get("committee"),
            role.get("source_metadata", {}).get("chamber"),
        ]
        if value
    ).lower()
    ticker_match = sorted(tickers.intersection(ticker_scope))
    sector_match = sorted(sectors.intersection(sector_scope))
    asset_match = sorted(asset_classes.intersection(asset_scope))
    jurisdiction_match = sorted(scope for scope in jurisdiction_scope if scope in role_text)
    entity_match = sorted(scope for scope in entity_scope if scope in role_text)

    inferred_from_title = event.get("market_relevance") == "title_keyword_match"
    if ticker_match:
        reasons.append(f"asset or ticker scope: {', '.join(ticker_match)}")
    if jurisdiction_match:
        reasons.append(f"office jurisdiction: {', '.join(jurisdiction_match[:3])}")
    if entity_match:
        reasons.append(f"agency or entity scope: {', '.join(entity_match[:3])}")
    if sector_match:
        reasons.append(f"sector scope: {', '.join(sector_match)}")
    if asset_match:
        reasons.append(f"asset class: {', '.join(asset_match)}")
    if branch_scope and branch in branch_scope:
        reasons.append(f"{branch.lower()} branch scope")

    institutional = False
    if branch == "Executive" and event_type in {"executive_order", "presidential_document", "agency_rule"}:
        institutional = True
    if branch == "Legislative" and event_type in {"legislation", "bill_action", "vote", "funding"}:
        institutional = True
    if branch == "Judicial" and event_type == "court_decision":
        institutional = True
    if institutional:
        reasons.append("institutional event type")

    if event.get("relevance") == "macro":
        tier = "general_macro"
        reasons.append("general macro context")
    elif ticker_match and not inferred_from_title:
        tier = "asset_specific"
    elif jurisdiction_match or entity_match:
        tier = "jurisdictional"
    elif institutional and branch in branch_scope:
        tier = "institutional"
    elif ticker_match or sector_match or asset_match:
        tier = "sector_context"
    else:
        tier = "general_context"
        if not reasons:
            reasons.append("global public context")

    tier_rank = {
        "direct": 6,
        "asset_specific": 5,
        "jurisdictional": 4,
        "institutional": 3,
        "sector_context": 2,
        "general_macro": 1,
        "general_context": 0,
    }
    return {
        "tier": tier,
        "tier_rank": tier_rank[tier],
        "reasons": reasons,
        "display_default": tier in {"direct", "asset_specific", "jurisdictional"}
        or (tier == "institutional" and event.get("editor_status") == "curated"),
    }


def timeline_event_positions(
    events: list[dict],
    periods: list[dict],
    official: dict,
    trades: list[dict],
) -> list[dict]:
    if not periods:
        return []
    rows = []
    for event in events:
        career_day = active_service_day(event["date"], periods)
        if career_day is None:
            continue
        relevance = event_relevance(event, official, trades)
        rows.append(
            {
                "id": event["id"],
                "date": event["date"],
                "career_day": career_day,
                "relationship_tier": relevance["tier"],
                "relationship_tier_rank": relevance["tier_rank"],
                "relationship_reasons": relevance["reasons"],
                "display_default": relevance["display_default"],
            }
        )
    return rows


def trade_clusters(timeline_trades: list[dict], window_days: int = 14) -> list[dict]:
    clusters = []
    current = []
    for trade in sorted(timeline_trades, key=lambda row: (row["date"], row["id"])):
        if current and (parse_iso_date(trade["date"]) - parse_iso_date(current[-1]["date"])).days > window_days:
            if len(current) > 1:
                clusters.append(cluster_row(current, window_days))
            current = []
        current.append(trade)
    if len(current) > 1:
        clusters.append(cluster_row(current, window_days))
    return clusters


def cluster_row(rows: list[dict], window_days: int) -> dict:
    return {
        "id": f"cluster-{rows[0]['date']}-{rows[-1]['date']}-{len(rows)}",
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "window_days": window_days,
        "trade_count": len(rows),
        "asset_classes": dict(Counter(row["asset_class"] for row in rows)),
        "tickers": sorted({row["ticker"] for row in rows if row.get("ticker")}),
        "total_value_midpoint": round(sum(row.get("value_midpoint") or 0 for row in rows), 2),
    }


def career_trade_timeline(
    public_officials: dict,
    fixture_people: list[dict],
    all_trades: list[dict],
    market_series: list[dict],
    fred_context: dict,
    civic_events: list[dict],
    crypto_prices: dict,
    presidential_oge_status: dict,
    presidential_oge_documents: dict,
    presidential_oge_transactions: dict,
    house_ptr_transactions: dict,
    event_entity_map: dict,
    company_reference: dict,
    include_fixture_timelines: bool = False,
) -> dict:
    roles_by_person = public_roles_by_person(public_officials)
    trades_by_person = defaultdict(list)
    for trade in all_trades:
        trades_by_person[trade["person_id"]].append(trade)

    public_people_by_id = {person["external_person_id"]: person for person in public_officials.get("people", [])}
    president_ids = []
    official_rows = []
    events = timeline_event_rows(fred_context, civic_events, event_entity_map, company_reference)
    oge_by_official = defaultdict(list)
    for status in presidential_oge_status.get("officials", []):
        oge_by_official[status["official_id"]].append(status)
    oge_documents_by_official = defaultdict(list)
    for document in presidential_oge_documents.get("documents", []):
        oge_documents_by_official[document["official_id"]].append(document)
    oge_unavailable_by_official = defaultdict(list)
    for unavailable in presidential_oge_documents.get("unavailable_documents", []):
        oge_unavailable_by_official[unavailable["official_id"]].append(unavailable)
    oge_transactions_by_official = defaultdict(list)
    for transaction in presidential_oge_transactions.get("transactions", []):
        oge_transactions_by_official[transaction["official_id"]].append(transaction)
    house_transactions_by_official = defaultdict(list)
    for transaction in house_ptr_transactions.get("transactions", []):
        house_transactions_by_official[transaction["official_id"]].append(transaction)
    house_documents_by_official = defaultdict(list)
    for document in house_ptr_transactions.get("documents", []):
        if document.get("official_id"):
            house_documents_by_official[document["official_id"]].append(document)
    crypto_points_by_symbol = {
        symbol: series.get("points", [])
        for symbol, series in crypto_prices.get("series", {}).items()
    }
    market_points_by_symbol = defaultdict(list)
    for point in market_series:
        market_points_by_symbol[point["symbol"]].append(point)

    for external_id, roles in roles_by_person.items():
        presidential_roles = [
            role
            for role in roles
            if role.get("role_title") == "President" and role.get("role_category") == "elected_executive"
        ]
        if not presidential_roles:
            continue
        person = public_people_by_id.get(external_id, {})
        preview_trade_source_rows = sorted(
            oge_transactions_by_official.get(external_id, []),
            key=lambda item: (item["trade_date"], item["id"]),
        )
        periods = service_periods(presidential_roles, preview_trade_source_rows)
        start, end = service_bounds(periods)
        timeline_trades = [
            timeline_trade_row(trade, periods, market_points_by_symbol, crypto_points_by_symbol)
            for trade in preview_trade_source_rows
        ]
        disclosure_documents = oge_documents_by_official.get(external_id, [])
        unavailable_documents = oge_unavailable_by_official.get(external_id, [])
        document_count = len(disclosure_documents)
        preview_trade_count = len(timeline_trades)
        disclosure_status = "No reviewed presidential trade disclosures ingested yet"
        record_status = "source_status_only"
        confidence_label = "Source status only"
        if preview_trade_count:
            disclosure_status = (
                f"{document_count} official OGE documents indexed; "
                f"{preview_trade_count} parser-preview 278-T transactions require review before production promotion"
            )
            record_status = "official_oge_parser_preview_not_promoted"
            confidence_label = "Official OGE parser preview; review required"
        elif document_count:
            disclosure_status = f"{document_count} official OGE documents indexed; no parser-preview transactions detected"
            record_status = "official_oge_documents_indexed"
            confidence_label = "Official OGE documents indexed"
        elif unavailable_documents:
            disclosure_status = "Historical OGE records require official archive/request workflow"
        president_ids.append(external_id)
        official_rows.append(
            {
                "id": external_id,
                "full_name": person.get("full_name", external_id),
                "branch": "Executive",
                "timeline_group": "presidential_baseline",
                "service_start": start,
                "service_end": end,
                "service_periods": periods,
                "active_service_days": periods[-1]["career_end_day"] + 1 if periods else 0,
                "roles": presidential_roles,
                "trades": timeline_trades,
                "disclosure_sources": oge_by_official.get(external_id, []),
                "disclosure_documents": disclosure_documents,
                "unavailable_disclosure_documents": unavailable_documents,
                "events": timeline_event_positions(
                    events,
                    periods,
                    {"branch": "Executive", "roles": presidential_roles},
                    timeline_trades,
                ),
                "trade_clusters": trade_clusters(timeline_trades),
                "stats": {
                    "trade_count": preview_trade_count,
                    "parser_preview_trade_count": preview_trade_count,
                    "document_count": document_count,
                    "buy_count": sum(1 for trade in timeline_trades if trade["action"] == "BUY"),
                    "sell_count": sum(1 for trade in timeline_trades if trade["action"] == "SELL"),
                    "crypto_count": sum(1 for trade in timeline_trades if trade["asset_class"] == "crypto"),
                    "total_value_midpoint": round(sum(trade["value_midpoint"] or 0 for trade in timeline_trades), 2),
                    "disclosure_status": disclosure_status,
                    "record_status": record_status,
                    "confidence_label": confidence_label,
                    "public_production_trade_count": 0,
                    "review_required_before_public_trade": preview_trade_count > 0 or document_count > 0,
                },
            }
        )

    house_out_of_service_trade_count = 0
    for external_id, source_rows in sorted(house_transactions_by_official.items()):
        roles = roles_by_person.get(external_id, [])
        if not roles:
            continue
        person = public_people_by_id.get(external_id, {})
        periods = service_periods(roles, source_rows)
        start, end = service_bounds(periods)
        timeline_trades = []
        for trade in sorted(source_rows, key=lambda item: (item["trade_date"], item["id"])):
            row = timeline_trade_row(trade, periods, market_points_by_symbol, crypto_points_by_symbol)
            if row["career_day"] is None:
                house_out_of_service_trade_count += 1
                continue
            timeline_trades.append(row)
        documents = house_documents_by_official.get(external_id, [])
        official_rows.append(
            {
                "id": external_id,
                "full_name": person.get("full_name", external_id),
                "branch": "Legislative",
                "timeline_group": "official_house_ptr_preview",
                "service_start": start,
                "service_end": end,
                "service_periods": periods,
                "active_service_days": periods[-1]["career_end_day"] + 1 if periods else 0,
                "roles": roles,
                "trades": timeline_trades,
                "disclosure_sources": [
                    {
                        "source_id": "house-financial-disclosure",
                        "source_url": "https://disclosures-clerk.house.gov/financialdisclosure",
                        "record_status": "official_house_parser_preview_not_promoted",
                    }
                ],
                "events": timeline_event_positions(
                    events,
                    periods,
                    {"branch": "Legislative", "roles": roles},
                    timeline_trades,
                ),
                "trade_clusters": trade_clusters(timeline_trades),
                "stats": {
                    "trade_count": len(timeline_trades),
                    "parser_preview_trade_count": len(timeline_trades),
                    "document_count": len(documents),
                    "buy_count": sum(1 for trade in timeline_trades if trade["action"] == "BUY"),
                    "sell_count": sum(1 for trade in timeline_trades if trade["action"] == "SELL"),
                    "crypto_count": sum(1 for trade in timeline_trades if trade["asset_class"] == "crypto"),
                    "total_value_midpoint": round(sum(trade["value_midpoint"] or 0 for trade in timeline_trades), 2),
                    "disclosure_status": (
                        f"{len(documents)} official House PTR documents; "
                        f"{len(timeline_trades)} parser-preview transactions require review"
                    ),
                    "record_status": "official_house_parser_preview_not_promoted",
                    "confidence_label": "Official House Clerk PTR parser preview; review required",
                    "public_production_trade_count": 0,
                    "review_required_before_public_trade": True,
                },
            }
        )

    for person in fixture_people if include_fixture_timelines else []:
        person_trades = sorted(trades_by_person.get(person["id"], []), key=lambda item: (item["trade_date"], item["id"]))
        fixture_roles = [
            {
                "service_start": person.get("service_start"),
                "service_end": person.get("service_end"),
                "role_title": person.get("office") or person.get("chamber") or person.get("branch"),
                "role_category": "fixture_trade_official",
                "source_tier": "fixture",
            }
        ]
        periods = service_periods(fixture_roles, person_trades)
        start, end = service_bounds(periods)
        timeline_trades = [
            timeline_trade_row(trade, periods, market_points_by_symbol, crypto_points_by_symbol)
            for trade in person_trades
        ]
        official_rows.append(
            {
                "id": person["id"],
                "full_name": person["full_name"],
                "branch": person["branch"],
                "timeline_group": "fixture_trade_preview",
                "service_start": start,
                "service_end": end,
                "service_periods": periods,
                "active_service_days": periods[-1]["career_end_day"] + 1 if periods else 0,
                "roles": fixture_roles,
                "trades": timeline_trades,
                "disclosure_sources": [],
                "events": timeline_event_positions(events, periods, person, timeline_trades),
                "trade_clusters": trade_clusters(timeline_trades),
                "stats": {
                    "trade_count": len(timeline_trades),
                    "buy_count": sum(1 for trade in timeline_trades if trade["action"] == "BUY"),
                    "sell_count": sum(1 for trade in timeline_trades if trade["action"] == "SELL"),
                    "crypto_count": sum(1 for trade in timeline_trades if trade["asset_class"] == "crypto"),
                    "total_value_midpoint": round(sum(trade["value_midpoint"] or 0 for trade in timeline_trades), 2),
                    "disclosure_status": "Fixture trade preview",
                    "record_status": "fixture_demo",
                    "confidence_label": "Fixture/demo trades",
                },
            }
        )

    asset_classes = sorted(
        {
            trade["asset_class"]
            for official in official_rows
            for trade in official["trades"]
            if trade.get("asset_class")
        }
    )
    return {
        "schema_version": "career-trade-timeline-v2",
        "event_relationship_methodology_version": "event-relevance-v2",
        "default_axis": "career",
        "axis_modes": ["career", "calendar", "event_window"],
        "zoom_presets": [
            {"id": "full", "label": "Full career", "days": None},
            {"id": "first-year", "label": "First year", "days": 365},
            {"id": "first-term", "label": "First term", "days": 1461},
            {"id": "event-window", "label": "Event window", "days": 360},
        ],
        "default_official_ids": sorted(president_ids),
        "asset_classes": asset_classes,
        "event_types": sorted({event["event_type"] for event in events}),
        "summary": {
            "official_count": len(official_rows),
            "default_official_count": len(president_ids),
            "trade_count": sum(len(official["trades"]) for official in official_rows),
            "event_count": len(events),
            "crypto_trade_count": sum(official["stats"]["crypto_count"] for official in official_rows),
            "trade_cluster_count": sum(len(official.get("trade_clusters", [])) for official in official_rows),
            "presidential_oge_status_count": presidential_oge_status.get("summary", {}).get("official_status_count", 0),
            "presidential_oge_document_count": presidential_oge_documents.get("summary", {}).get("document_count", 0),
            "presidential_oge_parser_preview_transaction_count": presidential_oge_transactions.get("summary", {}).get(
                "parser_preview_transaction_count",
                0,
            ),
            "presidential_oge_public_production_trade_count": presidential_oge_transactions.get("summary", {}).get(
                "public_production_trade_count",
                0,
            ),
            "house_ptr_document_count": house_ptr_transactions.get("summary", {}).get(
                "processed_document_count", 0
            ),
            "house_ptr_parser_preview_transaction_count": house_ptr_transactions.get("summary", {}).get(
                "parser_preview_transaction_count", 0
            ),
            "house_ptr_timeline_transaction_count": sum(
                len(official["trades"])
                for official in official_rows
                if official["timeline_group"] == "official_house_ptr_preview"
            ),
            "house_ptr_out_of_service_trade_count": house_out_of_service_trade_count,
        },
        "officials": official_rows,
        "events": events,
        "crypto_market": {
            "provider": crypto_prices.get("provider"),
            "context_label": crypto_prices.get("context_label"),
            "summary": crypto_prices.get("summary", {}),
            "coverage_report": crypto_prices.get("coverage_report", {}),
        },
        "presidential_oge_status": {
            "context_label": presidential_oge_status.get("context_label"),
            "summary": presidential_oge_status.get("summary", {}),
            "source": presidential_oge_status.get("source", {}),
        },
        "presidential_oge_documents": {
            "context_label": presidential_oge_documents.get("context_label"),
            "summary": presidential_oge_documents.get("summary", {}),
            "source": presidential_oge_documents.get("source", {}),
            "unavailable_documents": presidential_oge_documents.get("unavailable_documents", []),
        },
        "presidential_oge_transactions": {
            "context_label": presidential_oge_transactions.get("context_label"),
            "summary": presidential_oge_transactions.get("summary", {}),
        },
        "event_entity_map": {
            "schema_version": event_entity_map.get("schema_version"),
            "context_label": event_entity_map.get("context_label"),
            "mapped_event_count": len(event_entity_map.get("event_maps", [])),
            "company_entity_count": len(company_reference.get("entities", [])),
        },
    }


def trade_context_rows(
    all_people: list[dict],
    all_trades: list[dict],
    market_series: list[dict],
    market_metadata: dict,
    fred_context: dict,
    civic_events: list[dict],
) -> list[dict]:
    person_by_id = {person["id"]: person for person in all_people}
    points_by_symbol = defaultdict(list)
    for point in market_series:
        points_by_symbol[point["symbol"]].append(point)
    for points in points_by_symbol.values():
        points.sort(key=lambda item: item["date"])

    rows = []
    for trade in sorted(all_trades, key=lambda item: (item["trade_date"], item["id"]))[:48]:
        trade_date = parse_iso_date(trade["trade_date"])
        ticker = (trade.get("ticker") or "").upper()
        reference = market_metadata.get("ticker_reference", {}).get(ticker, {})
        benchmark_symbol = reference.get("benchmark_symbol") or "SPY"
        benchmark_symbol = benchmark_symbol if benchmark_symbol in points_by_symbol else "SPY"
        ticker_covered = ticker in points_by_symbol
        primary_symbol = ticker if ticker_covered else benchmark_symbol
        horizon_moves = {
            "asset": [
                move
                for move in [
                    market_move(points_by_symbol, primary_symbol, trade["trade_date"], 7),
                    market_move(points_by_symbol, primary_symbol, trade["trade_date"], 30),
                    market_move(points_by_symbol, primary_symbol, trade["trade_date"], 90),
                ]
                if move
            ],
            "benchmark": [
                move
                for move in [
                    market_move(points_by_symbol, benchmark_symbol, trade["trade_date"], 7),
                    market_move(points_by_symbol, benchmark_symbol, trade["trade_date"], 30),
                    market_move(points_by_symbol, benchmark_symbol, trade["trade_date"], 90),
                ]
                if move
            ],
        }
        trade_to_report_moves = [
            move
            for move in [
                market_move_between(points_by_symbol, primary_symbol, trade["trade_date"], trade["reported_date"], "asset trade-to-report"),
                market_move_between(points_by_symbol, benchmark_symbol, trade["trade_date"], trade["reported_date"], "benchmark trade-to-report"),
            ]
            if move
        ]
        macro_snapshot = {}
        for series_id in ["FEDFUNDS", "CPIAUCSL", "DGS10", "DGS2", "USREC"]:
            series = fred_context.get("series", {}).get(series_id)
            if not series:
                continue
            observation = latest_observation_at_or_before(series["observations"], trade_date)
            if observation:
                macro_snapshot[series_id] = {
                    "label": series["label"],
                    "date": observation["date"],
                    "value": observation["value"],
                    "units": series["units"],
                }
        rows.append(
            {
                "trade_id": trade["id"],
                "person_id": trade["person_id"],
                "person_name": person_by_id.get(trade["person_id"], {}).get("full_name", trade["person_id"]),
                "trade_date": trade["trade_date"],
                "reported_date": trade["reported_date"],
                "action": trade["action"],
                "asset_display_name": trade["asset_display_name"],
                "ticker": ticker,
                "issuer_reference": {
                    "issuer_name": reference.get("issuer_name") or trade["asset_display_name"],
                    "asset_class": reference.get("asset_class") or trade.get("asset_class"),
                    "sector": reference.get("sector") or "Unmapped",
                    "benchmark_symbol": benchmark_symbol,
                    "coverage_status": "covered" if ticker_covered else "fallback_to_benchmark",
                },
                "value_range_label": trade["value_range_label"],
                "disclosure_lag_days": trade["disclosure_lag_days"],
                "market_moves": horizon_moves["asset"][:1] + horizon_moves["benchmark"][:1],
                "horizon_moves": horizon_moves,
                "trade_to_report_moves": trade_to_report_moves,
                "price_window": {
                    "asset": {
                        "symbol": primary_symbol,
                        "points": price_window(points_by_symbol, primary_symbol, trade["trade_date"]),
                    },
                    "benchmark": {
                        "symbol": benchmark_symbol,
                        "points": price_window(points_by_symbol, benchmark_symbol, trade["trade_date"]),
                    },
                },
                "market_provider": market_metadata["summary"].get(
                    "active_market_price_provider",
                    market_metadata["provider"],
                ),
                "market_context_label": market_metadata["context_label"],
                "macro_snapshot": macro_snapshot,
                "nearby_events": nearby_context_events(fred_context, civic_events, trade_date),
                "context_label": fred_context.get(
                    "context_label",
                    "Context only - no inference of causation, intent, legality, ethics, or investment performance.",
                ),
            }
        )
    return rows


def build_dataset() -> dict:
    random.seed(42)
    public_officials = load_public_officials()
    fred_context = load_fred_context()
    civic_events = load_events()
    federal_event_context = load_json_file(FEDERAL_EVENTS, {"summary": {}, "sources": []})
    context_maps = load_context_maps()
    disclosure_artifacts = load_disclosure_artifacts()
    market_series, market_metadata = load_market_prices()
    crypto_prices = load_crypto_prices()
    presidential_oge_status = load_presidential_oge_status()
    presidential_oge_documents = load_presidential_oge_documents()
    presidential_oge_transactions = load_presidential_oge_transactions()
    house_ptr_transactions = load_house_ptr_transactions()
    house_disclosure_index = load_json_file(HOUSE_DISCLOSURE_INDEX, {"summary": {}})
    people = create_people()
    all_people = []
    all_filings = []
    all_trades = []
    all_raw_documents = []
    source_counts = defaultdict(lambda: {"raw_documents": 0, "filings": 0, "trades": 0})

    for person_index, person in enumerate(people, start=1):
        person_id = slugify(person.full_name)
        raw_documents, filings, trades, _artifacts = create_filings_and_trades(
            person,
            "static-pages-fixture-run",
        )
        filing_id_map = {}
        for filing_index, filing in enumerate(filings, start=1):
            filing_id_map[str(filing.id)] = f"{person_id}-filing-{filing_index:02d}"

        static_trades = []
        for trade_index, trade in enumerate(trades, start=1):
            trade_id = f"{person_id}-trade-{trade_index:03d}"
            filing_id = filing_id_map[str(trade.filing_id)]
            row = {
                "id": trade_id,
                "person_id": person_id,
                "filing_id": filing_id,
                "trade_date": iso(trade.trade_date),
                "reported_date": iso(trade.reported_date),
                "action": trade.action,
                "asset_display_name": trade.asset_display_name,
                "ticker": trade.ticker,
                "asset_class": trade.asset_class,
                "value_range_label": trade.value_range_label,
                "value_range_min": number(trade.value_range_min),
                "value_range_max": number(trade.value_range_max),
                "disclosure_lag_days": trade.disclosure_lag_days,
                "parsing_confidence": number(trade.parsing_confidence),
                "record_status": "fixture_demo",
                "confidence_label": "Fixture/demo parser output",
            }
            static_trades.append(row)
            all_trades.append(row)

        source_id = source_id_for_person(person)
        source_counts[source_id]["raw_documents"] += len(raw_documents)
        source_counts[source_id]["filings"] += len(filings)
        source_counts[source_id]["trades"] += len(static_trades)

        static_filings = []
        for filing_index, filing in enumerate(filings, start=1):
            row = {
                "id": filing_id_map[str(filing.id)],
                "person_id": person_id,
                "filing_type": filing.filing_type,
                "filed_date": iso(filing.filed_date),
                "source_url": filing.source_url,
                "retrieval_source": filing.retrieval_source,
                "file_hash": filing.file_hash,
            }
            static_filings.append(row)
            all_filings.append(row)

        for raw_index, raw_document in enumerate(raw_documents, start=1):
            all_raw_documents.append(
                {
                    "id": f"{person_id}-raw-{raw_index:02d}",
                    "person_id": person_id,
                    "source_id": source_id,
                    "retrieved_at": iso(raw_document.retrieved_at),
                    "content_type": raw_document.content_type,
                    "file_hash": raw_document.file_hash,
                    "rights_status": raw_document.rights_status,
                    "provenance_complete": raw_document.provenance_complete,
                }
            )

        action_counts = Counter(trade["action"] for trade in static_trades)
        asset_counts = Counter(trade["asset_class"] for trade in static_trades)
        all_people.append(
            {
                "id": person_id,
                "display_order": person_index,
                "full_name": person.full_name,
                "branch": person.branch,
                "chamber": person.chamber,
                "state": person.state,
                "party": person.party,
                "district": person.district,
                "office": person.office,
                "agency": person.agency,
                "court": person.court,
                "service_start": iso(person.service_start),
                "service_end": iso(person.service_end),
                "source_id": source_id,
                "filings": static_filings,
                "trades": static_trades,
                "stats": {
                    "filing_count": len(static_filings),
                    "trade_count": len(static_trades),
                    "buy_count": action_counts.get("BUY", 0),
                    "sell_count": action_counts.get("SELL", 0),
                    "median_lag_days": median([trade["disclosure_lag_days"] for trade in static_trades]),
                    "asset_classes": dict(sorted(asset_counts.items())),
                    "total_reported_min": sum(trade["value_range_min"] or 0 for trade in static_trades),
                    "total_reported_max": sum(trade["value_range_max"] or 0 for trade in static_trades),
                },
                "scorecard": scorecard(person.branch, len(static_filings), static_trades),
            }
        )

    fixture_branch_counts = Counter(person["branch"] for person in all_people)
    career_timeline = career_trade_timeline(
        public_officials,
        all_people,
        all_trades,
        market_series,
        fred_context,
        civic_events,
        crypto_prices,
        presidential_oge_status,
        presidential_oge_documents,
        presidential_oge_transactions,
        house_ptr_transactions,
        context_maps["event_entity_map"],
        context_maps["company_entity_reference"],
    )
    branch_counts = Counter(official["branch"] for official in career_timeline["officials"])
    sources = []
    for source in OFFICIAL_SOURCES:
        counts = source_counts[source["id"]]
        source_status = source.get("ingestion_status", "planned")
        missing_capabilities = [
            "reviewed production official-source ingestion",
            "reviewed public filing promotion",
        ]
        if source["id"] == "house-financial-disclosure" and house_ptr_transactions["summary"].get(
            "processed_document_count"
        ):
            source_status = "official_index_and_parser_preview"
            missing_capabilities = [
                "OCR extraction and validation for image-only filings",
                "reviewed public filing promotion",
            ]
        status_label = {
            "parser_preview_ready": "Parser preview ready",
            "source_index_ready": "Source index ready",
            "official_index_and_parser_preview": "Official index and parser previews ready",
            "planned": "Planned",
        }.get(source_status, source_status)
        sources.append(
            {
                **source,
                "fixture_counts": counts,
                "readiness": {
                    "status": source_status,
                    "label": status_label,
                    "missing_capabilities": missing_capabilities,
                },
            }
        )

    return {
        "generated_at": date.today().isoformat(),
        "dataset_version": settings.DATASET_VERSION,
        "methodology_version": settings.METHODOLOGY_VERSION,
        "parser_version": settings.PARSER_VERSION,
        "site_mode": "public_research_preview",
        "disclaimer": (
            "This public research preview combines source-backed official rosters, official House Clerk and OGE "
            "parser previews, and market context. Development fixtures are excluded from public timelines. "
            "Parser previews require review and are not reviewed public-production trades."
        ),
        "summary": {
            "official_count": career_timeline["summary"]["official_count"],
            "fixture_demo_official_count": len(all_people),
            "tracked_public_official_count": public_officials["summary"]["person_count"],
            "public_official_role_count": public_officials["summary"]["role_count"],
            "filing_count": len(all_filings),
            "trade_count": len(all_trades),
            "raw_document_count": len(all_raw_documents),
            "event_count": len(civic_events),
            "source_ingested_federal_event_count": federal_event_context.get("summary", {}).get(
                "event_count", 0
            ),
            "macro_series_count": fred_context["summary"].get("series_count", 0),
            "macro_release_event_count": fred_context["summary"].get("release_event_count", 0),
            "market_price_provider": market_metadata["summary"].get("active_market_price_provider", market_metadata["provider"]),
            "market_price_point_count": market_metadata["summary"].get("price_point_count", 0),
            "crypto_price_point_count": crypto_prices["summary"].get("price_point_count", 0),
            "career_timeline_official_count": career_timeline["summary"]["official_count"],
            "career_timeline_default_official_count": career_timeline["summary"]["default_official_count"],
            "career_timeline_trade_count": career_timeline["summary"]["trade_count"],
            "career_timeline_crypto_trade_count": career_timeline["summary"]["crypto_trade_count"],
            "career_timeline_trade_cluster_count": career_timeline["summary"]["trade_cluster_count"],
            "presidential_oge_source_status_count": career_timeline["summary"]["presidential_oge_status_count"],
            "presidential_oge_document_count": career_timeline["summary"]["presidential_oge_document_count"],
            "presidential_oge_parser_preview_transaction_count": career_timeline["summary"][
                "presidential_oge_parser_preview_transaction_count"
            ],
            "presidential_oge_public_production_trade_count": career_timeline["summary"][
                "presidential_oge_public_production_trade_count"
            ],
            "house_ptr_indexed_document_count": house_disclosure_index.get("summary", {})
            .get("member_ptr_document_count", 0),
            "house_ptr_processed_document_count": house_ptr_transactions["summary"].get(
                "processed_document_count", 0
            ),
            "house_ptr_machine_readable_document_count": house_ptr_transactions["summary"]
            .get("document_status_counts", {})
            .get("parser_preview", 0),
            "house_ptr_ocr_required_document_count": house_ptr_transactions["summary"]
            .get("document_status_counts", {})
            .get("ocr_required", 0),
            "house_ptr_parser_preview_transaction_count": house_ptr_transactions["summary"].get(
                "parser_preview_transaction_count", 0
            ),
            "house_ptr_timeline_transaction_count": career_timeline["summary"].get(
                "house_ptr_timeline_transaction_count", 0
            ),
            "house_ptr_timeline_official_count": sum(
                1
                for official in career_timeline["officials"]
                if official["timeline_group"] == "official_house_ptr_preview"
            ),
            "disclosure_queue_item_count": disclosure_artifacts["ingestion_queue"].get("summary", {}).get("queue_item_count", 0),
            "archived_source_document_count": disclosure_artifacts["raw_archive_index"].get("summary", {}).get("archived_document_count", 0),
            "reviewed_fixture_promotion_count": disclosure_artifacts["reviewed_promotions"].get("summary", {}).get("reviewed_fixture_promotion_count", 0),
            "reviewed_public_trade_count": disclosure_artifacts["completeness_dashboard"].get("summary", {}).get("reviewed_public_trade_count", 0),
            "branch_counts": dict(sorted(branch_counts.items())),
            "fixture_branch_counts": dict(sorted(fixture_branch_counts.items())),
            "public_official_role_counts_by_branch": public_officials["summary"]["role_counts_by_branch"],
            "public_official_role_counts_by_term": public_officials["summary"]["role_counts_by_term"],
            "public_official_role_counts_by_category": public_officials["summary"]["role_counts_by_category"],
        },
        "public_officials": public_officials,
        "people": all_people,
        "filings": all_filings,
        "trades": all_trades,
        "raw_documents": all_raw_documents,
        "sources": sources,
        "events": civic_events,
        "federal_event_context": {
            "schema_version": federal_event_context.get("schema_version"),
            "generated_at": federal_event_context.get("generated_at"),
            "scope": federal_event_context.get("scope", {}),
            "sources": federal_event_context.get("sources", []),
            "summary": federal_event_context.get("summary", {}),
            "context_label": federal_event_context.get("context_label"),
        },
        "market": market_snapshot(market_series, market_metadata),
        "crypto_market": {
            "provider": crypto_prices.get("provider"),
            "context_label": crypto_prices.get("context_label"),
            "summary": crypto_prices.get("summary", {}),
            "source": crypto_prices.get("source", {}),
            "coverage_report": crypto_prices.get("coverage_report", {}),
        },
        "presidential_oge_status": {
            "context_label": presidential_oge_status.get("context_label"),
            "summary": presidential_oge_status.get("summary", {}),
            "source": presidential_oge_status.get("source", {}),
        },
        "presidential_oge_documents": {
            "context_label": presidential_oge_documents.get("context_label"),
            "summary": presidential_oge_documents.get("summary", {}),
            "source": presidential_oge_documents.get("source", {}),
            "unavailable_documents": presidential_oge_documents.get("unavailable_documents", []),
            "documents": presidential_oge_documents.get("documents", []),
        },
        "presidential_oge_transactions": {
            "context_label": presidential_oge_transactions.get("context_label"),
            "summary": presidential_oge_transactions.get("summary", {}),
            "transactions": presidential_oge_transactions.get("transactions", []),
        },
        "house_disclosures": {
            "index": {
                "schema_version": house_disclosure_index.get("schema_version"),
                "generated_at": house_disclosure_index.get("generated_at"),
                "source": house_disclosure_index.get("source", {}),
                "scope": house_disclosure_index.get("scope", {}),
                "summary": house_disclosure_index.get("summary", {}),
            },
            "transactions_manifest": house_ptr_transactions.get("manifest", {}),
        },
        "disclosure_pipeline": public_disclosure_artifacts(disclosure_artifacts),
        "context_maps": context_maps,
        "fred_context": fred_context,
        "career_trade_timeline": career_timeline,
        "trade_context": {
            "context_label": fred_context.get(
                "context_label",
                "Context only - no inference of causation, intent, legality, ethics, or investment performance.",
            ),
            "rows": trade_context_rows(
                all_people,
                all_trades,
                market_series,
                market_metadata,
                fred_context,
                civic_events,
            ),
        },
    }


def compact_role(role: dict) -> dict:
    metadata = role.get("source_metadata") or {}
    return {
        "id": role.get("external_role_id"),
        "presidential_term": role.get("presidential_term"),
        "role_category": role.get("role_category"),
        "role_title": role.get("role_title"),
        "office": role.get("office"),
        "agency": role.get("agency"),
        "court": role.get("court"),
        "service_start": role.get("service_start"),
        "service_end": role.get("service_end"),
        "source_id": role.get("source_id"),
        "source_tier": role.get("source_tier"),
        "source_url": role.get("source_url"),
        "chamber": metadata.get("chamber"),
        "congress_number": metadata.get("congress_number"),
        "party": metadata.get("party"),
        "state": metadata.get("state"),
        "district": metadata.get("district"),
        "bioguide_id": metadata.get("bioguide_id"),
    }


def compact_official_index(public_officials: dict) -> tuple[list[dict], dict[str, list[dict]]]:
    roles_by_person = public_roles_by_person(public_officials)
    details = {}
    rows = []
    for person in public_officials.get("people", []):
        external_id = person["external_person_id"]
        roles = sorted(
            roles_by_person.get(external_id, []),
            key=lambda role: (role.get("service_start") or "", role.get("external_role_id") or ""),
        )
        compact_roles = [compact_role(role) for role in roles]
        details[external_id] = compact_roles
        primary = next((role for role in reversed(compact_roles) if not role.get("service_end")), None)
        primary = primary or (compact_roles[-1] if compact_roles else None)
        periods = service_periods(roles, [])
        rows.append(
            {
                "id": external_id,
                "full_name": person["full_name"],
                "branch": person["branch"],
                "role_count": len(compact_roles),
                "primary_role": primary,
                "service_periods": periods,
                "terms": sorted({role["presidential_term"] for role in compact_roles if role.get("presidential_term")}),
                "role_categories": sorted({role["role_category"] for role in compact_roles if role.get("role_category")}),
                "chambers": sorted({role["chamber"] for role in compact_roles if role.get("chamber")}),
                "congresses": sorted({role["congress_number"] for role in compact_roles if role.get("congress_number")}),
                "parties": sorted({role["party"] for role in compact_roles if role.get("party")}),
                "states": sorted({role["state"] for role in compact_roles if role.get("state")}),
                "districts": sorted({str(role["district"]) for role in compact_roles if role.get("district") is not None}),
            }
        )
    return sorted(rows, key=lambda row: (row["branch"], row["full_name"])), details


def coverage_payload(dataset: dict) -> dict:
    timeline_officials = dataset["career_trade_timeline"].get("officials", [])
    record_states = Counter(
        trade.get("record_status", "unknown")
        for official in timeline_officials
        for trade in official.get("trades", [])
    )
    event_types = Counter(event.get("event_type", "other") for event in dataset["career_trade_timeline"].get("events", []))
    event_editor_states = Counter(
        event.get("editor_status", "unknown") for event in dataset["career_trade_timeline"].get("events", [])
    )
    timeline_by_branch = defaultdict(lambda: Counter({"officials": 0, "trades": 0, "production_trades": 0}))
    for official in timeline_officials:
        row = timeline_by_branch[official["branch"]]
        row["officials"] += 1
        row["trades"] += len(official.get("trades", []))
        row["production_trades"] += sum(
            1 for trade in official.get("trades", []) if trade.get("public_production_trade") is True
        )
    return {
        "schema_version": "civicledger-coverage-v1",
        "generated_at": dataset["generated_at"],
        "historical_scope": {
            "start_date": "2009-01-20",
            "congresses": list(range(111, 120)),
            "presidential_terms": ["obama-44", "trump-45", "biden-46", "trump-47"],
        },
        "summary": dataset["summary"],
        "record_states": dict(sorted(record_states.items())),
        "timeline_by_branch": {branch: dict(counts) for branch, counts in sorted(timeline_by_branch.items())},
        "event_types": dict(sorted(event_types.items())),
        "event_editor_states": dict(sorted(event_editor_states.items())),
        "sources": [
            {
                "id": source["id"],
                "branch": source["branch"],
                "ingestion_status": source.get("ingestion_status"),
                "readiness": source.get("readiness"),
            }
            for source in dataset.get("sources", [])
        ],
        "release_blockers": [
            *(
                ["No reviewed public production trade rows exist yet."]
                if dataset["summary"].get("reviewed_public_trade_count", 0) == 0
                else []
            ),
            *(
                [
                    f"{dataset['summary'].get('house_ptr_ocr_required_document_count', 0):,} indexed House PTRs are image-only and remain in the OCR/review queue."
                ]
                if dataset["summary"].get("house_ptr_ocr_required_document_count", 0)
                else []
            ),
            "Senate disclosure documents are not ingested because the official portal acknowledgement workflow is not automated.",
            "Judicial disclosure documents are not ingested; the official JEFS requester and acknowledgement workflow remains external.",
            "Executive disclosure coverage beyond the presidential OGE index is incomplete.",
            "The House Clerk's structured periodic-transaction index in this dataset begins in 2015; earlier Obama-era House transaction backfill remains incomplete.",
            "Structured Supreme Court slip-opinion ingestion begins with October Term 2017; official bound-volume backfill for 2009-2016 remains pending.",
        ],
    }


def compact_public_event(event: dict) -> dict:
    keys = [
        "id",
        "date",
        "label",
        "event_type",
        "description",
        "source",
        "source_urls",
        "source_tier",
        "editor_status",
        "branch_scope",
        "sector_scope",
        "asset_scope",
        "jurisdiction_scope",
        "ticker_scope",
        "entity_scope",
        "company_entity_scope",
        "market_topic_ids",
        "market_relevance",
        "law_number",
        "executive_order_number",
        "docket_number",
        "citation",
        "term_year",
    ]
    row = {key: event.get(key) for key in keys if event.get(key) not in (None, "", [], {})}
    for key in ["announcement_date", "effective_date", "publication_date"]:
        value = event.get(key)
        if value and value != event.get("date"):
            row[key] = value
    return row


def write_partition(relative_path: str, payload) -> dict:
    path = ROOT / "pages-site" / "data" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
    path.write_bytes(encoded)
    return {
        "path": relative_path,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def write_public_partitions(dataset: dict) -> None:
    if PUBLIC_PARTITIONS.exists():
        shutil.rmtree(PUBLIC_PARTITIONS)
    PUBLIC_PARTITIONS.mkdir(parents=True, exist_ok=True)

    officials, role_details = compact_official_index(dataset["public_officials"])
    files = {}
    files["overview"] = write_partition(
        "partitions/overview.json",
        {
            "generated_at": dataset["generated_at"],
            "dataset_version": dataset["dataset_version"],
            "methodology_version": dataset["methodology_version"],
            "parser_version": dataset["parser_version"],
            "site_mode": dataset["site_mode"],
            "disclaimer": dataset["disclaimer"],
            "summary": dataset["summary"],
            "sources": dataset["sources"],
            "disclosure_pipeline": dataset["disclosure_pipeline"],
            "presidential_oge_status": dataset["presidential_oge_status"],
            "presidential_oge_documents": {
                "context_label": dataset["presidential_oge_documents"].get("context_label"),
                "summary": dataset["presidential_oge_documents"].get("summary", {}),
                "unavailable_documents": dataset["presidential_oge_documents"].get("unavailable_documents", []),
            },
            "house_disclosures": dataset.get("house_disclosures", {}),
            "federal_event_context": dataset.get("federal_event_context", {}),
        },
    )
    files["officials_index"] = write_partition(
        "partitions/officials-index.json",
        {"schema_version": "official-index-v1", "officials": officials},
    )
    files["coverage"] = write_partition("partitions/coverage.json", coverage_payload(dataset))
    files["events"] = write_partition(
        "partitions/events.json",
        {
            "schema_version": "timeline-events-v2",
            "methodology_version": dataset["career_trade_timeline"].get(
                "event_relationship_methodology_version"
            ),
            "events": [
                compact_public_event(event)
                for event in dataset["career_trade_timeline"].get("events", [])
            ],
        },
    )

    timeline_partitions = {}
    timeline_official_summaries = []
    for official in dataset["career_trade_timeline"].get("officials", []):
        relative = f"partitions/timelines/{public_slug(official['id'])}.json"
        timeline_partitions[official["id"]] = write_partition(
            relative,
            {
                "schema_version": dataset["career_trade_timeline"]["schema_version"],
                "official": official,
            },
        )
        timeline_official_summaries.append(
            {
                "id": official["id"],
                "full_name": official["full_name"],
                "branch": official["branch"],
                "timeline_group": official["timeline_group"],
                "record_status": official.get("stats", {}).get("record_status"),
                "trade_count": len(official.get("trades", [])),
                "event_count": len(official.get("events", [])),
                "service_periods": official.get("service_periods", []),
            }
        )
    files["timeline_index"] = write_partition(
        "partitions/timeline-index.json",
        {
            "schema_version": dataset["career_trade_timeline"]["schema_version"],
            "default_official_ids": dataset["career_trade_timeline"]["default_official_ids"],
            "asset_classes": dataset["career_trade_timeline"]["asset_classes"],
            "event_types": dataset["career_trade_timeline"]["event_types"],
            "summary": dataset["career_trade_timeline"]["summary"],
            "officials": timeline_official_summaries,
        },
    )

    role_partitions = {}
    for branch in ["Legislative", "Executive", "Judicial"]:
        branch_ids = {official["id"] for official in officials if official["branch"] == branch}
        relative = f"partitions/roles/{branch.lower()}.json"
        role_partitions[branch] = write_partition(
            relative,
            {
                "schema_version": "official-role-details-v1",
                "branch": branch,
                "roles_by_official": {
                    official_id: role_details[official_id]
                    for official_id in sorted(branch_ids)
                },
            },
        )

    market_partitions = {}
    market_data = load_json_file(MARKET_PRICES, {"series": {}})
    for symbol, series in sorted(market_data.get("series", {}).items()):
        relative = f"partitions/market/{public_slug(symbol)}.json"
        market_partitions[symbol] = write_partition(
            relative,
            {"symbol": symbol, "source": market_data.get("source", {}), **series},
        )
    crypto_data = load_json_file(CRYPTO_PRICES, {"series": {}})
    for symbol, series in sorted(crypto_data.get("series", {}).items()):
        relative = f"partitions/market/{public_slug(symbol)}.json"
        market_partitions[symbol] = write_partition(
            relative,
            {"symbol": symbol, "source": crypto_data.get("source", {}), **series},
        )
    files["market_index"] = write_partition(
        "partitions/market-index.json",
        {
            "schema_version": "market-partition-index-v1",
            "symbols": sorted(market_partitions),
            "market_summary": market_data.get("summary", {}),
            "crypto_summary": crypto_data.get("summary", {}),
        },
    )

    manifest = {
        "schema_version": "civicledger-public-manifest-v1",
        "generated_at": dataset["generated_at"],
        "dataset_version": dataset["dataset_version"],
        "methodology_version": dataset["methodology_version"],
        "event_relationship_methodology_version": dataset["career_trade_timeline"].get(
            "event_relationship_methodology_version"
        ),
        "files": files,
        "partitions": {
            "timelines": timeline_partitions,
            "roles": role_partitions,
            "market": market_partitions,
        },
    }
    PUBLIC_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def compatibility_snapshot(dataset: dict) -> dict:
    """Keep the retired monolith useful without duplicating every public partition."""
    timeline = dataset["career_trade_timeline"]
    default_ids = set(timeline["default_official_ids"])
    compact_timeline = {
        key: value
        for key, value in timeline.items()
        if key not in {"officials", "event_windows"}
    }
    compact_timeline["officials"] = [
        official for official in timeline["officials"] if official["id"] in default_ids
    ]
    return {
        "schema_version": "civicledger-static-compat-v2",
        "generated_at": dataset["generated_at"],
        "dataset_version": dataset["dataset_version"],
        "methodology_version": dataset["methodology_version"],
        "parser_version": dataset["parser_version"],
        "site_mode": dataset["site_mode"],
        "disclaimer": dataset["disclaimer"],
        "summary": dataset["summary"],
        "sources": dataset["sources"],
        "presidential_oge_status": dataset["presidential_oge_status"],
        "presidential_oge_documents": dataset["presidential_oge_documents"],
        "presidential_oge_transactions": dataset["presidential_oge_transactions"],
        "house_disclosures": dataset["house_disclosures"],
        "disclosure_pipeline": dataset["disclosure_pipeline"],
        "career_trade_timeline": compact_timeline,
        "manifest_path": "manifest.json",
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset()
    write_public_partitions(dataset)
    OUTPUT.write_text(json.dumps(compatibility_snapshot(dataset), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")
    print(f"Wrote {PUBLIC_MANIFEST}")


if __name__ == "__main__":
    main()
