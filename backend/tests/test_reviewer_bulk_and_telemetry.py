from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from app.database import get_sync_db
from app.main import app
from app.models import _reject_relationship_review_mutation
from app.routes.review import _review_revision
from app.services.reviewer_telemetry import (
    build_baseline,
    build_telemetry,
    snapshot_source,
)


CANDIDATE_ONE = UUID("10000000-0000-0000-0000-000000000001")
CANDIDATE_TWO = UUID("10000000-0000-0000-0000-000000000002")
TRADE_ONE = UUID("20000000-0000-0000-0000-000000000001")
TRADE_TWO = UUID("20000000-0000-0000-0000-000000000002")
EVENT_ONE = UUID("30000000-0000-0000-0000-000000000001")
EVENT_TWO = UUID("30000000-0000-0000-0000-000000000002")
PERSON_ID = UUID("40000000-0000-0000-0000-000000000001")
REVIEW_ID = UUID("50000000-0000-0000-0000-000000000001")


class FakeResult:
    def __init__(self, *, rows=None):
        self.rows = [] if rows is None else rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


def candidate_row(candidate_id, trade_id, event_id):
    candidate = SimpleNamespace(
        id=candidate_id,
        trade_id=trade_id,
        event_id=event_id,
        days_from_event=2,
        evidence_tier="entity_and_timing",
        relationship_reasons=["Official-source entity match."],
        internal_rank=Decimal("0.80"),
        methodology_version="event-relevance-v1",
        review_status="candidate",
        created_at=datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc),
    )
    trade = SimpleNamespace(
        id=trade_id,
        person_id=PERSON_ID,
        trade_date=date(2026, 7, 10),
        reported_date=date(2026, 7, 11),
        action="BUY",
        asset_display_name="Example Industries",
        ticker="EXM",
        asset_class="equity",
        value_range_label="$1,001 - $15,000",
    )
    event = SimpleNamespace(
        id=event_id,
        date=date(2026, 7, 8),
        label="Example official event",
        event_type="regulatory_action",
        description="Official event description.",
    )
    person = SimpleNamespace(id=PERSON_ID, full_name="Jordan Example")
    return candidate, trade, event, person


class BulkSession:
    def __init__(self):
        self.rows = [
            candidate_row(CANDIDATE_ONE, TRADE_ONE, EVENT_ONE),
            candidate_row(CANDIDATE_TWO, TRADE_TWO, EVENT_TWO),
        ]
        self.reviews = []
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.flush_count = 0

    def execute(self, statement):
        sql = str(statement)
        if "JOIN trades" in sql:
            return FakeResult(rows=self.rows)
        if "relationship_reviews" in sql:
            return FakeResult(rows=self.reviews)
        if statement._for_update_arg is not None:
            return FakeResult(rows=[row[0] for row in self.rows])
        raise AssertionError(f"Unexpected statement: {sql}")

    def add(self, review):
        self.added.append(review)
        self.reviews.append(review)

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class AuditSession:
    def __init__(self):
        self.candidate = candidate_row(CANDIDATE_ONE, TRADE_ONE, EVENT_ONE)[0]
        self.review = SimpleNamespace(
            id=REVIEW_ID,
            candidate_id=CANDIDATE_ONE,
            decision="accept",
            reviewer="Audit Reviewer",
            reason="Matched against the linked official record.",
            reviewed_at=datetime(2026, 7, 12, 13, 0, tzinfo=timezone.utc),
        )

    def execute(self, statement):
        assert "relationship_reviews" in str(statement)
        return FakeResult(rows=[(self.review, self.candidate)])


@contextmanager
def client_for(session):
    def override_get_sync_db():
        yield session

    app.dependency_overrides[get_sync_db] = override_get_sync_db
    app.openapi_schema = None
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.openapi_schema = None


def bulk_payload(revision):
    return {
        "decision": "accept",
        "reviewer": "  Bulk Reviewer  ",
        "evidence_note": "  Same evidence boundary applies to this selected set.  ",
        "targets": [
            {
                "candidate_id": str(CANDIDATE_ONE),
                "expected_status": "candidate",
                "expected_revision": revision,
            },
            {
                "candidate_id": str(CANDIDATE_TWO),
                "expected_status": "candidate",
                "expected_revision": revision,
            },
        ],
    }


