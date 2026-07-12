#!/usr/bin/env python3
"""Build review-gated historical-news context candidates."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.historical_news import (  # noqa: E402
    GDELT_DOC_API_URL,
    GdeltDocHistoricalNewsProvider,
    HistoricalNewsProvider,
    HistoricalNewsQuery,
    ProviderUnavailableError,
)


OUTPUT = ROOT / "data" / "context" / "historical_news_context.json"
CACHE = ROOT / ".cache" / "historical-news"
CONTEXT_NOTE = (
    "News discovery context only. A provider match is not verification of an article's claims "
    "and does not imply causation, intent, legality, ethics, or investment performance."
)
REVIEW_POLICY = {
    "record_status": "news_provider_candidate_not_reviewed",
    "review_status": "pending_human_review",
    "review_required_before_publication": True,
    "public_production_event": False,
}


def _article_id(url: str) -> str:
    return f"news-{hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]}"


def _coverage_status(retrieval_status: str) -> str:
    if retrieval_status == "fetched":
        return "covered"
    if retrieval_status in {"cache_hit", "stale_cache_fallback"}:
        return "cached"
    return retrieval_status


def build_dataset(
    provider: HistoricalNewsProvider,
    queries: list[HistoricalNewsQuery],
    *,
    artifact_date: str,
) -> dict:
    date.fromisoformat(artifact_date)
    ordered_queries = sorted(queries, key=lambda item: item.query_id)
    coverage_report = {}
    events_by_id: dict[str, dict] = {}

    for query in ordered_queries:
        try:
            result = provider.search(query)
        except ProviderUnavailableError as exc:
            coverage_report[query.query_id] = {
                "status": "unavailable",
                "provider": provider.provider_id,
                "article_count": 0,
                "reason": str(exc),
            }
            continue
        except Exception as exc:  # Provider plugins must not abort the artifact run.
            coverage_report[query.query_id] = {
                "status": "unavailable",
                "provider": provider.provider_id,
                "article_count": 0,
                "reason": f"Unexpected provider error ({type(exc).__name__})",
            }
            continue

        coverage_report[query.query_id] = {
            "status": _coverage_status(result.retrieval_status),
            "retrieval_status": result.retrieval_status,
            "provider": provider.provider_id,
            "request_url": result.request_url,
            "article_count": len(result.articles),
            "warnings": list(result.warnings),
        }
        for article in sorted(
            result.articles,
            key=lambda item: (item.published_at or "", item.url, item.title),
        ):
            event_id = _article_id(article.url)
            if event_id not in events_by_id:
                events_by_id[event_id] = {
                    "id": event_id,
                    "date": article.published_at[:10] if article.published_at else None,
                    "published_at": article.published_at,
                    "event_type": "historical_news",
                    "title": article.title,
                    "article_url": article.url,
                    "publisher_domain": article.domain,
                    "language": article.language,
                    "source_country": article.source_country,
                    "image_url": article.image_url,
                    "matched_query_ids": [],
                    "_discovery_urls": [],
                    "source_tier": "news_publisher_via_aggregator",
                    "source_attribution_complete": bool(article.url and result.request_url),
                    **REVIEW_POLICY,
                    "context_note": CONTEXT_NOTE,
                }
            event = events_by_id[event_id]
            event["matched_query_ids"].append(query.query_id)
            event["_discovery_urls"].append(result.request_url)

    events = []
    for event in events_by_id.values():
        discovery_urls = sorted(set(event.pop("_discovery_urls")))
        event["matched_query_ids"] = sorted(set(event["matched_query_ids"]))
        article_source = {
            "role": "article",
            "name": event["publisher_domain"] or "Publisher domain unavailable",
            "url": event["article_url"],
            "source_tier": "news_publisher",
        }
        discovery_sources = [
            {
                "role": "discovery_provider",
                "name": provider.provider_name,
                "url": request_url,
                "source_tier": provider.source_tier,
            }
            for request_url in discovery_urls
        ]
        event["sources"] = [article_source, *discovery_sources]
        event["source_urls"] = [event["article_url"], *discovery_urls]
        events.append(event)
    events.sort(key=lambda event: (event["date"] or "", event["article_url"], event["id"]))

    status_counts = Counter(item["status"] for item in coverage_report.values())
    return {
        "schema_version": "historical-news-context-v1",
        "artifact_date": artifact_date,
        "source": {
            "id": provider.provider_id,
            "name": provider.provider_name,
            "source_tier": provider.source_tier,
            "documentation_url": provider.documentation_url,
        },
        "scope": {
            "description": "Bounded provider-discovered historical-news candidates for research review.",
            "queries": [query.as_dict() for query in ordered_queries],
        },
        "summary": {
            "query_count": len(ordered_queries),
            "event_count": len(events),
            "coverage_status_counts": dict(sorted(status_counts.items())),
            "review_pending_event_count": len(events),
            "public_production_event_count": 0,
        },
        "coverage_report": coverage_report,
        "events": events,
        "ingestion_policy": {
            "review_required_before_publication": True,
            "provider_match_is_verification": False,
            "public_production_event_default": False,
        },
        "context_label": CONTEXT_NOTE,
    }


def parse_query_argument(
    value: str,
    *,
    position: int,
    start_date: str,
    end_date: str,
    max_records: int,
) -> HistoricalNewsQuery:
    query_id = ""
    query_text = value.strip()
    if "=" in query_text:
        candidate_id, candidate_query = query_text.split("=", 1)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", candidate_id.strip()):
            query_id = candidate_id.strip().lower()
            query_text = candidate_query.strip()
    if not query_id:
        digest = hashlib.sha256(query_text.encode("utf-8")).hexdigest()[:8]
        query_id = f"query-{position:03d}-{digest}"
    return HistoricalNewsQuery(
        query_id=query_id,
        query=query_text,
        label=query_text,
        start_date=start_date,
        end_date=end_date,
        max_records=max_records,
    )


def write_artifact(payload: dict) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(OUTPUT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        action="append",
        required=True,
        help="GDELT query, optionally prefixed with a stable id as QUERY_ID=QUERY.",
    )
    parser.add_argument("--start", required=True, help="Inclusive ISO start date.")
    parser.add_argument("--end", default=date.today().isoformat(), help="Inclusive ISO end date.")
    parser.add_argument("--artifact-date", help="Stable ISO artifact date; defaults to --end.")
    parser.add_argument("--max-records", type=int, default=250)
    parser.add_argument("--provider-url", default=GDELT_DOC_API_URL)
    parser.add_argument("--refresh", action="store_true", help="Refresh even when a cache entry exists.")
    args = parser.parse_args()

    queries = [
        parse_query_argument(
            value,
            position=position,
            start_date=args.start,
            end_date=args.end,
            max_records=args.max_records,
        )
        for position, value in enumerate(args.query, start=1)
    ]
    duplicate_ids = [
        query_id
        for query_id, count in Counter(query.query_id for query in queries).items()
        if count > 1
    ]
    if duplicate_ids:
        raise SystemExit(f"Duplicate query ids: {', '.join(sorted(duplicate_ids))}")

    provider = GdeltDocHistoricalNewsProvider(
        base_url=args.provider_url,
        cache_directory=CACHE,
        refresh=args.refresh,
    )
    dataset = build_dataset(
        provider,
        queries,
        artifact_date=args.artifact_date or args.end,
    )
    write_artifact(dataset)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
