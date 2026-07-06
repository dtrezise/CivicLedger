from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db, get_sync_db
from app.schemas import (
    FilingDetail,
    ParserArtifactListResponse,
    PromotePreviewRequest,
    PromotePreviewResponse,
    RollbackFilingRequest,
    RollbackFilingResponse,
    SupersedeFilingRequest,
)
from app.services.promotion import (
    promote_preview_artifact,
    rollback_promoted_filing,
    supersede_filing,
)

router = APIRouter(prefix="/review", tags=["review"])


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
    return ParserArtifactListResponse(items=items, page=page, page_size=page_size, total=total)


@router.post("/parser-previews/{artifact_id}/promote", response_model=PromotePreviewResponse)
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
        provenance_complete=bool(filing.source_url and filing.retrieved_at and filing.file_hash),
        created_at=filing.created_at,
    )
