from datetime import date

from app.services.source_snapshots import (
    build_snapshot_index,
    canonical_source_url,
    event_source_urls,
)


def test_source_url_canonicalization_removes_tracking_and_fragments():
    assert canonical_source_url(
        "HTTPS://Example.GOV/rule?utm_source=test&docket=123#details"
    ) == "https://example.gov/rule?docket=123"


def test_event_source_urls_deduplicate_supported_fields():
    event = {
        "sources": ["https://example.gov/a?utm_medium=email", "https://example.gov/a"],
        "source_url": "https://example.gov/b",
        "publisher": "not-a-url",
    }
    assert event_source_urls(event) == ["https://example.gov/a", "https://example.gov/b"]


def test_snapshot_index_is_deterministic_and_labels_normalized_hash_boundary():
    dataset = {
        "source_dataset": "official-events",
        "source_tier": "official",
        "generated_at": "2026-07-12",
        "events": [
            {
                "id": "event-1",
                "date": "2026-01-02",
                "label": "Official event",
                "sources": ["https://example.gov/event-1"],
            }
        ],
    }
    first = build_snapshot_index([dataset], as_of=date(2026, 7, 12))
    second = build_snapshot_index([dataset], as_of=date(2026, 7, 12))
    assert first == second
    assert first["summary"]["snapshot_count"] == 1
    snapshot = first["snapshots"][0]
    assert len(snapshot["snapshot_id"]) == 64
    assert len(snapshot["source_record_sha256"]) == 64
    assert snapshot["snapshot_kind"] == "normalized_source_record"
    assert snapshot["immutable"] is True
