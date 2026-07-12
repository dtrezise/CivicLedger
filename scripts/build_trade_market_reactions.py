#!/usr/bin/env python3
"""Build neutral pre/post market context for disclosure transactions."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.asset_resolution import is_target_asset, resolve_asset_name  # noqa: E402
from app.services.market_prices import resolve_ticker_history  # noqa: E402
from app.services.market_reactions import (  # noqa: E402
    DEFAULT_WINDOW_DAYS,
    DEFAULT_WINDOW_SESSIONS,
    MARKET_CONTEXT_LABEL,
    MarketReactionCalculator,
    market_reaction_coverage_diagnostics,
)
from scripts.build_asset_resolution_dataset import load_transactions  # noqa: E402


MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"
OUTPUT = ROOT / "data" / "context" / "trade_market_reactions.json"
PARTITION_ROOT = ROOT / "data" / "context" / "trade_market_reactions"
SCHEMA_VERSION = "trade-market-context-v1"
_TICKER_RE = re.compile(r"^[A-Z0-9.-]{1,10}$")


def load_market_prices(path: Path = MARKET_PRICES) -> dict:
    return json.loads(path.read_text())


def _market_reference(market_prices: dict, symbol: str) -> dict | None:
    reference = market_prices.get("ticker_reference", {}).get(symbol)
    if reference:
        return {"identifier": symbol, "symbol": symbol, "market_symbol": symbol, **reference}
    series_reference = market_prices.get("series", {}).get(symbol, {}).get("reference")
    if series_reference:
        return {
            "identifier": symbol,
            "symbol": symbol,
            "market_symbol": symbol,
            **series_reference,
        }
    return None


def _transaction_reference(transaction: dict, market_prices: dict) -> tuple[dict | None, str]:
    asset_name = transaction.get("asset_display_name") or transaction.get("raw_asset_text")
    asset_class = transaction.get("asset_class")
    if is_target_asset(asset_name, asset_class):
        resolution = resolve_asset_name(
            asset_name,
            transaction.get("ticker"),
            asset_class,
            transaction.get("trade_date"),
        )
        if not resolution:
            return None, "unresolved_target_asset"
        return resolution, "resolved_target_asset"

    disclosed_ticker = str(transaction.get("ticker") or "").strip().upper()
    if not disclosed_ticker or not _TICKER_RE.fullmatch(disclosed_ticker):
        return None, "missing_or_invalid_disclosed_ticker"
    ticker_mapping = resolve_ticker_history(disclosed_ticker, transaction.get("trade_date"))
    mapped_symbol = ticker_mapping.get("market_symbol")
    if not mapped_symbol:
        return None, f"ticker_history_{ticker_mapping['status']}"
    reference = _market_reference(market_prices, mapped_symbol)
    if not reference:
        return None, "missing_market_reference"
    return {
        "resolution_status": "resolved",
        "match_method": "disclosed_ticker_market_reference",
        "identifier_type": "ticker",
        "canonical_name": reference.get("issuer_name"),
        "fund_family": None,
        "ticker_history_status": ticker_mapping["status"],
        "ticker_history_effective_date": ticker_mapping["effective_date"],
        "ticker_history_mapping": ticker_mapping.get("mapping"),
        **reference,
    }, "disclosed_ticker_market_reference"


def _reaction_id(transaction: dict, symbol: str) -> str:
    source_key = transaction.get("id") or "|".join(
        str(transaction.get(field) or "")
        for field in ("document_id", "official_id", "trade_date", "asset_display_name")
    )
    digest = hashlib.sha256(f"{source_key}|{symbol}".encode("utf-8")).hexdigest()[:16]
    return f"trade-market-context-{digest}"


def _row_from_reaction(transaction: dict, reference: dict, reaction: dict) -> dict:
    return {
        "id": _reaction_id(transaction, reaction["asset_symbol"]),
        "transaction_id": transaction.get("id"),
        "document_id": transaction.get("document_id"),
        "official_id": transaction.get("official_id"),
        "source_dataset": transaction.get("source_dataset"),
        "source_record_status": transaction.get("record_status"),
        "public_production_trade": bool(transaction.get("public_production_trade")),
        "review_required_before_public_trade": bool(
            transaction.get("review_required_before_public_trade")
        ),
        "action": transaction.get("action"),
        "asset_display_name": transaction.get("asset_display_name"),
        "disclosed_asset_class": transaction.get("asset_class"),
        "disclosed_ticker": transaction.get("ticker"),
        "resolved_identifier": reference.get("identifier"),
        "identifier_type": reference.get("identifier_type"),
        "resolution_method": reference.get("match_method"),
        "ticker_history_status": reference.get("ticker_history_status"),
        "ticker_history_effective_date": reference.get("ticker_history_effective_date"),
        "ticker_history_mapping": reference.get("ticker_history_mapping"),
        "canonical_name": reference.get("canonical_name"),
        "issuer_name": reference.get("issuer_name"),
        "fund_family": reference.get("fund_family"),
        "resolved_asset_class": reference.get("asset_class"),
        "sector": reference.get("sector"),
        **reaction,
    }


def build_dataset(
    transactions: Iterable[dict],
    market_prices: dict,
    window_sessions: Iterable[int] = DEFAULT_WINDOW_SESSIONS,
    generated_at: str | None = None,
    window_days: Iterable[int] = DEFAULT_WINDOW_DAYS,
) -> dict:
    source_rows = sorted(
        list(transactions),
        key=lambda row: (row.get("trade_date") or "", row.get("id") or ""),
    )
    requested_windows = tuple(sorted({int(value) for value in window_sessions}))
    requested_day_windows = tuple(sorted({int(value) for value in window_days}))
    calculator = MarketReactionCalculator(market_prices)
    reactions = []
    skip_reasons: Counter[str] = Counter()

    for transaction in source_rows:
        trade_date = transaction.get("trade_date")
        if not trade_date:
            skip_reasons["missing_trade_date"] += 1
            continue
        reference, reference_status = _transaction_reference(transaction, market_prices)
        if not reference:
            skip_reasons[reference_status] += 1
            continue

        asset_symbol = reference["market_symbol"].upper()
        benchmark_symbol = str(reference.get("benchmark_symbol") or "").upper()
        if not benchmark_symbol:
            skip_reasons["missing_benchmark_mapping"] += 1
            continue
        reaction = calculator.compute(
            asset_symbol,
            benchmark_symbol,
            trade_date,
            requested_windows,
            requested_day_windows,
        )
        if reaction["status"] == "unavailable":
            skip_reasons[reaction["coverage_reason"]] += 1
            continue
        reactions.append(_row_from_reaction(transaction, reference, reaction))

    statuses = Counter(row["status"] for row in reactions)
    symbols = sorted({row["asset_symbol"] for row in reactions})
    benchmarks = sorted({row["benchmark_symbol"] for row in reactions})
    reaction_diagnostics = market_reaction_coverage_diagnostics(reactions)
    reaction_ids = [row["id"] for row in reactions]
    duplicate_reaction_ids = sorted(
        reaction_id
        for reaction_id, count in Counter(reaction_ids).items()
        if count > 1
    )
    symbol_year_partitions = partition_reactions_by_symbol_year(reactions)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or date.today().isoformat(),
        "source": {
            "market_prices_path": "data/context/market_prices.json",
            "market_prices_generated_at": market_prices.get("generated_at"),
            "market_price_source": market_prices.get("source", {}),
        },
        "scope": {
            "source_datasets": sorted(
                {row.get("source_dataset") for row in source_rows if row.get("source_dataset")}
            ),
            "window_unit": "common_trading_sessions",
            "requested_session_counts": list(requested_windows),
            "requested_calendar_day_counts": list(requested_day_windows),
            "asset_symbols": symbols,
            "benchmark_symbols": benchmarks,
            "symbol_year_partition_count": len(symbol_year_partitions),
        },
        "methodology": {
            "anchor": "First common asset and benchmark market date on or after trade_date.",
            "pre_window": "Return from N common trading sessions before the anchor to the anchor.",
            "post_window": "Return from the anchor to N common trading sessions after the anchor.",
            "calendar_windows": (
                "Neutral 7/30/90-day windows use the last common market date on or before the pre target and "
                "the first common market date on or after the post target."
            ),
            "benchmark_adjustment": "asset_return_pct minus benchmark_return_pct",
            "price_field": "Adjusted close when present; otherwise close.",
            "trade_action_treatment": (
                "BUY, SELL, and EXCHANGE labels are retained but do not change the sign of returns."
            ),
            "coverage_policy": (
                "Rows require a direct asset series, an explicit benchmark mapping, and at "
                "least one complete pre or post window."
            ),
        },
        "summary": {
            "source_transaction_count": len(source_rows),
            "market_context_row_count": len(reactions),
            "covered_row_count": statuses["covered"],
            "partial_row_count": statuses["partial"],
            "skipped_transaction_count": sum(skip_reasons.values()),
            "skip_counts_by_reason": dict(sorted(skip_reasons.items())),
            "distinct_asset_symbol_count": len(symbols),
            "distinct_benchmark_symbol_count": len(benchmarks),
            "review_required_context_row_count": sum(
                1 for row in reactions if row["review_required_before_public_trade"]
            ),
            "complete_calendar_window_count": reaction_diagnostics[
                "complete_calendar_window_count"
            ],
            "missing_provider_provenance_count": reaction_diagnostics[
                "missing_provider_provenance_count"
            ],
            "duplicate_reaction_id_count": len(duplicate_reaction_ids),
        },
        "coverage_diagnostics": {
            **reaction_diagnostics,
            "duplicate_reaction_ids": duplicate_reaction_ids,
            "symbol_year_partitions": symbol_year_partitions,
        },
        "reactions": reactions,
        "context_label": MARKET_CONTEXT_LABEL,
    }


def partition_reactions_by_symbol_year(reactions: Iterable[dict]) -> dict[str, dict]:
    grouped: Counter[tuple[str, str]] = Counter()
    for row in reactions:
        symbol = str(row.get("asset_symbol") or "").upper()
        year = str(row.get("event_date") or "")[:4]
        if symbol and len(year) == 4 and year.isdigit():
            grouped[(symbol, year)] += 1
    return {
        f"{symbol}:{year}": {
            "symbol": symbol,
            "year": int(year),
            "reaction_count": count,
            "path": f"trade_market_reactions/{symbol.lower()}/{year}.json",
        }
        for (symbol, year), count in sorted(grouped.items())
    }


def _canonical_partition_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def write_partitioned_dataset(
    dataset: dict,
    output: Path = OUTPUT,
    partition_root: Path = PARTITION_ROOT,
) -> dict:
    """Write a compact manifest plus independently verifiable symbol-year shards."""

    reactions = sorted(
        dataset.get("reactions", []),
        key=lambda row: (
            str(row.get("asset_symbol") or ""),
            str(row.get("event_date") or ""),
            str(row.get("id") or ""),
        ),
    )
    grouped: dict[tuple[str, int], list[dict]] = {}
    for row in reactions:
        symbol = str(row.get("asset_symbol") or "").upper()
        year_text = str(row.get("event_date") or "")[:4]
        if not symbol or len(year_text) != 4 or not year_text.isdigit():
            raise ValueError(f"Reaction {row.get('id')} has no partitionable symbol/year")
        grouped.setdefault((symbol, int(year_text)), []).append(row)

    if partition_root.exists():
        shutil.rmtree(partition_root)
    partition_root.mkdir(parents=True, exist_ok=True)

    partition_records = {}
    for (symbol, year), rows in sorted(grouped.items()):
        relative_path = Path("trade_market_reactions") / symbol.lower() / f"{year}.json"
        path = output.parent / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "trade-market-context-partition-v1",
            "generated_at": dataset.get("generated_at"),
            "symbol": symbol,
            "year": year,
            "reaction_count": len(rows),
            "reactions": rows,
        }
        encoded = _canonical_partition_bytes(payload)
        path.write_bytes(encoded)
        partition_records[f"{symbol}:{year}"] = {
            "symbol": symbol,
            "year": year,
            "reaction_count": len(rows),
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "path": relative_path.as_posix(),
        }

    manifest = {key: value for key, value in dataset.items() if key != "reactions"}
    manifest["storage"] = {
        "format": "symbol_year_partitions",
        "partition_schema_version": "trade-market-context-partition-v1",
        "partition_count": len(partition_records),
        "reaction_count": len(reactions),
        "partitions": partition_records,
    }
    manifest.setdefault("coverage_diagnostics", {})["symbol_year_partitions"] = partition_records
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def _parse_windows(value: str) -> tuple[int, ...]:
    windows = tuple(sorted({int(item.strip()) for item in value.split(",") if item.strip()}))
    if not windows or any(item <= 0 for item in windows):
        raise argparse.ArgumentTypeError("windows must be positive comma-separated integers")
    return windows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--windows",
        type=_parse_windows,
        default=DEFAULT_WINDOW_SESSIONS,
        help="Common trading-session windows, comma separated (default: 1,5,20).",
    )
    parser.add_argument(
        "--day-windows",
        type=_parse_windows,
        default=DEFAULT_WINDOW_DAYS,
        help="Calendar-day windows, comma separated (default: 7,30,90).",
    )
    args = parser.parse_args()

    dataset = build_dataset(
        load_transactions(),
        load_market_prices(),
        args.windows,
        window_days=args.day_windows,
    )
    manifest = write_partitioned_dataset(dataset)
    print(
        f"Wrote {OUTPUT} with {manifest['storage']['partition_count']} partitions "
        f"and {manifest['storage']['reaction_count']} reactions"
    )


if __name__ == "__main__":
    main()
