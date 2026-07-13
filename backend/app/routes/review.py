from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db, get_sync_db
from app.models import (
    Event,
    Person,
    RelationshipReview,
    ReviewAssignmentEvent,
    ReviewSavedFilter,
    ReviewSession,
    Trade,
    TradeEventCandidate,
)
from app.schemas import (
    FilingDetail,
    ParserArtifactListResponse,
    PromotePreviewRequest,
    PromotePreviewResponse,
    RelationshipAuditExportRecord,
    RelationshipAuditExportResponse,
    RelationshipBulkReviewCreateRequest,
    RelationshipBulkReviewResponse,
    RelationshipCandidateSort,
    RelationshipCandidateStatus,
    RelationshipReviewCreateRequest,
    RelationshipReviewDecision,
    RelationshipReviewHistoryItem,
    ReviewAssignmentAction,
    ReviewAssignmentCreateRequest,
    ReviewAssignmentItem,
    ReviewSavedFilterCreateRequest,
    ReviewSavedFilterItem,
    ReviewSessionCloseRequest,
    ReviewSessionCreateRequest,
    ReviewSessionItem,
    ReviewerTelemetryResponse,
    RollbackFilingRequest,
    RollbackFilingResponse,
    SupersedeFilingRequest,
    TradeEventCandidateReviewItem,
    TradeEventCandidateReviewListResponse,
)
from app.services.promotion import (
    promote_preview_artifact,
    rollback_promoted_filing,
    supersede_filing,
)

router = APIRouter(prefix="/review", tags=["review"])
ROOT = Path(__file__).resolve().parents[3]
REVIEWER_TELEMETRY = ROOT / "data" / "operations" / "source_refresh_telemetry.json"

DECISION_STATUS = {
    RelationshipReviewDecision.ACCEPT: RelationshipCandidateStatus.ACCEPTED,
    RelationshipReviewDecision.NARROW: RelationshipCandidateStatus.NARROWED,
    RelationshipReviewDecision.REJECT: RelationshipCandidateStatus.REJECTED,
    RelationshipReviewDecision.SUPERSEDE: RelationshipCandidateStatus.SUPERSEDED,
}


def _review_history(
    db: Session, candidate_ids: list[UUID]
) -> dict[UUID, list[RelationshipReviewHistoryItem]]:
    history: dict[UUID, list[RelationshipReviewHistoryItem]] = defaultdict(list)
    if not candidate_ids:
        return history

    reviews = (
        db.execute(
            select(RelationshipReview)
            .where(RelationshipReview.candidate_id.in_(candidate_ids))
            .order_by(RelationshipReview.reviewed_at, RelationshipReview.id)
        )
        .scalars()
        .all()
    )
    for review in reviews:
        history[review.candidate_id].append(
            RelationshipReviewHistoryItem(
                id=review.id,
                candidate_id=review.candidate_id,
                decision=review.decision,
                reviewer=review.reviewer,
                evidence_note=review.reason,
                reviewed_at=review.reviewed_at,
            )
        )
    return history


def _candidate_select():
    return (
        select(TradeEventCandidate, Trade, Event, Person)
        .join(Trade, Trade.id == TradeEventCandidate.trade_id)
        .join(Event, Event.id == TradeEventCandidate.event_id)
        .join(Person, Person.id == Trade.person_id)
    )


def _candidate_item(
    row,
    history: dict[UUID, list[RelationshipReviewHistoryItem]],
) -> TradeEventCandidateReviewItem:
    candidate, trade, event, person = row
    reasons = (
        candidate.relationship_reasons
        if isinstance(candidate.relationship_reasons, list)
        else []
    )
    normalized_reasons = [
        reason if isinstance(reason, (str, dict)) else {"value": str(reason)}
        for reason in reasons
    ]
    candidate_history = history.get(candidate.id, [])
    return TradeEventCandidateReviewItem(
        id=candidate.id,
        trade_id=candidate.trade_id,
        event_id=candidate.event_id,
        person_id=trade.person_id,
        person_name=person.full_name,
        trade_date=trade.trade_date,
        reported_date=trade.reported_date,
        action=trade.action,
        asset_display_name=trade.asset_display_name,
        ticker=trade.ticker,
        asset_class=trade.asset_class,
        value_range_label=trade.value_range_label,
        event_date=event.date,
        event_label=event.label,
        event_type=event.event_type,
        event_description=event.description,
        days_from_event=candidate.days_from_event,
        evidence_tier=candidate.evidence_tier,
        relationship_reasons=normalized_reasons,
        internal_rank=candidate.internal_rank,
        methodology_version=candidate.methodology_version,
        review_status=candidate.review_status,
        review_revision=_review_revision(candidate.review_status, candidate_history),
        created_at=candidate.created_at,
        reviews=candidate_history,
    )