def test_bulk_decision_is_atomic_and_appends_one_review_per_candidate():
    session = BulkSession()
    revision = _review_revision("candidate", [])

    with client_for(session) as client:
        response = client.post(
            "/review/relationship-candidates/bulk-decisions",
            json=bulk_payload(revision),
        )

    assert response.status_code == 201
    assert response.json()["updated_count"] == 2
    assert {item["review_status"] for item in response.json()["items"]} == {"accepted"}
    assert len(session.added) == 2
    assert {review.reviewer for review in session.added} == {"Bulk Reviewer"}
    assert len({review.reviewed_at for review in session.added}) == 1
    assert session.flush_count == 1
    assert session.commit_count == 1
    assert session.rollback_count == 0


def test_bulk_decision_rejects_one_stale_target_without_any_write():
    session = BulkSession()
    payload = bulk_payload(_review_revision("candidate", []))
    payload["targets"][1]["expected_revision"] = "0" * 64

    with client_for(session) as client:
        response = client.post(
            "/review/relationship-candidates/bulk-decisions",
            json=payload,
        )

    assert response.status_code == 409
    assert str(CANDIDATE_TWO) in response.json()["detail"]
    assert session.added == []
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert all(row[0].review_status == "candidate" for row in session.rows)


def test_relationship_audit_export_is_content_addressed_and_deterministic():
    session = AuditSession()

    with client_for(session) as client:
        first = client.get("/review/relationship-audit-history/export")
        second = client.get("/review/relationship-audit-history/export")

    assert first.status_code == 200
    assert first.content == second.content
    assert first.headers["etag"] == second.headers["etag"]
    assert "attachment; filename=\"relationship-audit-" in first.headers[
        "content-disposition"
    ]
    payload = first.json()
    assert payload["record_count"] == 1
    assert payload["records"][0]["review_id"] == str(REVIEW_ID)
    assert payload["export_id"].endswith(payload["content_sha256"][:16])
    assert len(payload["content_sha256"]) == 64


def test_relationship_review_model_rejects_mutation():
    with pytest.raises(ValueError, match="append a new review"):
        _reject_relationship_review_mutation()


def test_reviewer_telemetry_is_deterministic_and_separates_signal_types():
    original = snapshot_source(
        source_id="source-a",
        path="data/source-a.json",
        payload={"schema_version": "v1", "summary": {"record_count": 10}},
        count_metric="record_count",
    )
    changed = snapshot_source(
        source_id="source-a",
        path="data/source-a.json",
        payload={"schema_version": "v1", "summary": {"record_count": 12}},
        count_metric="record_count",
    )
    baseline = build_baseline([original], captured_at="2026-07-11")
    arguments = {
        "runs": [
            {
                "run_id": "run-1",
                "source_id": "source-a",
                "status": "success",
                "started_at": "2026-07-12T12:00:00Z",
                "completed_at": "2026-07-12T12:00:10Z",
                "failure_count": 0,
            },
            {
                "run_id": "run-2",
                "source_id": "source-b",
                "status": "failed",
                "started_at": "2026-07-12T13:00:00Z",
                "completed_at": "2026-07-12T13:00:20Z",
                "failure_count": 2,
            },
        ],
        "current_snapshots": [changed],
        "baseline": baseline,
        "failure_observations": [],
        "generated_at": "2026-07-12",
    }

    first = build_telemetry(**arguments)
    second = build_telemetry(**arguments)

    assert first == second
    assert first["status"] == "attention"
    assert first["refresh_duration"]["p50"] == 10.0
    assert first["refresh_duration"]["p95"] == 20.0
    assert first["summary"]["source_failure_count"] == 2
    assert first["summary"]["data_drift_count"] == 1
    assert first["data_drift"][0]["baseline_record_count"] == 10
    assert first["data_drift"][0]["current_record_count"] == 12


def test_reviewer_telemetry_artifact_is_exposed_by_api():
    with TestClient(app) as client:
        response = client.get("/review/telemetry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "reviewer-source-telemetry-v1"
    assert set(payload["summary"]) == {
        "refresh_run_count",
        "measured_refresh_count",
        "failed_refresh_count",
        "source_failure_count",
        "data_drift_count",
    }
