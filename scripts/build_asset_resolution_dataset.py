#!/usr/bin/env python3
"""Build conservative fund, ETF, and 529 asset-resolution context."""

from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.asset_resolution import (  # noqa: E402
    CURATED_ASSET_REFERENCES,
    asset_resolution_diagnostics,
    asset_resolution_record,
    is_target_asset,
)


HOUSE_TRANSACTION_INDEX = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
PRESIDENTIAL_TRANSACTIONS = ROOT / "data" / "disclosures" / "presidential_oge_transactions.json"
SENATE_TRANSACTIONS = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"
OUTPUT = ROOT / "data" / "context" / "asset_resolution.json"
SCHEMA_VERSION = "asset-resolution-context-v1"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _partition_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def load_transactions(
    house_index_path: Path = HOUSE_TRANSACTION_INDEX,
    presidential_path: Path = PRESIDENTIAL_TRANSACTIONS,
    senate_path: Path = SENATE_TRANSACTIONS,
) -> list[dict]:
    rows: list[dict] = []
    if house_index_path.exists():
        house_index = _read_json(house_index_path)
        partitions = house_index.get("year_partitions", {})
        for year in sorted(partitions, key=str):
            partition = partitions[year]
            partition_path = _partition_path(partition["path"])
            if not partition_path.exists():
                continue
            for transaction in _read_json(partition_path).get("transactions", []):
                rows.append({"source_dataset": "house_ptr_transactions", **transaction})

    if presidential_path.exists():
        for transaction in _read_json(presidential_path).get("transactions", []):
            rows.append({"source_dataset": "presidential_oge_transactions", **transaction})

    if senate_path.exists():
        for transaction in _read_json(senate_path).get("transactions", []):
            rows.append({"source_dataset": "senate_ptr_transactions", **transaction})

    return sorted(
        rows,
        key=lambda row: (
            row.get("trade_date") or "",
            row.get("id") or "",
            row.get("asset_display_name") or "",
        ),
    )


def _resolution_id(normalized_name: str) -> str:
    digest = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()[:16]
    return f"asset-resolution-{digest}"


def _source_record(transaction: dict, resolution: dict) -> dict:
    return {
        "transaction_id": transaction.get("id"),
        "document_id": transaction.get("document_id"),
        "official_id": transaction.get("official_id"),
        "trade_date": transaction.get("trade_date"),
        "source_dataset": transaction.get("source_dataset"),
        "source_record_status": transaction.get("record_status"),
        "public_production_trade": bool(transaction.get("public_production_trade")),
        "review_required_before_public_trade": bool(
            transaction.get("review_required_before_public_trade")
        ),
        "asset_display_name": transaction.get("asset_display_name"),
        "disclosed_asset_class": transaction.get("asset_class"),
        "disclosed_ticker": transaction.get("ticker"),
        **resolution,
    }


