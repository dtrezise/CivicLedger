#!/usr/bin/env python3
"""Build the deterministic canonical entity-reference context dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.entity_reference import build_entity_reference, canonical_json  # noqa: E402
from app.services.market_prices import TICKER_HISTORY, validate_ticker_history  # noqa: E402


ASSET_RESOLUTION = ROOT / "data" / "context" / "asset_resolution.json"
COMPANY_REFERENCE = ROOT / "data" / "context" / "company_entity_reference.json"
SEC_EVENTS = ROOT / "data" / "context" / "sec_filing_events.json"
MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"
HOUSE_INDEX = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
PRESIDENTIAL_TRANSACTIONS = ROOT / "data" / "disclosures" / "presidential_oge_transactions.json"
SENATE_TRANSACTIONS = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"
OUTPUT = ROOT / "data" / "context" / "entity_reference.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(
    source_id: str,
    path: Path,
    payload: dict,
    *,
    source_tier: str,
    artifact_date: str | None = None,
) -> dict:
    return {
        "source_id": source_id,
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _file_sha256(path),
        "schema_version": payload.get("schema_version"),
        "artifact_date": artifact_date
        or payload.get("generated_at")
        or payload.get("artifact_date"),
        "source_tier": source_tier,
    }


def _partition_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_disclosure_rows() -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    snapshots: list[dict] = []

    house_index = _read_json(HOUSE_INDEX)
    snapshots.append(
        _snapshot(
            "house_ptr_transactions:index",
            HOUSE_INDEX,
            house_index,
            source_tier="official_parser_preview",
        )
    )
    for year, partition in sorted(house_index.get("year_partitions", {}).items()):
        path = _partition_path(partition["path"])
        payload = _read_json(path)
        source_id = f"house_ptr_transactions:{year}"
        snapshots.append(
            _snapshot(source_id, path, payload, source_tier="official_parser_preview")
        )
        rows.extend(
            {
                "source_dataset": "house_ptr_transactions",
                "_source_snapshot_id": source_id,
                **transaction,
            }
            for transaction in payload.get("transactions", [])
        )

    for source_id, source_dataset, path in (
        (
            "presidential_oge_transactions",
            "presidential_oge_transactions",
            PRESIDENTIAL_TRANSACTIONS,
        ),
        ("senate_ptr_transactions", "senate_ptr_transactions", SENATE_TRANSACTIONS),
    ):
        payload = _read_json(path)
        snapshots.append(
            _snapshot(source_id, path, payload, source_tier="official_parser_preview")
        )
        rows.extend(
            {
                "source_dataset": source_dataset,
                "_source_snapshot_id": source_id,
                **transaction,
            }
            for transaction in payload.get("transactions", [])
        )

    rows.sort(
        key=lambda row: (
            str(row.get("source_dataset") or ""),
            str(row.get("id") or ""),
        )
    )
    return rows, snapshots


def build_dataset(
    *,
    asset_resolution_path: Path = ASSET_RESOLUTION,
    company_reference_path: Path = COMPANY_REFERENCE,
    sec_events_path: Path = SEC_EVENTS,
    market_prices_path: Path = MARKET_PRICES,
) -> dict:
    asset_resolution = _read_json(asset_resolution_path)
    company_reference = _read_json(company_reference_path)
    sec_events = _read_json(sec_events_path)
    market_prices = _read_json(market_prices_path)
    disclosure_rows, disclosure_snapshots = load_disclosure_rows()

    snapshots = [
        _snapshot(
            "asset_resolution",
            asset_resolution_path,
            asset_resolution,
            source_tier="curated_parser_context",
        ),
        _snapshot(
            "company_entity_reference",
            company_reference_path,
            company_reference,
            source_tier="curated_context",
            artifact_date=market_prices.get("generated_at"),
        ),
        _snapshot(
            "sec_filing_events",
            sec_events_path,
            sec_events,
            source_tier="official",
        ),
        _snapshot(
            "market_prices",
            market_prices_path,
            market_prices,
            source_tier="market_data_provider",
        ),
        {
            "source_id": "market_ticker_history",
            "path": "backend/app/services/market_prices.py#TICKER_HISTORY",
            "sha256": hashlib.sha256(
                canonical_json([row.as_dict() for row in validate_ticker_history()]).encode("utf-8")
            ).hexdigest(),
            "schema_version": "ticker-history-v1",
            "artifact_date": market_prices.get("generated_at"),
            "source_tier": "source_checked_curated_reference",
        },
        {
            "source_id": "disclosure_labels",
            "path": "logical:combined-disclosure-labels",
            "sha256": hashlib.sha256(
                canonical_json(
                    [
                        {
                            "id": row.get("id"),
                            "label": row.get("asset_display_name") or row.get("raw_asset_text"),
                            "ticker": row.get("ticker"),
                            "source_dataset": row.get("source_dataset"),
                        }
                        for row in disclosure_rows
                    ]
                ).encode("utf-8")
            ).hexdigest(),
            "schema_version": "combined-disclosure-labels-v1",
            "artifact_date": max(
                (
                    str(row.get("artifact_date") or "")[:10]
                    for row in disclosure_snapshots
                    if row.get("artifact_date")
                ),
                default=market_prices.get("generated_at"),
            ),
            "source_tier": "official_parser_preview",
        },
        *disclosure_snapshots,
    ]
    return build_entity_reference(
        asset_resolution=asset_resolution,
        company_entity_reference=company_reference,
        sec_filing_events=sec_events,
        market_prices=market_prices,
        disclosure_rows=disclosure_rows,
        ticker_history=[row.as_dict() for row in validate_ticker_history(TICKER_HISTORY)],
        source_snapshots=snapshots,
    )


def write_dataset(dataset: dict, output: Path = OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    dataset = build_dataset()
    write_dataset(dataset, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "dataset_hash": dataset["dataset_hash"],
                **dataset["summary"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
