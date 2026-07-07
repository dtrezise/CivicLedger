#!/usr/bin/env python3
"""Build the static data snapshot used by the GitHub Pages edition."""

from __future__ import annotations

import json
import random
import re
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
PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
FRED_CONTEXT = ROOT / "data" / "context" / "fred_market_context.json"
MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"
CRYPTO_PRICES = ROOT / "data" / "context" / "crypto_prices.json"
CURATED_TIMELINE_EVENTS = ROOT / "data" / "context" / "timeline_events.json"
PRESIDENTIAL_OGE_STATUS = ROOT / "data" / "disclosures" / "presidential_oge_disclosure_status.json"
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
    with (FIXTURES / "events" / "events.json").open() as handle:
        fixture_events = json.load(handle)
    if not CURATED_TIMELINE_EVENTS.exists():
        return fixture_events
    curated = json.loads(CURATED_TIMELINE_EVENTS.read_text())
    return fixture_events + curated.get("events", [])


def load_presidential_oge_status() -> dict:
    if not PRESIDENTIAL_OGE_STATUS.exists():
        return {
            "context_label": "Presidential OGE disclosure source status has not been generated.",
            "summary": {"official_status_count": 0, "reviewed_trade_count": 0},
            "officials": [],
            "source": {},
        }
    return json.loads(PRESIDENTIAL_OGE_STATUS.read_text())


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


def timeline_event_rows(fred_context: dict, civic_events: list[dict]) -> list[dict]:
    rows = []
    for index, event in enumerate(civic_events, start=1):
        rows.append(
            {
                "id": f"civic-event-{index:03d}",
                "date": event["date"],
                "label": event["label"],
                "event_type": event["event_type"],
                "description": event.get("description") or "",
                "source": event.get("source") or "CivicLedger fixture event",
                "relevance": "general",
                "source_urls": event.get("sources", []),
                "branch_scope": event.get("branch_scope", []),
                "sector_scope": event.get("sector_scope", []),
                "asset_scope": event.get("asset_scope", []),
                "jurisdiction_scope": event.get("jurisdiction_scope", []),
                "editor_status": event.get("editor_status", "fixture"),
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
                "source_urls": event.get("source_urls", []),
                "branch_scope": ["Executive", "Legislative", "Judicial"],
                "sector_scope": ["Broad Market"],
                "asset_scope": [],
                "jurisdiction_scope": ["macro"],
                "editor_status": "system_generated",
            }
        )
    return sorted(rows, key=lambda item: (item["date"], item["id"]))


def service_bounds(roles: list[dict], trades: list[dict]) -> tuple[str | None, str | None]:
    starts = [role.get("service_start") for role in roles if role.get("service_start")]
    starts += [trade.get("trade_date") for trade in trades if trade.get("trade_date")]
    ends = [role.get("service_end") for role in roles if role.get("service_end")]
    ends += [trade.get("trade_date") for trade in trades if trade.get("trade_date")]
    if any(role.get("service_start") and not role.get("service_end") for role in roles):
        ends.append(date.today().isoformat())
    return (min(starts) if starts else None, max(ends) if ends else None)


def days_from_anchor(value: str | None, anchor: str | None) -> int | None:
    if not value or not anchor:
        return None
    return (parse_iso_date(value) - parse_iso_date(anchor)).days


def timeline_trade_row(trade: dict, anchor: str | None, crypto_points_by_symbol: dict[str, list[dict]]) -> dict:
    reference = asset_reference(trade.get("ticker"), trade.get("asset_class"))
    midpoint = value_midpoint(trade)
    row = {
        "id": trade["id"],
        "date": trade["trade_date"],
        "career_day": days_from_anchor(trade.get("trade_date"), anchor),
        "reported_date": trade["reported_date"],
        "action": trade["action"],
        "ticker": normalize_asset_symbol(trade.get("ticker")),
        "asset_display_name": trade["asset_display_name"],
        "asset_class": reference.get("asset_class") or trade.get("asset_class") or "unknown",
        "sector": reference.get("sector", "Unmapped"),
        "value_range_label": trade["value_range_label"],
        "value_midpoint": midpoint,
        "disclosure_lag_days": trade["disclosure_lag_days"],
        "record_status": trade.get("record_status", "fixture_demo"),
        "confidence_label": trade.get("confidence_label", "Fixture/demo trade"),
        "parsing_confidence": trade.get("parsing_confidence"),
    }
    if row["asset_class"] == "crypto":
        row["price_window"] = crypto_price_window(row["ticker"], row["date"], crypto_points_by_symbol)
    return row


