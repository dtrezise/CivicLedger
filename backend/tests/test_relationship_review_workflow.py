from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_sync_db
from app.main import app


CANDIDATE_ID = UUID("10000000-0000-0000-0000-000000000001")
TRADE_ID = UUID("20000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("30000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("40000000-0000-0000-0000-000000000001")
EXISTING_REVIEW_ID = UUID("50000000-0000-0000-0000-000000000001")


class FakeResult:
    def __init__(self, *, scalar=None, row=None, rows=None):
        self.scalar = scalar
        self.row = row
        self.rows = [] if rows is None else rows

    def scalar_one(self):
        return self.scalar

    def scalar_one_or_none(self):
        return self.scalar

    def one_or_none(self):
        return self.row

    def all(self):
        return self.rows

    def scalars(self):
        return self


def make_candidate_row(*, status="candidate"):
    candidate = SimpleNamespace(
        id=CANDIDATE_ID,
        trade_id=TRADE_ID,
        event_id=EVENT_ID,
        days_from_event=3,
        evidence_tier="entity_and_timing",
        relationship_reasons=[
            "Trade falls inside the event window.",
            {"reason": "Asset and event issuer match."},
        ],
        internal_rank=Decimal("0.93"),
        methodology_version="event-relevance-v1",
        review_status=status,
        created_at=datetime(2026, 7, 10, 14, 30, tzinfo=timezone.utc),
    )
    trade = SimpleNamespace(
        id=TRADE_ID,
        person_id=PERSON_ID,
        trade_date=date(2026, 7, 4),
        reported_date=date(2026, 7, 9),
        action="BUY",
        asset_display_name="Example Industries",
        ticker="EXM",
        asset_class="equity",
        value_range_label="$1,001 - $15,000",
    )
    event = SimpleNamespace(
        id=EVENT_ID,
        date=date(2026, 7, 1),
        label="Example agency action",
        event_type="regulatory_action",
        description="Official action affecting Example Industries.",
    )
    person = SimpleNamespace(id=PERSON_ID, full_name="Jordan Example")
    return candidate, trade, event, person


def make_existing_review():
    return SimpleNamespace(
        id=EXISTING_REVIEW_ID,
        candidate_id=CANDIDATE_ID,
        decision="narrow",
        reviewer="First Reviewer",
        reason="Limited to the named issuer and three-day event window.",
        reviewed_at=datetime(2026, 7, 11, 9, 15, tzinfo=timezone.utc),
    )


class WorkflowSession:
    def __init__(self, *, status="candidate", reviews=None, fail_flush=False):
        self.row = make_candidate_row(status=status)
        self.candidate = self.row[0]
        self.reviews = list(reviews or [])
        self.fail_flush = fail_flush
        self.statements = []
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def execute(self, statement):
        self.statements.append(statement)
        sql = str(statement)
        if "JOIN trades" in sql:
            return FakeResult(row=self.row)
        if "relationship_reviews" in sql:
            return FakeResult(rows=self.reviews)
        if statement._for_update_arg is not None:
            return FakeResult(scalar=self.candidate)
        raise AssertionError(f"Unexpected statement: {sql}")

    def add(self, review):
        self.added.append(review)
        self.reviews.append(review)

    def flush(self):
        self.flush_count += 1
        if self.fail_flush:
            raise SQLAlchemyError("database details must not escape")

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class SequenceSession:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError(f"Unexpected statement: {statement}")
        return self.results.pop(0)


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


def test_candidate_queue_filters_by_status_and_returns_history():
    row = make_candidate_row(status="accepted")
    existing_review = make_existing_review()
    session = SequenceSession(
        [
            FakeResult(scalar=1),
            FakeResult(rows=[row]),
            FakeResult(rows=[existing_review]),
        ]
    )

    with client_for(session) as client:
        response = client.get(
            "/review/relationship-candidates",
            params={"status": "accepted", "page": 2, "page_size": 1},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert payload["page_size"] == 1
    assert payload["total"] == 1
    assert payload["items"][0]["review_status"] == "accepted"
    assert payload["items"][0]["person_name"] == "Jordan Example"
    assert payload["items"][0]["reviews"] == [
        {
            "id": str(EXISTING_REVIEW_ID),
            "candidate_id": str(CANDIDATE_ID),
            "decision": "narrow",
            "reviewer": "First Reviewer",
            "evidence_note": "Limited to the named issuer and three-day event window.",
            "reviewed_at": "2026-07-11T09:15:00Z",
        }
    ]
    assert "accepted" in session.statements[0].compile().params.values()
    assert "accepted" in session.statements[1].compile().params.values()
    assert session.results == []


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("accept", "accepted"),
        ("narrow", "narrowed"),
        ("reject", "rejected"),
        ("supersede", "superseded"),
    ],
)
def test_each_decision_appends_attributed_timestamped_history(
    decision, expected_status
):
    existing_review = make_existing_review()
    session = WorkflowSession(reviews=[existing_review])

    with client_for(session) as client:
        response = client.post(
            f"/review/relationship-candidates/{CANDIDATE_ID}/decisions",
            json={
                "decision": decision,
                "reviewer": "  Second Reviewer  ",
                "evidence_note": "  Confirmed against the linked official source.  ",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["review_status"] == expected_status
    assert len(payload["reviews"]) == 2
    assert payload["reviews"][0]["id"] == str(EXISTING_REVIEW_ID)
    assert payload["reviews"][0]["evidence_note"] == existing_review.reason
    assert payload["reviews"][1]["decision"] == decision
    assert payload["reviews"][1]["reviewer"] == "Second Reviewer"
    assert (
        payload["reviews"][1]["evidence_note"]
        == "Confirmed against the linked official source."
    )
    assert (
        datetime.fromisoformat(payload["reviews"][1]["reviewed_at"]).tzinfo is not None
    )
    assert session.added[0].decision == decision
    assert session.candidate.review_status == expected_status
    assert session.flush_count == 1
    assert session.commit_count == 1
    assert session.rollback_count == 0


def test_later_decisions_do_not_replace_earlier_history():
    existing_review = make_existing_review()
    session = WorkflowSession(reviews=[existing_review])

    with client_for(session) as client:
        first = client.post(
            f"/review/relationship-candidates/{CANDIDATE_ID}/decisions",
            json={
                "decision": "accept",
                "reviewer": "Second Reviewer",
                "evidence_note": "Accepted after source comparison.",
            },
        )
        second = client.post(
            f"/review/relationship-candidates/{CANDIDATE_ID}/decisions",
            json={
                "decision": "supersede",
                "reviewer": "Third Reviewer",
                "evidence_note": "A newer methodology produced a replacement candidate.",
            },
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert [review["id"] for review in second.json()["reviews"][:2]] == [
        str(EXISTING_REVIEW_ID),
        first.json()["reviews"][1]["id"],
    ]
    assert [review["decision"] for review in second.json()["reviews"]] == [
        "narrow",
        "accept",
        "supersede",
    ]
    assert session.candidate.review_status == "superseded"
    assert session.commit_count == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "approve", "reviewer": "Reviewer", "evidence_note": "Evidence."},
        {"decision": "accept", "reviewer": "   ", "evidence_note": "Evidence."},
        {"decision": "accept", "reviewer": "Reviewer", "evidence_note": "   "},
        {
            "decision": "accept",
            "reviewer": "Reviewer",
            "evidence_note": "Evidence.",
            "candidate_status": "accepted",
        },
    ],
)
def test_invalid_decision_writes_are_rejected_before_database_use(payload):
    session = WorkflowSession()

    with client_for(session) as client:
        response = client.post(
            f"/review/relationship-candidates/{CANDIDATE_ID}/decisions",
            json=payload,
        )

    assert response.status_code == 422
    assert session.statements == []
    assert session.added == []
    assert session.commit_count == 0


