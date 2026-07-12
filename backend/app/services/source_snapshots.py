"""Deterministic normalized snapshots for source-linked contextual event records."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def canonical_source_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in TRACKING_QUERY_KEYS
        )
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def normalized_hash(payload: Any) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def event_source_urls(event: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("sources", "source_urls", "request_urls"):
        value = event.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(item for item in value if isinstance(item, str))
    for key in ("source_url", "html_url", "filing_url", "opinion_url"):
        if isinstance(event.get(key), str):
            values.append(event[key])
    return sorted({canonical_source_url(value) for value in values if value.startswith(("http://", "https://"))})


def snapshots_for_events(
    events: Iterable[dict[str, Any]],
    *,
    source_dataset: str,
    generated_at: str | None,
    default_source_tier: str = "official",
) -> list[dict[str, Any]]:
    rows = []
    for position, event in enumerate(events):
        event_id = str(event.get("id") or event.get("event_id") or f"row-{position}")
        record_hash = normalized_hash(event)
        for url in event_source_urls(event):
            snapshot_id = hashlib.sha256(
                f"{source_dataset}\0{event_id}\0{url}\0{record_hash}".encode()
            ).hexdigest()
            rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "event_id": event_id,
                    "event_date": event.get("date") or event.get("filing_date"),
                    "source_dataset": source_dataset,
                    "source_url": url,
                    "source_tier": event.get("source_tier") or default_source_tier,
                    "snapshot_kind": "normalized_source_record",
                    "source_record_sha256": record_hash,
                    "upstream_response_sha256": event.get("response_sha256"),
                    "dataset_generated_at": generated_at,
                    "immutable": True,
                }
            )
    return rows


def build_snapshot_index(datasets: Iterable[dict[str, Any]], *, as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date.today()
    snapshots = []
    for dataset in datasets:
        snapshots.extend(
            snapshots_for_events(
                dataset.get("events", []),
                source_dataset=dataset["source_dataset"],
                generated_at=dataset.get("generated_at"),
                default_source_tier=dataset.get("source_tier", "official"),
            )
        )
    unique = {row["snapshot_id"]: row for row in snapshots}
    ordered = sorted(
        unique.values(),
        key=lambda row: (row["source_dataset"], row["event_date"] or "", row["event_id"], row["source_url"]),
    )
    by_dataset = Counter(row["source_dataset"] for row in ordered)
    return {
        "generated_at": as_of.isoformat(),
        "schema_version": "normalized-source-snapshots-v1",
        "interpretation_boundary": (
            "These hashes freeze normalized CivicLedger source records. They are not a substitute "
            "for an upstream raw-response hash unless upstream_response_sha256 is present."
        ),
        "summary": {
            "snapshot_count": len(ordered),
            "event_count": len({(row["source_dataset"], row["event_id"]) for row in ordered}),
            "counts_by_dataset": dict(sorted(by_dataset.items())),
            "upstream_response_hash_count": sum(
                1 for row in ordered if row.get("upstream_response_sha256")
            ),
        },
        "snapshots": ordered,
    }