def event_relevance(event: dict, official: dict, trades: list[dict]) -> dict:
    score = 35
    reasons = []
    event_type = event.get("event_type", "")
    branch = official.get("branch")
    sectors = {trade.get("sector") for trade in trades if trade.get("sector")}
    asset_classes = {trade.get("asset_class") for trade in trades if trade.get("asset_class")}
    branch_scope = set(event.get("branch_scope") or [])
    sector_scope = set(event.get("sector_scope") or [])
    asset_scope = set(event.get("asset_scope") or [])
    jurisdiction_scope = {str(item).lower() for item in event.get("jurisdiction_scope") or []}
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
    if event.get("relevance") == "macro":
        score += 20
        reasons.append("macro context")
    if branch_scope and branch in branch_scope:
        score += 18
        reasons.append("branch scope match")
    if sector_scope and sectors.intersection(sector_scope):
        score += 16
        reasons.append("sector overlap")
    if asset_scope and asset_classes.intersection(asset_scope):
        score += 16
        reasons.append("asset-class overlap")
    if jurisdiction_scope and any(scope in role_text for scope in jurisdiction_scope):
        score += 12
        reasons.append("office or jurisdiction overlap")
    if branch == "Executive" and event_type in {"executive_order", "policy_change", "macro_release"}:
        score += 18
        reasons.append("executive-adjacent event")
    if branch == "Legislative" and event_type in {"bill", "funding", "macro_release"}:
        score += 18
        reasons.append("legislative-adjacent event")
    if branch == "Judicial" and event_type in {"court_decision", "ruling"}:
        score += 18
        reasons.append("judicial-adjacent event")
    if trades and any(trade.get("asset_class") == "crypto" for trade in trades) and "crypto" in event_type:
        score += 20
        reasons.append("crypto asset overlap")
    if trades and not reasons:
        reasons.append("selected official has reviewed trades")
    return {
        "score": min(score, 100),
        "reason": ", ".join(reasons) if reasons else "general public context",
    }


