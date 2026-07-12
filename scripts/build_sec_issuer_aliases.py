#!/usr/bin/env python3
"""Build conservative issuer-alias evidence from official SEC ticker data."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import os
from pathlib import Path
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.entity_reference import (  # noqa: E402
    issuer_name_matches,
    normalize_name,
    stable_hash,
)
from app.services.sec_edgar import (  # noqa: E402
    SEC_COMPANY_TICKERS_URL,
    SecEdgarSubmissionsProvider,
    SecIssuerTickerResult,
)
OUTPUT = ROOT / "data" / "context" / "sec_issuer_aliases.json"
CACHE = ROOT / ".cache" / "sec-edgar"
DEFAULT_MIN_OCCURRENCES = 20
HOUSE_INDEX = ROOT / "data" / "disclosures" / "house_ptr_transactions.json"
PRESIDENTIAL_TRANSACTIONS = ROOT / "data" / "disclosures" / "presidential_oge_transactions.json"
SENATE_TRANSACTIONS = ROOT / "data" / "disclosures" / "senate_ptr_transactions.json"
MARKET_PRICES = ROOT / "data" / "context" / "market_prices.json"


def load_disclosure_rows() -> list[dict]:
    rows = []
    house_index = json.loads(HOUSE_INDEX.read_text())
    for partition in house_index.get("year_partitions", {}).values():
        path = Path(partition["path"])
        if not path.is_absolute():
            path = ROOT / path
        payload = json.loads(path.read_text())
        rows.extend(
            {"source_dataset": "house_ptr_transactions", **transaction}
            for transaction in payload.get("transactions", [])
        )
    for source_dataset, path in (
        ("presidential_oge_transactions", PRESIDENTIAL_TRANSACTIONS),
        ("senate_ptr_transactions", SENATE_TRANSACTIONS),
    ):
        payload = json.loads(path.read_text())
        rows.extend(
            {"source_dataset": source_dataset, **transaction}
            for transaction in payload.get("transactions", [])
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("source_dataset") or ""),
            str(row.get("id") or ""),
        ),
    )


def load_supported_tickers() -> set[str]:
    market_prices = json.loads(MARKET_PRICES.read_text())
    return {
        ticker.upper()
        for ticker in (market_prices.get("ticker_reference") or {})
        if _symbol(ticker)
    }


def _symbol(value: object) -> str | None:
    candidate = str(value or "").strip().upper()
    if not candidate or len(candidate) > 15:
        return None
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
    return candidate if candidate[0].isalnum() and set(candidate) <= allowed else None


def _observations(disclosure_rows: Iterable[dict]) -> dict[str, dict[str, dict]]:
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in disclosure_rows:
        ticker = _symbol(row.get("ticker"))
        label = str(row.get("asset_display_name") or row.get("raw_asset_text") or "").strip()
        normalized = normalize_name(label)
        if not ticker or not normalized:
            continue
        aggregate = grouped[ticker].setdefault(
            normalized,
            {
                "alias": label,
                "normalized_alias": normalized,
                "occurrence_count": 0,
                "source_datasets": set(),
                "sample_transaction_ids": set(),
                "asset_classes": set(),
            },
        )
        if (label.casefold(), label) < (
            aggregate["alias"].casefold(),
            aggregate["alias"],
        ):
            aggregate["alias"] = label
        aggregate["occurrence_count"] += 1
        if row.get("source_dataset"):
            aggregate["source_datasets"].add(str(row["source_dataset"]))
        if row.get("id"):
            aggregate["sample_transaction_ids"].add(str(row["id"]))
        if row.get("asset_class"):
            aggregate["asset_classes"].add(str(row["asset_class"]))
    return grouped


def build_dataset(
    ticker_result: SecIssuerTickerResult,
    disclosure_rows: Iterable[dict],
    *,
    artifact_date: str,
    minimum_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    excluded_supported_tickers: set[str] | None = None,
) -> dict:
    date.fromisoformat(artifact_date)
    if minimum_occurrences < 1:
        raise ValueError("minimum_occurrences must be positive")

    observations = _observations(disclosure_rows)
    excluded_supported_tickers = {
        ticker.upper() for ticker in (excluded_supported_tickers or set())
    }
    sec_by_ticker: dict[str, list] = defaultdict(list)
    for record in ticker_result.records:
        sec_by_ticker[record.ticker].append(record)

    records = []
    gaps = []
    eligible_tickers = [
        ticker
        for ticker, aliases in observations.items()
        if ticker not in excluded_supported_tickers
        if sum(item["occurrence_count"] for item in aliases.values())
        >= minimum_occurrences
    ]
    for ticker in sorted(eligible_tickers):
        aliases = observations[ticker]
        candidates = sec_by_ticker.get(ticker, [])
        identities = sorted({(item.cik, item.company_name) for item in candidates})
        total_occurrences = sum(item["occurrence_count"] for item in aliases.values())
        if not identities:
            gaps.append(
                {
                    "id": f"sec-alias-gap:{ticker}",
                    "ticker": ticker,
                    "gap_type": "ticker_not_in_sec_reference",
                    "occurrence_count": total_occurrences,
                    "observed_aliases": sorted(item["alias"] for item in aliases.values()),
                }
            )
            continue
        if len(identities) != 1:
            gaps.append(
                {
                    "id": f"sec-alias-gap:{ticker}",
                    "ticker": ticker,
                    "gap_type": "ambiguous_sec_ticker",
                    "occurrence_count": total_occurrences,
                    "candidate_issuers": [
                        {"cik": cik, "official_name": company_name}
                        for cik, company_name in identities
                    ],
                    "observed_aliases": sorted(item["alias"] for item in aliases.values()),
                }
            )
            continue

        cik, company_name = identities[0]
        accepted = []
        rejected = []
        observed_asset_classes = set()
        for normalized, alias in sorted(aliases.items()):
            row = {
                "alias": alias["alias"],
                "normalized_alias": normalized,
                "occurrence_count": alias["occurrence_count"],
                "source_datasets": sorted(alias["source_datasets"]),
                "sample_transaction_ids": sorted(alias["sample_transaction_ids"])[:10],
                "match_method": "unique_sec_ticker_and_exact_issuer_name_core",
            }
            if issuer_name_matches(company_name, alias["alias"], ticker=ticker):
                accepted.append(row)
                observed_asset_classes.update(alias["asset_classes"])
            else:
                rejected.append(row)
        accepted_occurrences = sum(item["occurrence_count"] for item in accepted)
        if accepted_occurrences >= minimum_occurrences:
            matched_candidates = [
                item for item in candidates if (item.cik, item.company_name) == identities[0]
            ]
            exchanges = sorted(
                {item.exchange for item in matched_candidates if item.exchange}
            )
            records.append(
                {
                    "id": f"sec-issuer-alias:{cik}:{ticker}",
                    "cik": cik,
                    "official_name": company_name,
                    "ticker": ticker,
                    "exchanges": exchanges,
                    "source_url": ticker_result.request_url,
                    "occurrence_count": accepted_occurrences,
                    "observed_asset_classes": sorted(observed_asset_classes),
                    "aliases": accepted,
                }
            )
        elif accepted:
            gaps.append(
                {
                    "id": f"sec-alias-gap:{ticker}:below-frequency-threshold",
                    "ticker": ticker,
                    "gap_type": "supported_alias_below_frequency_threshold",
                    "cik": cik,
                    "official_name": company_name,
                    "occurrence_count": accepted_occurrences,
                    "minimum_occurrences": minimum_occurrences,
                    "observed_aliases": [item["alias"] for item in accepted],
                }
            )
        if rejected or not accepted:
            gaps.append(
                {
                    "id": f"sec-alias-gap:{ticker}:name-mismatch",
                    "ticker": ticker,
                    "gap_type": "issuer_name_mismatch",
                    "cik": cik,
                    "official_name": company_name,
                    "occurrence_count": sum(
                        item["occurrence_count"] for item in rejected
                    ),
                    "observed_aliases": [item["alias"] for item in rejected],
                }
            )

    records.sort(key=lambda item: (item["cik"], item["ticker"]))
    gaps.sort(key=lambda item: item["id"])
    gap_counts = Counter(item["gap_type"] for item in gaps)
    dataset = {
        "schema_version": "sec-issuer-alias-evidence-v1",
        "artifact_date": artifact_date,
        "source": {
            "id": "sec-company-tickers-exchange",
            "name": "SEC company tickers and exchanges",
            "source_tier": "official",
            "request_url": ticker_result.request_url,
            "retrieval_status": ticker_result.retrieval_status,
            "warnings": list(ticker_result.warnings),
        },
        "scope": {
            "minimum_ticker_occurrences": minimum_occurrences,
            "matching_policy": (
                "A disclosure alias is supported only when its ticker maps to one SEC issuer "
                "and its normalized issuer-name core exactly matches the official SEC name."
            ),
            "fuzzy_matching": False,
            "historical_ticker_inference": False,
            "already_supported_ticker_count": len(excluded_supported_tickers),
        },
        "summary": {
            "observed_ticker_count": len(observations),
            "eligible_high_frequency_ticker_count": len(eligible_tickers),
            "supported_ticker_count": len(records),
            "supported_alias_count": sum(len(item["aliases"]) for item in records),
            "supported_occurrence_count": sum(
                item["occurrence_count"] for item in records
            ),
            "gap_count": len(gaps),
            "gap_counts": dict(sorted(gap_counts.items())),
        },
        "records": records,
        "gaps": gaps,
        "context_label": (
            "Official identity evidence only. A supported issuer alias does not establish "
            "ownership, event relevance, trade relevance, or causation."
        ),
    }
    dataset["dataset_hash"] = stable_hash(dataset)
    return dataset


def write_artifact(payload: dict, output: Path = OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-date", default=date.today().isoformat())
    parser.add_argument("--minimum-occurrences", type=int, default=DEFAULT_MIN_OCCURRENCES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SEC_EDGAR_USER_AGENT"),
        help="SEC-compliant organization and contact identity header.",
    )
    parser.add_argument("--provider-url", default=SEC_COMPANY_TICKERS_URL)
    args = parser.parse_args(argv)

    provider = SecEdgarSubmissionsProvider(
        user_agent=args.user_agent,
        cache_directory=CACHE,
        company_tickers_url=args.provider_url,
        refresh=args.refresh,
    )
    ticker_result = provider.company_tickers()
    disclosure_rows = load_disclosure_rows()
    dataset = build_dataset(
        ticker_result,
        disclosure_rows,
        artifact_date=args.artifact_date,
        minimum_occurrences=args.minimum_occurrences,
        excluded_supported_tickers=load_supported_tickers(),
    )
    write_artifact(dataset, args.output)
    print(json.dumps({"output": str(args.output), **dataset["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