def test_database_failure_rolls_back_and_returns_safe_error():
    session = WorkflowSession(fail_flush=True)

    with client_for(session) as client:
        response = client.post(
            f"/review/relationship-candidates/{CANDIDATE_ID}/decisions",
            json={
                "decision": "reject",
                "reviewer": "Reviewer",
                "evidence_note": "Issuer overlap is unsupported.",
            },
        )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "The relationship decision could not be saved."
    }
    assert "database details" not in response.text
    assert session.flush_count == 1
    assert session.commit_count == 0
    assert session.rollback_count == 1


def test_missing_candidate_returns_404_without_a_write():
    session = SequenceSession([FakeResult(scalar=None)])
    session.added = []
    session.commit_count = 0
    session.rollback_count = 0

    def add(review):
        session.added.append(review)

    def commit():
        session.commit_count += 1

    def rollback():
        session.rollback_count += 1

    session.add = add
    session.flush = lambda: None
    session.commit = commit
    session.rollback = rollback

    with client_for(session) as client:
        response = client.post(
            f"/review/relationship-candidates/{uuid4()}/decisions",
            json={
                "decision": "accept",
                "reviewer": "Reviewer",
                "evidence_note": "Evidence note.",
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Relationship candidate not found."}
    assert session.added == []
    assert session.commit_count == 0
    assert session.rollback_count == 1