def _review_revision(
    status: str, history: list[RelationshipReviewHistoryItem]
) -> str:
    revision_state = {
        "review_ids": [str(review.id) for review in history],
        "status": status,
    }
    encoded = json.dumps(
        revision_state, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _load_candidate(
    db: Session, candidate_id: UUID
) -> TradeEventCandidateReviewItem | None:
    row = db.execute(
        _candidate_select().where(TradeEventCandidate.id == candidate_id)
    ).one_or_none()
    if row is None:
        return None
    history = _review_history(db, [candidate_id])
    return _candidate_item(row, history)


def _validated_session(
    db: Session, session_id: UUID | None, reviewer: str
) -> ReviewSession | None:
    if session_id is None:
        return None
    session = db.execute(
        select(ReviewSession).where(ReviewSession.id == session_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Review session not found.")
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Review session is already completed.")
    if session.reviewer.casefold() != reviewer.strip().casefold():
        raise HTTPException(
            status_code=409,
            detail="The decision reviewer must match the active review session.",
        )
    return session


def _session_item(db: Session, session: ReviewSession) -> ReviewSessionItem:
    counts = dict(
        db.execute(
            select(RelationshipReview.decision, func.count(RelationshipReview.id))
            .where(RelationshipReview.review_session_id == session.id)
            .group_by(RelationshipReview.decision)
        ).all()
    )
    return ReviewSessionItem(
        id=session.id,
        reviewer=session.reviewer,
        status=session.status,
        filter_snapshot=session.filter_snapshot or {},
        started_at=session.started_at,
        completed_at=session.completed_at,
        decision_count=sum(counts.values()),
        decision_counts={str(key): int(value) for key, value in sorted(counts.items())},
    )


@router.get("/telemetry", response_model=ReviewerTelemetryResponse)
def get_reviewer_telemetry():
    if not REVIEWER_TELEMETRY.exists():
        raise HTTPException(
            status_code=503,
            detail="Reviewer telemetry artifact is unavailable.",
        )
    try:
        return json.loads(REVIEWER_TELEMETRY.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Reviewer telemetry artifact is invalid.",
        ) from exc


@router.get("/assignments", response_model=list[ReviewAssignmentItem])
def list_assignment_events(
    candidate_id: UUID | None = None,
    assignee: str | None = Query(None, min_length=1, max_length=200),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db),
):
    statement = select(ReviewAssignmentEvent)
    if candidate_id is not None:
        statement = statement.where(ReviewAssignmentEvent.candidate_id == candidate_id)
    if assignee:
        statement = statement.where(ReviewAssignmentEvent.assignee == assignee.strip())
    rows = db.execute(
        statement.order_by(
            ReviewAssignmentEvent.occurred_at.desc(), ReviewAssignmentEvent.id.desc()
        ).limit(limit)
    ).scalars().all()
    return [
        ReviewAssignmentItem(
            id=row.id,
            candidate_id=row.candidate_id,
            action=row.action,
            assignee=row.assignee,
            actor=row.actor,
            note=row.note,
            occurred_at=row.occurred_at,
        )
        for row in rows
    ]


@router.post("/assignments", response_model=ReviewAssignmentItem, status_code=201)
def create_assignment_event(
    payload: ReviewAssignmentCreateRequest,
    db: Session = Depends(get_sync_db),
):
    if payload.action == ReviewAssignmentAction.ASSIGN and not payload.assignee:
        raise HTTPException(status_code=422, detail="Assign actions require an assignee.")
    exists = db.execute(
        select(TradeEventCandidate.id).where(
            TradeEventCandidate.id == payload.candidate_id
        )
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="Relationship candidate not found.")
    row = ReviewAssignmentEvent(
        id=uuid4(),
        candidate_id=payload.candidate_id,
        action=payload.action.value,
        assignee=payload.assignee,
        actor=payload.actor,
        note=payload.note,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return ReviewAssignmentItem(
        id=row.id,
        candidate_id=row.candidate_id,
        action=row.action,
        assignee=row.assignee,
        actor=row.actor,
        note=row.note,
        occurred_at=row.occurred_at,
    )


@router.get("/saved-filters", response_model=list[ReviewSavedFilterItem])
def list_saved_filters(
    owner: str = Query(..., min_length=1, max_length=200),
    db: Session = Depends(get_sync_db),
):
    rows = db.execute(
        select(ReviewSavedFilter)
        .where(ReviewSavedFilter.owner == owner.strip())
        .order_by(ReviewSavedFilter.name, ReviewSavedFilter.id)
    ).scalars().all()
    return [
        ReviewSavedFilterItem(
            id=row.id,
            owner=row.owner,
            name=row.name,
            criteria=row.criteria,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/saved-filters", response_model=ReviewSavedFilterItem, status_code=201)
def create_saved_filter(
    payload: ReviewSavedFilterCreateRequest,
    db: Session = Depends(get_sync_db),
):
    duplicate = db.execute(
        select(ReviewSavedFilter.id).where(
            ReviewSavedFilter.owner == payload.owner,
            ReviewSavedFilter.name == payload.name,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="A saved filter with this name already exists.")
    row = ReviewSavedFilter(
        id=uuid4(),
        owner=payload.owner,
        name=payload.name,
        criteria=payload.criteria.model_dump(mode="json", exclude_none=True),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return ReviewSavedFilterItem(
        id=row.id,
        owner=row.owner,
        name=row.name,
        criteria=row.criteria,
        created_at=row.created_at,
    )


@router.delete("/saved-filters/{filter_id}", status_code=204)
def delete_saved_filter(
    filter_id: UUID,
    owner: str = Query(..., min_length=1, max_length=200),
    db: Session = Depends(get_sync_db),
):
    result = db.execute(
        delete(ReviewSavedFilter).where(
            ReviewSavedFilter.id == filter_id,
            ReviewSavedFilter.owner == owner.strip(),
        )
    )
    if not result.rowcount:
        db.rollback()
        raise HTTPException(status_code=404, detail="Saved filter not found.")
    db.commit()
    return Response(status_code=204)


@router.get("/sessions", response_model=list[ReviewSessionItem])
def list_review_sessions(
    reviewer: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_sync_db),
):
    rows = db.execute(
        select(ReviewSession)
        .where(ReviewSession.reviewer == reviewer.strip())
        .order_by(ReviewSession.started_at.desc(), ReviewSession.id.desc())
        .limit(limit)
    ).scalars().all()
    return [_session_item(db, row) for row in rows]


@router.post("/sessions", response_model=ReviewSessionItem, status_code=201)
def start_review_session(
    payload: ReviewSessionCreateRequest,
    db: Session = Depends(get_sync_db),
):
    row = ReviewSession(
        id=uuid4(),
        reviewer=payload.reviewer,
        status="active",
        filter_snapshot=payload.filter_snapshot.model_dump(mode="json", exclude_none=True),
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return _session_item(db, row)


@router.post("/sessions/{session_id}/complete", response_model=ReviewSessionItem)
def complete_review_session(
    session_id: UUID,
    payload: ReviewSessionCloseRequest,
    db: Session = Depends(get_sync_db),
):
    row = db.execute(
        select(ReviewSession).where(ReviewSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Review session not found.")
    if row.reviewer.casefold() != payload.reviewer.casefold():
        raise HTTPException(status_code=409, detail="Only the session reviewer can complete it.")
    if row.status != "completed":
        row.status = "completed"
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
    return _session_item(db, row)


@router.get("/parser-previews", response_model=ParserArtifactListResponse)
async def list_parser_previews(
    source_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.list_parser_artifacts(
        db,
        artifact_type="preview",
        source_id=source_id,
        page=page,
        page_size=page_size,
    )
    return ParserArtifactListResponse(
        items=items, page=page, page_size=page_size, total=total
    )


@router.get(
    "/relationship-candidates",
    response_model=TradeEventCandidateReviewListResponse,
)
def list_relationship_candidates(
    status: RelationshipCandidateStatus | None = None,
    evidence_tier: str | None = Query(None, min_length=1, max_length=100),
    event_type: str | None = Query(None, min_length=1, max_length=100),
    query: str | None = Query(None, min_length=2, max_length=200, alias="q"),
    max_abs_days: int | None = Query(None, ge=0, le=3650),
    min_internal_rank: float | None = Query(None, ge=0),
    has_reviews: bool | None = None,
    sort: RelationshipCandidateSort = RelationshipCandidateSort.PRIORITY,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_sync_db),
):
    count_statement = (
        select(func.count(func.distinct(TradeEventCandidate.id)))
        .select_from(TradeEventCandidate)
        .join(Trade, Trade.id == TradeEventCandidate.trade_id)
        .join(Event, Event.id == TradeEventCandidate.event_id)
        .join(Person, Person.id == Trade.person_id)
    )
    items_statement = _candidate_select()
    filters = []
    if status is not None:
        filters.append(TradeEventCandidate.review_status == status.value)
    if evidence_tier:
        filters.append(TradeEventCandidate.evidence_tier == evidence_tier.strip())
    if event_type:
        filters.append(Event.event_type == event_type.strip())
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                Person.full_name.ilike(pattern),
                Trade.asset_display_name.ilike(pattern),
                Trade.ticker.ilike(pattern),
                Event.label.ilike(pattern),
            )
        )
    if max_abs_days is not None:
        filters.append(func.abs(TradeEventCandidate.days_from_event) <= max_abs_days)
    if min_internal_rank is not None:
        filters.append(TradeEventCandidate.internal_rank >= min_internal_rank)
    if has_reviews is not None:
        review_exists = (
            select(RelationshipReview.id)
            .where(RelationshipReview.candidate_id == TradeEventCandidate.id)
            .exists()
        )
        filters.append(review_exists if has_reviews else ~review_exists)
    if filters:
        count_statement = count_statement.where(*filters)
        items_statement = items_statement.where(*filters)

    status_priority = case(
        (TradeEventCandidate.review_status == "candidate", 0),
        (TradeEventCandidate.review_status == "narrowed", 1),
        (TradeEventCandidate.review_status == "accepted", 2),
        (TradeEventCandidate.review_status == "rejected", 3),
        else_=4,
    )
    order_by = {
        RelationshipCandidateSort.PRIORITY: (
            status_priority,
            TradeEventCandidate.internal_rank.desc().nullslast(),
            func.abs(TradeEventCandidate.days_from_event),
            TradeEventCandidate.created_at,
            TradeEventCandidate.id,
        ),
        RelationshipCandidateSort.NEWEST: (
            TradeEventCandidate.created_at.desc(),
            TradeEventCandidate.id,
        ),
        RelationshipCandidateSort.OLDEST: (
            TradeEventCandidate.created_at,
            TradeEventCandidate.id,
        ),
        RelationshipCandidateSort.EVENT_DATE: (
            Event.date.desc(),
            TradeEventCandidate.id,
        ),
        RelationshipCandidateSort.TRADE_DATE: (
            Trade.trade_date.desc(),
            TradeEventCandidate.id,
        ),
    }[sort]

    total = db.execute(count_statement).scalar_one()
    rows = db.execute(
        items_statement.order_by(*order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    candidate_ids = [row[0].id for row in rows]
    history = _review_history(db, candidate_ids)
    return TradeEventCandidateReviewListResponse(
        items=[_candidate_item(row, history) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        sort=sort,
    )


@router.get(
    "/relationship-candidates/{candidate_id}",
    response_model=TradeEventCandidateReviewItem,
)
def get_relationship_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_sync_db),
):
    candidate = _load_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Relationship candidate not found.")
    return candidate


@router.get(
    "/relationship-candidates/{candidate_id}/history",
    response_model=list[RelationshipReviewHistoryItem],
)
def get_relationship_candidate_history(
    candidate_id: UUID,
    db: Session = Depends(get_sync_db),
):
    exists = db.execute(
        select(TradeEventCandidate.id).where(TradeEventCandidate.id == candidate_id)
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="Relationship candidate not found.")
    return _review_history(db, [candidate_id]).get(candidate_id, [])


@router.get(
    "/relationship-audit-history/export",
    response_model=RelationshipAuditExportResponse,
)
def export_relationship_audit_history(
    db: Session = Depends(get_sync_db),
):
    rows = db.execute(
        select(RelationshipReview, TradeEventCandidate)
        .join(
            TradeEventCandidate,
            TradeEventCandidate.id == RelationshipReview.candidate_id,
        )
        .order_by(RelationshipReview.reviewed_at, RelationshipReview.id)
    ).all()
    records = [
        RelationshipAuditExportRecord(
            review_id=review.id,
            candidate_id=review.candidate_id,
            trade_id=candidate.trade_id,
            event_id=candidate.event_id,
            methodology_version=candidate.methodology_version,
            decision=review.decision,
            reviewer=review.reviewer,
            evidence_note=review.reason,
            reviewed_at=review.reviewed_at,
            review_session_id=getattr(review, "review_session_id", None),
        )
        for review, candidate in rows
    ]
    core = {
        "schema_version": "relationship-audit-export-v1",
        "snapshot_through": (
            records[-1].reviewed_at.isoformat() if records else None
        ),
        "record_count": len(records),
        "interpretation_boundary": (
            "Append-only reviewer decisions and attribution only. This export does not "
            "promote candidates or establish that a relationship is causal."
        ),
        "records": [record.model_dump(mode="json") for record in records],
    }
    canonical_core = json.dumps(
        core, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = sha256(canonical_core).hexdigest()
    payload = {
        **core,
        "export_id": f"relationship-audit-{digest[:16]}",
        "content_sha256": digest,
    }
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="relationship-audit-{digest[:16]}.json"'
            ),
            "ETag": f'"{digest}"',
        },
    )


@router.post(
    "/relationship-candidates/{candidate_id}/decisions",
    response_model=TradeEventCandidateReviewItem,
    status_code=201,
)
def create_relationship_candidate_decision(
    candidate_id: UUID,
    payload: RelationshipReviewCreateRequest,
    db: Session = Depends(get_sync_db),
):
    try:
        candidate = db.execute(
            select(TradeEventCandidate)
            .where(TradeEventCandidate.id == candidate_id)
            .with_for_update()
        ).scalar_one_or_none()
        if candidate is None:
            raise HTTPException(
                status_code=404, detail="Relationship candidate not found."
            )

        if (
            payload.expected_status is not None
            and candidate.review_status != payload.expected_status.value
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "The candidate status changed after this review view was loaded. "
                    "Reload the candidate before recording a decision."
                ),
            )

        if payload.expected_revision is not None:
            current_history = _review_history(db, [candidate_id]).get(candidate_id, [])
            current_revision = _review_revision(
                candidate.review_status, current_history
            )
            if current_revision != payload.expected_revision:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "The candidate review history changed after this review view was "
                        "loaded. Reload the candidate before recording a decision."
                    ),
                )

        _validated_session(db, payload.review_session_id, payload.reviewer)
        reviewed_at = datetime.now(timezone.utc)
        review = RelationshipReview(
            id=uuid4(),
            candidate_id=candidate.id,
            decision=payload.decision.value,
            reviewer=payload.reviewer,
            reason=payload.evidence_note,
            reviewed_at=reviewed_at,
            review_session_id=payload.review_session_id,
        )
        candidate.review_status = DECISION_STATUS[payload.decision].value
        db.add(review)
        db.flush()
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The relationship decision could not be saved.",
        ) from exc

    saved_candidate = _load_candidate(db, candidate_id)
    if saved_candidate is None:
        raise HTTPException(status_code=404, detail="Relationship candidate not found.")
    return saved_candidate


@router.post(
    "/relationship-candidates/bulk-decisions",
    response_model=RelationshipBulkReviewResponse,
    status_code=201,
)
def create_bulk_relationship_candidate_decisions(
    payload: RelationshipBulkReviewCreateRequest,
    db: Session = Depends(get_sync_db),
):
    target_ids = sorted(
        (target.candidate_id for target in payload.targets), key=str
    )
    target_by_id = {target.candidate_id: target for target in payload.targets}
    try:
        _validated_session(db, payload.review_session_id, payload.reviewer)
        candidates = (
            db.execute(
                select(TradeEventCandidate)
                .where(TradeEventCandidate.id.in_(target_ids))
                .order_by(TradeEventCandidate.id)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        candidates_by_id = {candidate.id: candidate for candidate in candidates}
        missing = [candidate_id for candidate_id in target_ids if candidate_id not in candidates_by_id]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Relationship candidates not found: {', '.join(map(str, missing))}.",
            )

        history = _review_history(db, target_ids)
        stale = []
        for candidate_id in target_ids:
            candidate = candidates_by_id[candidate_id]
            target = target_by_id[candidate_id]
            current_revision = _review_revision(
                candidate.review_status, history.get(candidate_id, [])
            )
            if (
                candidate.review_status != target.expected_status.value
                or current_revision != target.expected_revision
            ):
                stale.append(candidate_id)
        if stale:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The bulk review was not recorded because candidate state changed: "
                    f"{', '.join(map(str, stale))}. Reload the queue and try again."
                ),
            )

        reviewed_at = datetime.now(timezone.utc)
        for candidate_id in target_ids:
            candidate = candidates_by_id[candidate_id]
            db.add(
                RelationshipReview(
                    id=uuid4(),
                    candidate_id=candidate_id,
                    decision=payload.decision.value,
                    reviewer=payload.reviewer,
                    reason=payload.evidence_note,
                    reviewed_at=reviewed_at,
                    review_session_id=payload.review_session_id,
                )
            )
            candidate.review_status = DECISION_STATUS[payload.decision].value
        db.flush()
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The bulk relationship decision could not be saved.",
        ) from exc

    rows = db.execute(
        _candidate_select().where(TradeEventCandidate.id.in_(target_ids))
    ).all()
    saved_history = _review_history(db, target_ids)
    items_by_id = {
        row[0].id: _candidate_item(row, saved_history) for row in rows
    }
    return RelationshipBulkReviewResponse(
        updated_count=len(target_ids),
        items=[items_by_id[candidate_id] for candidate_id in target_ids],
    )


