from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db, get_sync_db
from app.models import Event, Person, RelationshipReview, Trade, TradeEventCandidate
from app.schemas import (
    FilingDetail,
    ParserArtifactListResponse,
    PromotePreviewRequest,
    PromotePreviewResponse,
    RelationshipCandidateSort,
    RelationshipCandidateStatus,
    RelationshipReviewCreateRequest,
    RelationshipReviewDecision,
    RelationshipReviewHistoryItem,
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
        created_at=candidate.created_at,
        reviews=history.get(candidate.id, []),
    )


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

        reviewed_at = datetime.now(timezone.utc)
        review = RelationshipReview(
            id=uuid4(),
            candidate_id=candidate.id,
            decision=payload.decision.value,
            reviewer=payload.reviewer,
            reason=payload.evidence_note,
            reviewed_at=reviewed_at,
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
