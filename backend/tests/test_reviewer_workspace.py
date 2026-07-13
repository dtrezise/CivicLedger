from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import ReviewAssignmentEvent, _reject_relationship_review_mutation
from app.schemas import (
    ReviewAssignmentCreateRequest,
    ReviewFilterCriteria,
    ReviewSavedFilterCreateRequest,
    ReviewSessionCreateRequest,
)


ROOT = Path(__file__).resolve().parents[2]


def test_saved_filter_criteria_are_strict_and_bounded():
    saved = ReviewSavedFilterCreateRequest(
        owner=" Reviewer ",
        name=" High evidence ",
        criteria=ReviewFilterCriteria(
            status="candidate",
            max_abs_days=30,
            min_internal_rank=0.7,
            page_size=50,
        ),
    )
    assert saved.owner == "Reviewer"
    assert saved.name == "High evidence"
    assert saved.criteria.max_abs_days == 30
    with pytest.raises(ValidationError):
        ReviewFilterCriteria(max_abs_days=3651)
    with pytest.raises(ValidationError):
        ReviewSessionCreateRequest(
            reviewer="Reviewer",
            filter_snapshot={"unknown_filter": True},
        )


def test_assignment_payload_and_history_are_attributed_and_append_only():
    payload = ReviewAssignmentCreateRequest(
        candidate_id=uuid4(),
        action="assign",
        assignee=" Analyst ",
        actor=" Lead ",
        note=" Priority queue ",
    )
    assert payload.assignee == "Analyst"
    assert payload.actor == "Lead"
    assert payload.note == "Priority queue"
    assert ReviewAssignmentEvent.__tablename__ == "review_assignment_events"
    with pytest.raises(ValueError, match="immutable"):
        _reject_relationship_review_mutation()


def test_reviewer_workspace_migration_adds_session_link_and_assignment_trigger():
    migration = (
        ROOT
        / "backend"
        / "migrations"
        / "versions"
        / "0007_reviewer_workspaces.py"
    ).read_text()
    assert 'down_revision = "0006_review_immutability"' in migration
    assert '"review_sessions"' in migration
    assert '"review_saved_filters"' in migration
    assert '"review_assignment_events"' in migration
    assert '"review_session_id"' in migration
    assert "BEFORE UPDATE OR DELETE ON review_assignment_events" in migration