def timeline_event_positions(
    events: list[dict],
    anchor: str | None,
    start: str | None,
    end: str | None,
    official: dict,
    trades: list[dict],
) -> list[dict]:
    if not start or not end:
        return []
    start_date = parse_iso_date(start)
    end_date = parse_iso_date(end)
    rows = []
    for event in events:
        event_date = parse_iso_date(event["date"])
        if start_date - timedelta(days=180) <= event_date <= end_date + timedelta(days=180):
            relevance = event_relevance(event, official, trades)
            rows.append(
                {
                    **event,
                    "career_day": days_from_anchor(event["date"], anchor),
                    "relevance_score": relevance["score"],
                    "relevance_reason": relevance["reason"],
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
    fred_context: dict,
    civic_events: list[dict],
    crypto_prices: dict,
    presidential_oge_status: dict,
) -> dict:
    roles_by_person = public_roles_by_person(public_officials)
    trades_by_person = defaultdict(list)
    for trade in all_trades:
        trades_by_person[trade["person_id"]].append(trade)

    public_people_by_id = {person["external_person_id"]: person for person in public_officials.get("people", [])}
    president_ids = []
    official_rows = []
    events = timeline_event_rows(fred_context, civic_events)
    oge_by_official = defaultdict(list)
    for status in presidential_oge_status.get("officials", []):
        oge_by_official[status["official_id"]].append(status)
    crypto_points_by_symbol = {
        symbol: series.get("points", [])
        for symbol, series in crypto_prices.get("series", {}).items()
    }

    for external_id, roles in roles_by_person.items():
        presidential_roles = [
            role
            for role in roles
            if role.get("role_title") == "President" and role.get("role_category") == "elected_executive"
        ]
        if not presidential_roles:
            continue
        person = public_people_by_id.get(external_id, {})
        start, end = service_bounds(presidential_roles, [])
        president_ids.append(external_id)
        official_rows.append(
            {
                "id": external_id,
                "full_name": person.get("full_name", external_id),
                "branch": "Executive",
                "timeline_group": "presidential_baseline",
                "service_start": start,
                "service_end": end,
                "roles": presidential_roles,
                "trades": [],
                "disclosure_sources": oge_by_official.get(external_id, []),
                "events": timeline_event_positions(
                    events,
                    start,
                    start,
                    end,
                    {"branch": "Executive", "roles": presidential_roles},
                    [],
                ),
                "trade_clusters": [],
                "stats": {
                    "trade_count": 0,
                    "buy_count": 0,
                    "sell_count": 0,
                    "crypto_count": 0,
                    "total_value_midpoint": 0,
                    "disclosure_status": (
                        "OGE source identified; no reviewed presidential trade disclosures promoted yet"
                        if oge_by_official.get(external_id)
                        else "No reviewed presidential trade disclosures ingested yet"
                    ),
                    "record_status": "source_status_only",
                    "confidence_label": "Source status only",
                },
            }
        )

    for person in fixture_people:
        person_trades = sorted(trades_by_person.get(person["id"], []), key=lambda item: (item["trade_date"], item["id"]))
        start, end = service_bounds(
            [
                {
                    "service_start": person.get("service_start"),
                    "service_end": person.get("service_end"),
                    "role_title": person.get("office") or person.get("chamber") or person.get("branch"),
                    "role_category": "fixture_trade_official",
                    "source_tier": "fixture",
                }
            ],
            person_trades,
        )
        timeline_trades = [timeline_trade_row(trade, start, crypto_points_by_symbol) for trade in person_trades]
        official_rows.append(
            {
                "id": person["id"],
                "full_name": person["full_name"],
                "branch": person["branch"],
                "timeline_group": "fixture_trade_preview",
                "service_start": start,
                "service_end": end,
                "roles": [
                    {
                        "service_start": person.get("service_start"),
                        "service_end": person.get("service_end"),
                        "role_title": person.get("office") or person.get("chamber") or person.get("branch"),
                        "role_category": "fixture_trade_official",
                        "source_tier": "fixture",
                    }
                ],
                "trades": timeline_trades,
                "disclosure_sources": [],
                "events": timeline_event_positions(events, start, start, end, person, timeline_trades),
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

    event_windows = []
    for event in events:
        event_date = parse_iso_date(event["date"])
        event_windows.append(
            {
                **event,
                "window_days": 180,
                "official_trade_counts": {
                    official["id"]: sum(
                        1
                        for trade in official["trades"]
                        if abs((parse_iso_date(trade["date"]) - event_date).days) <= 180
                    )
                    for official in official_rows
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
        "schema_version": "career-trade-timeline-v1",
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
        },
        "officials": official_rows,
        "events": events,
        "event_windows": event_windows,
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
    market_series, market_metadata = load_market_prices()
    crypto_prices = load_crypto_prices()
    presidential_oge_status = load_presidential_oge_status()
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

    branch_counts = Counter(person["branch"] for person in all_people)
    career_timeline = career_trade_timeline(
        public_officials,
        all_people,
        all_trades,
        fred_context,
        civic_events,
        crypto_prices,
        presidential_oge_status,
    )
    sources = []
    for source in OFFICIAL_SOURCES:
        counts = source_counts[source["id"]]
        status_label = {
            "parser_preview_ready": "Parser preview ready",
            "source_index_ready": "Source index ready",
            "planned": "Planned",
        }.get(source.get("ingestion_status"), source.get("ingestion_status", "Planned"))
        sources.append(
            {
                **source,
                "fixture_counts": counts,
                "readiness": {
                    "status": source.get("ingestion_status", "planned"),
                    "label": status_label,
                    "missing_capabilities": [
                        "reviewed production official-source ingestion",
                        "reviewed public filing promotion",
                    ],
                },
            }
        )

    return {
        "generated_at": date.today().isoformat(),
        "dataset_version": settings.DATASET_VERSION,
        "methodology_version": settings.METHODOLOGY_VERSION,
        "parser_version": settings.PARSER_VERSION,
        "site_mode": "public_static_demo",
        "disclaimer": (
            "This public GitHub Pages edition combines fixture/demo financial-disclosure records with "
            "a source-backed public-official role roster for legislative, executive, and judicial branch buildout. "
            "It demonstrates the interface and provenance approach, not a production public disclosure database."
        ),
        "summary": {
            "official_count": len(all_people),
            "tracked_public_official_count": public_officials["summary"]["person_count"],
            "public_official_role_count": public_officials["summary"]["role_count"],
            "filing_count": len(all_filings),
            "trade_count": len(all_trades),
            "raw_document_count": len(all_raw_documents),
            "event_count": len(civic_events),
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
            "branch_counts": dict(sorted(branch_counts.items())),
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


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
