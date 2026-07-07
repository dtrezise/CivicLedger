#!/usr/bin/env python3
"""Build the static data snapshot used by the GitHub Pages edition."""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from datetime import date
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


def market_snapshot() -> dict:
    series = generate_market_series()
    monthly = defaultdict(dict)
    for point in series:
        month = point.date.strftime("%Y-%m")
        monthly[month][point.symbol] = float(point.value)
    return {
        "monthly": [
            {"month": month, **values}
            for month, values in sorted(monthly.items())
            if "SPY" in values and "DIA" in values
        ]
    }


def load_events() -> list[dict]:
    with (FIXTURES / "events" / "events.json").open() as handle:
        return json.load(handle)


def build_dataset() -> dict:
    random.seed(42)
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
            "This public GitHub Pages edition uses fixture/demo data generated from the CivicLedger seed model. "
            "It demonstrates the interface and provenance approach, not a production public disclosure database."
        ),
        "summary": {
            "official_count": len(all_people),
            "filing_count": len(all_filings),
            "trade_count": len(all_trades),
            "raw_document_count": len(all_raw_documents),
            "event_count": len(load_events()),
            "branch_counts": dict(sorted(branch_counts.items())),
        },
        "people": all_people,
        "filings": all_filings,
        "trades": all_trades,
        "raw_documents": all_raw_documents,
        "sources": sources,
        "events": load_events(),
        "market": market_snapshot(),
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