def build_dataset(transactions: Iterable[dict], generated_at: str | None = None) -> dict:
    source_rows = sorted(
        list(transactions),
        key=lambda row: (row.get("trade_date") or "", row.get("id") or ""),
    )
    transaction_resolutions = []
    grouped: dict[str, dict] = {}

    for transaction in source_rows:
        asset_name = transaction.get("asset_display_name") or transaction.get("raw_asset_text")
        asset_class = transaction.get("asset_class")
        if not is_target_asset(asset_name, asset_class):
            continue
        resolution = asset_resolution_record(
            asset_name,
            transaction.get("ticker"),
            asset_class,
            transaction.get("trade_date"),
        )
        source_record = _source_record(transaction, resolution)
        transaction_resolutions.append(source_record)

        normalized_name = resolution["normalized_name"]
        aggregate = grouped.setdefault(
            normalized_name,
            {
                "observed_names": set(),
                "transaction_ids": set(),
                "source_datasets": set(),
                "disclosed_asset_classes": set(),
                "disclosed_tickers": set(),
                "occurrence_count": 0,
                "resolution": resolution,
            },
        )
        aggregate["occurrence_count"] += 1
        if asset_name:
            aggregate["observed_names"].add(asset_name)
        if transaction.get("id"):
            aggregate["transaction_ids"].add(transaction["id"])
        if transaction.get("source_dataset"):
            aggregate["source_datasets"].add(transaction["source_dataset"])
        if asset_class:
            aggregate["disclosed_asset_classes"].add(asset_class)
        if transaction.get("ticker"):
            aggregate["disclosed_tickers"].add(transaction["ticker"])

    assets = []
    for normalized_name, aggregate in sorted(grouped.items()):
        transaction_ids = sorted(aggregate["transaction_ids"])
        assets.append(
            {
                "id": _resolution_id(normalized_name),
                "observed_names": sorted(aggregate["observed_names"]),
                "occurrence_count": aggregate["occurrence_count"],
                "transaction_ids": transaction_ids,
                "source_datasets": sorted(aggregate["source_datasets"]),
                "disclosed_asset_classes": sorted(aggregate["disclosed_asset_classes"]),
                "disclosed_tickers": sorted(aggregate["disclosed_tickers"]),
                **aggregate["resolution"],
            }
        )

    transaction_statuses = Counter(
        row["resolution_status"] for row in transaction_resolutions
    )
    asset_statuses = Counter(row["resolution_status"] for row in assets)
    resolved_classes = Counter(
        row["asset_class"]
        for row in transaction_resolutions
        if row["resolution_status"] == "resolved"
    )
    diagnostics = asset_resolution_diagnostics(transaction_resolutions)
    source_year_counts = Counter(
        (
            str(row.get("source_dataset") or "unknown"),
            str(row.get("trade_date") or "unknown")[:4],
        )
        for row in transaction_resolutions
    )
    transaction_ids = [
        str(row["transaction_id"])
        for row in transaction_resolutions
        if row.get("transaction_id")
    ]
    duplicate_transaction_ids = sorted(
        transaction_id
        for transaction_id, count in Counter(transaction_ids).items()
        if count > 1
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or date.today().isoformat(),
        "scope": {
            "target_asset_classes": ["etf", "fund", "mutual_fund", "529_portfolio"],
            "source_datasets": sorted(
                {row.get("source_dataset") for row in source_rows if row.get("source_dataset")}
            ),
            "curated_reference_count": len(CURATED_ASSET_REFERENCES),
        },
        "methodology": {
            "matching": (
                "Exact curated aliases after conservative punctuation, ownership-note, and "
                "disclosure-suffix normalization; otherwise one explicit known symbol token."
            ),
            "fuzzy_matching": False,
            "ticker_guard": (
                "A disclosed ticker is not accepted unless it appears as a standalone token "
                "and belongs to the curated reference table."
            ),
            "unresolved_policy": "Ambiguous or unsupported names remain unresolved.",
            "ticker_history": (
                "Resolved market symbols are evaluated against explicit effective-date ranges using trade_date; "
                "mappings outside a known range remain diagnostic rather than being guessed."
            ),
        },
        "summary": {
            "source_transaction_count": len(source_rows),
            "target_transaction_count": len(transaction_resolutions),
            "resolved_transaction_count": transaction_statuses["resolved"],
            "unresolved_transaction_count": transaction_statuses["unresolved"],
            "unique_asset_name_count": len(assets),
            "resolved_unique_asset_count": asset_statuses["resolved"],
            "unresolved_unique_asset_count": asset_statuses["unresolved"],
            "resolved_transaction_counts_by_asset_class": dict(sorted(resolved_classes.items())),
            "review_required_transaction_count": sum(
                1 for row in transaction_resolutions if row["review_required_before_public_trade"]
            ),
            "stale_or_invalid_mapping_count": diagnostics["stale_or_invalid_mapping_count"],
            "historical_symbol_change_count": diagnostics["historical_symbol_change_count"],
            "missing_effective_date_count": diagnostics["missing_effective_date_count"],
            "duplicate_transaction_id_count": len(duplicate_transaction_ids),
        },
        "coverage_diagnostics": {
            **diagnostics,
            "source_year_counts": {
                f"{source}:{year}": count
                for (source, year), count in sorted(source_year_counts.items())
            },
            "duplicate_transaction_ids": duplicate_transaction_ids,
        },
        "assets": assets,
        "transaction_resolutions": transaction_resolutions,
        "context_label": (
            "Curated identity context only. A resolved name does not change a disclosure's "
            "review or production status, and an unresolved name is not evidence of misconduct."
        ),
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset(load_transactions())
    OUTPUT.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