@router.post(
    "/parser-previews/{artifact_id}/promote", response_model=PromotePreviewResponse
)
def promote_parser_preview(
    artifact_id: UUID,
    payload: PromotePreviewRequest,
    db: Session = Depends(get_sync_db),
):
    try:
        filing, trades = promote_preview_artifact(
            db,
            preview_artifact_id=artifact_id,
            reviewer=payload.reviewer,
            person_name=payload.person_name,
            branch=payload.branch,
            chamber=payload.chamber,
            state=payload.state,
            party=payload.party,
            office=payload.office,
            agency=payload.agency,
            court=payload.court,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PromotePreviewResponse(filing_id=filing.id, trade_count=len(trades))


@router.post("/filings/{filing_id}/rollback", response_model=RollbackFilingResponse)
def rollback_filing(
    filing_id: UUID,
    payload: RollbackFilingRequest,
    db: Session = Depends(get_sync_db),
):
    try:
        result = rollback_promoted_filing(
            db,
            filing_id=filing_id,
            reviewer=payload.reviewer,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RollbackFilingResponse(**result)


@router.post("/filings/{filing_id}/supersede", response_model=FilingDetail)
def mark_filing_superseded(
    filing_id: UUID,
    payload: SupersedeFilingRequest,
    db: Session = Depends(get_sync_db),
):
    try:
        filing = supersede_filing(
            db,
            filing_id=filing_id,
            superseded_by_filing_id=payload.superseded_by_filing_id,
            reviewer=payload.reviewer,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FilingDetail(
        id=filing.id,
        person_id=filing.person_id,
        filing_type=filing.filing_type,
        filed_date=filing.filed_date,
        source_url=filing.source_url,
        retrieved_at=filing.retrieved_at,
        file_hash=filing.file_hash,
        retrieval_source=filing.retrieval_source,
        raw_document_id=filing.raw_document_id,
        superseded_by_filing_id=filing.superseded_by_filing_id,
        provenance_complete=bool(
            filing.source_url and filing.retrieved_at and filing.file_hash
        ),
        created_at=filing.created_at,
    )
