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
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.asset_resolution import is_target_asset, resolve_asset_name  # noqa: E402
from app.services.market_reactions import (  # noqa: E402
    DEFAULT_WINDOW_SESSIONS,
    MARKET_CONTEXT_LABEL,
    MarketReactionCalculator,
)
from scripts.build_asset_resolution_dataset import load_transactions  # noqa: E402


MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"
OUTPUT = ROOT / "data" / "context" / "trade_market_reactions.json"
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
        resolution = resolve_asset_name(asset_name, transaction.get("ticker"), asset_class)
        if not resolution:
            return None, "unresolved_target_asset"
        return resolution, "resolved_target_asset"

    disclosed_ticker = str(transaction.get("ticker") or "").strip().upper()
    if not disclosed_ticker or not _TICKER_RE.fullmatch(disclosed_ticker):
        return None, "missing_or_invalid_disclosed_ticker"
    reference = _market_reference(market_prices, disclosed_ticker)
    if not reference:
        return None, "missing_market_reference"
    return {
        "resolution_status": "resolved",
        "match_method": "disclosed_ticker_market_reference",
        "identifier_type": "ticker",
        "canonical_name": reference.get("issuer_name"),
        "fund_family": None,
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
) -> dict:
    source_rows = sorted(
        list(transactions),
        key=lambda row: (row.get("trade_date") or "", row.get("id") or ""),
    )
    requested_windows = tuple(sorted({int(value) for value in window_sessions}))
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
        )
        if reaction["status"] == "unavailable":
            skip_reasons[reaction["coverage_reason"]] += 1
            continue
        reactions.append(_row_from_reaction(transaction, reference, reaction))

    statuses = Counter(row["status"] for row in reactions)
    symbols = sorted({row["asset_symbol"] for row in reactions})
    benchmarks = sorted({row["benchmark_symbol"] for row in reactions})
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
            "asset_symbols": symbols,
            "benchmark_symbols": benchmarks,
        },
        "methodology": {
            "anchor": "First common asset and benchmark market date on or after trade_date.",
            "pre_window": "Return from N common trading sessions before the anchor to the anchor.",
            "post_window": "Return from the anchor to N common trading sessions after the anchor.",
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
        },
        "reactions": reactions,
        "context_label": MARKET_CONTEXT_LABEL,
    }


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
    args = parser.parse_args()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset(load_transactions(), load_market_prices(), args.windows)
    OUTPUT.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
