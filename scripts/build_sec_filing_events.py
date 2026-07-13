#!/usr/bin/env python3
"""Build review-gated SEC filing-event candidates from official EDGAR data."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.sec_edgar import (  # noqa: E402
    ProviderUnavailableError,
    SecCompanyRequest,
    SecEdgarOfficialProvider,
    SecFiling,
    SecFilingProvider,
    normalize_cik,
    sec_filing_index_url,
    sec_primary_document_url,
)


OUTPUT = ROOT / "data" / "context" / "sec_filing_events.json"
CACHE = ROOT / ".cache" / "sec-edgar"
ISSUER_ALIASES = ROOT / "data" / "context" / "sec_issuer_aliases.json"
DEFAULT_START = "2009-01-20"
DEFAULT_FORMS = (
    "6-K",
    "8-K",
    "8-K/A",
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "20-F",
    "40-F",
    "DEF 14A",
)
CONTEXT_NOTE = (
    "Official filing-presence context only. Inclusion does not establish the materiality of a "
    "filing to a trade and does not imply causation, intent, legality, ethics, or investment performance."
)
REVIEW_POLICY = {
    "record_status": "official_sec_filing_candidate_not_reviewed",
    "review_status": "pending_human_review",
    "review_required_before_publication": True,
    "public_production_event": False,
}
DEFAULT_SEED_ISSUERS = (
    ("alphabet", "0001652044"),
    ("amazon", "0001018724"),
    ("apple", "0000320193"),
    ("jpmorgan", "0000019617"),
    ("microsoft", "0000789019"),
    ("nvidia", "0001045810"),
)
DEFAULT_MAX_ALIAS_ISSUERS = 54


def _coverage_status(retrieval_status: str) -> str:
    if retrieval_status == "fetched":
        return "covered"
    if retrieval_status in {"cache_hit", "stale_cache_fallback"}:
        return "cached"
    return retrieval_status


def _filing_event(filing: SecFiling, company: dict, request_id: str) -> dict:
    filing_index = sec_filing_index_url(filing.cik, filing.accession_number)
    primary_document = sec_primary_document_url(
        filing.cik,
        filing.accession_number,
        filing.primary_document,
    )
    sources = [
        {
            "role": "filing_index",
            "name": "SEC EDGAR filing index",
            "url": filing_index,
            "source_tier": "official",
        }
    ]
    if primary_document:
        sources.append(
            {
                "role": "primary_document",
                "name": filing.primary_document_description or filing.primary_document,
                "url": primary_document,
                "source_tier": "official",
            }
        )
    atom_source = "browse-edgar" in filing.source_url and "output=atom" in filing.source_url
    sources.append(
        {
            "role": "filing_feed" if atom_source else "submissions_data",
            "name": "SEC EDGAR company Atom feed" if atom_source else "SEC EDGAR submissions JSON",
            "url": filing.source_url,
            "source_tier": "official",
        }
    )
    source_urls = [source["url"] for source in sources]
    return {
        "id": f"sec-filing:{filing.cik}:{filing.accession_number}",
        "date": filing.filing_date,
        "event_type": "sec_filing",
        "title": f"{filing.company_name} filed {filing.form}",
        "company": company,
        "filing": {
            "accession_number": filing.accession_number,
            "form": filing.form,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "accepted_at": filing.accepted_at,
            "file_number": filing.file_number,
            "items": list(filing.items),
            "primary_document": filing.primary_document,
            "is_xbrl": filing.is_xbrl,
            "is_inline_xbrl": filing.is_inline_xbrl,
        },
        "matched_request_ids": [request_id],
        "source_tier": "official",
        "source_attribution_complete": True,
        "sources": sources,
        "source_urls": source_urls,
        **REVIEW_POLICY,
        "context_note": CONTEXT_NOTE,
    }


def build_dataset(
    provider: SecFilingProvider,
    requests: list[SecCompanyRequest],
    *,
    artifact_date: str,
    selection_policy: dict | None = None,
) -> dict:
    date.fromisoformat(artifact_date)
    ordered_requests = sorted(requests, key=lambda item: item.request_id)
    coverage_report = {}
    events_by_id: dict[str, dict] = {}

    for request in ordered_requests:
        try:
            result = provider.filings(request)
        except ProviderUnavailableError as exc:
            coverage_report[request.request_id] = {
                "status": "unavailable",
                "provider": provider.provider_id,
                "cik": request.cik,
                "filing_count": 0,
                "reason": str(exc),
            }
            continue
        except Exception as exc:  # Provider plugins must not abort the artifact run.
            coverage_report[request.request_id] = {
                "status": "unavailable",
                "provider": provider.provider_id,
                "cik": request.cik,
                "filing_count": 0,
                "reason": f"Unexpected provider error ({type(exc).__name__})",
            }
            continue

        coverage_report[request.request_id] = {
            "status": _coverage_status(result.retrieval_status),
            "retrieval_status": result.retrieval_status,
            "provider": provider.provider_id,
            "cik": request.cik,
            "company_name": result.company.get("name"),
            "request_urls": list(result.request_urls),
            "filing_count": len(result.filings),
            "warnings": list(result.warnings),
        }
        for filing in sorted(
            result.filings,
            key=lambda item: (item.filing_date, item.accession_number),
        ):
            event = _filing_event(filing, result.company, request.request_id)
            existing = events_by_id.get(event["id"])
            if existing is None:
                events_by_id[event["id"]] = event
            else:
                existing["matched_request_ids"] = sorted(
                    set(existing["matched_request_ids"] + [request.request_id])
                )

    events = sorted(
        events_by_id.values(),
        key=lambda event: (event["date"], event["filing"]["accession_number"]),
    )
    status_counts = Counter(item["status"] for item in coverage_report.values())
    return {
        "schema_version": "sec-filing-events-v1",
        "artifact_date": artifact_date,
        "source": {
            "id": provider.provider_id,
            "name": provider.provider_name,
            "source_tier": provider.source_tier,
            "documentation_url": provider.documentation_url,
        },
        "scope": {
            "description": "Bounded official SEC filing events for issuer-context review.",
            "requests": [request.as_dict() for request in ordered_requests],
            "selection_policy": selection_policy or {
                "method": "explicit_request_list",
            },
        },
        "summary": {
            "request_count": len(ordered_requests),
            "event_count": len(events),
            "coverage_status_counts": dict(sorted(status_counts.items())),
            "review_pending_event_count": len(events),
            "public_production_event_count": 0,
        },
        "coverage_report": coverage_report,
        "events": events,
        "ingestion_policy": {
            "review_required_before_publication": True,
            "filing_presence_establishes_trade_relevance": False,
            "public_production_event_default": False,
        },
        "context_label": CONTEXT_NOTE,
    }


def parse_cik_argument(
    value: str,
    *,
    start_date: str,
    end_date: str,
    forms: tuple[str, ...],
) -> SecCompanyRequest:
    request_id = ""
    cik_value = value.strip()
    if "=" in cik_value:
        candidate_id, candidate_cik = cik_value.split("=", 1)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", candidate_id.strip()):
            request_id = candidate_id.strip().lower()
            cik_value = candidate_cik.strip()
    cik = normalize_cik(cik_value)
    if not request_id:
        request_id = f"cik-{cik}"
    return SecCompanyRequest(
        request_id=request_id,
        cik=cik,
        start_date=start_date,
        end_date=end_date,
        forms=forms,
    )


def requests_from_issuer_aliases(
    payload: dict,
    *,
    start_date: str,
    end_date: str,
    forms: tuple[str, ...],
    excluded_ciks: set[str],
    maximum_issuers: int,
) -> list[SecCompanyRequest]:
    if maximum_issuers < 0:
        raise ValueError("maximum_issuers cannot be negative")
    selected = []
    seen_ciks = set(excluded_ciks)
    ordered = sorted(
        payload.get("records", []),
        key=lambda row: (
            -int(row.get("occurrence_count") or 0),
            str(row.get("ticker") or ""),
            str(row.get("cik") or ""),
        ),
    )
    for row in ordered:
        if len(selected) >= maximum_issuers:
            break
        try:
            cik = normalize_cik(row.get("cik"))
        except (TypeError, ValueError):
            continue
        ticker = str(row.get("ticker") or "").strip().lower()
        if cik in seen_ciks or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,14}", ticker):
            continue
        request_id = f"alias-{re.sub(r'[^a-z0-9]+', '-', ticker).strip('-')}"
        selected.append(
            SecCompanyRequest(
                request_id=request_id,
                cik=cik,
                start_date=start_date,
                end_date=end_date,
                forms=forms,
                label=str(row.get("official_name") or "").strip() or None,
            )
        )
        seen_ciks.add(cik)
    return selected


def write_artifact(payload: dict) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(OUTPUT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cik",
        action="append",
        help="Issuer CIK, optionally prefixed with a stable id as REQUEST_ID=CIK.",
    )
    parser.add_argument("--start", default=DEFAULT_START, help="Inclusive ISO start date.")
    parser.add_argument("--end", default=date.today().isoformat(), help="Inclusive ISO end date.")
    parser.add_argument("--artifact-date", help="Stable ISO artifact date; defaults to --end.")
    parser.add_argument(
        "--forms",
        default=",".join(DEFAULT_FORMS),
        help="Comma-separated exact SEC form names; pass an empty string for all forms.",
    )
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SEC_EDGAR_USER_AGENT"),
        help="SEC-compliant organization and contact identity header.",
    )
    parser.add_argument("--refresh", action="store_true", help="Refresh even when cache entries exist.")
    parser.add_argument(
        "--issuer-aliases",
        type=Path,
        default=ISSUER_ALIASES,
        help="Deterministic SEC issuer-alias evidence artifact used for bounded expansion.",
    )
    parser.add_argument(
        "--include-alias-issuers",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--max-alias-issuers", type=int, default=DEFAULT_MAX_ALIAS_ISSUERS)
    args = parser.parse_args()

    forms = tuple(form.strip().upper() for form in args.forms.split(",") if form.strip())
    cik_arguments = args.cik or [f"{request_id}={cik}" for request_id, cik in DEFAULT_SEED_ISSUERS]
    requests = [
        parse_cik_argument(
            value,
            start_date=args.start,
            end_date=args.end,
            forms=forms,
        )
        for value in cik_arguments
    ]
    if args.include_alias_issuers:
        alias_payload = json.loads(args.issuer_aliases.read_text())
        requests.extend(
            requests_from_issuer_aliases(
                alias_payload,
                start_date=args.start,
                end_date=args.end,
                forms=forms,
                excluded_ciks={request.cik for request in requests},
                maximum_issuers=args.max_alias_issuers,
            )
        )
    duplicate_ids = [
        request_id
        for request_id, count in Counter(request.request_id for request in requests).items()
        if count > 1
    ]
    if duplicate_ids:
        raise SystemExit(f"Duplicate request ids: {', '.join(sorted(duplicate_ids))}")

    provider = SecEdgarOfficialProvider(
        user_agent=args.user_agent,
        cache_directory=CACHE,
        refresh=args.refresh,
    )
    dataset = build_dataset(
        provider,
        requests,
        artifact_date=args.artifact_date or args.end,
        selection_policy={
            "method": "six_seed_issuers_plus_dynamic_ranked_supported_alias_issuers",
            "alias_evidence_path": args.issuer_aliases.relative_to(ROOT).as_posix()
            if args.issuer_aliases.is_relative_to(ROOT)
            else str(args.issuer_aliases),
            "alias_rank": ["occurrence_count_desc", "ticker_asc", "cik_asc"],
            "maximum_additional_issuers": args.max_alias_issuers,
            "unsupported_or_ambiguous_aliases_included": False,
        },
    )
    write_artifact(dataset)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
