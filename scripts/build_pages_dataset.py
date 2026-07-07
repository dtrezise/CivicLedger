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


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "pages-site" / "data" / "civicledger-static.json"
PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
FRED_CONTEXT = ROOT / "data" / "context" / "fred_market_context.json"
MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"
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
        "monthly": [
            {"month": month, **values}
            for month, values in sorted(monthly.items())
            if all(symbol in values for symbol in MARKET_SYMBOLS)
        ]
    }


def load_events() -> list[dict]:
    with (FIXTURES / "events" / "events.json").open() as handle:
        return json.load(handle)


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
                "ticker": trade["ticker"],
                "value_range_label": trade["value_range_label"],
                "disclosure_lag_days": trade["disclosure_lag_days"],
                "market_moves": [
                    move
                    for move in [
                        market_move(points_by_symbol, "SPY", trade["trade_date"], 30),
                        market_move(points_by_symbol, "QQQ", trade["trade_date"], 30),
                        market_move(points_by_symbol, "DIA", trade["trade_date"], 30),
                    ]
                    if move
                ],
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
    sources = []
    for source in OFFICIAL_SOURCES:
        counts = source_counts[source["id"]]
        sources.append(
            {
                **source,
                "fixture_counts": counts,
                "readiness": {
                    "status": "preview",
                    "label": "Static demo data",
                    "missing_capabilities": [
                        "production official-source ingestion",
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
        "fred_context": fred_context,
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
