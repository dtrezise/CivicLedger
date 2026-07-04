from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.database import get_db
from app.schemas import FilingDetail
from app import crud

router = APIRouter(prefix="/filings", tags=["filings"])


@router.get("/{filing_id}", response_model=FilingDetail)
async def get_filing(filing_id: UUID, db: AsyncSession = Depends(get_db)):
    filing = await crud.get_filing(db, filing_id)
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")

    provenance_complete = bool(filing.source_url and filing.retrieved_at and filing.file_hash)

    return FilingDetail(
        id=filing.id,
        person_id=filing.person_id,
        filing_type=filing.filing_type,
        filed_date=filing.filed_date,
        source_url=filing.source_url,
        retrieved_at=filing.retrieved_at,
        file_hash=filing.file_hash,
        retrieval_source=filing.retrieval_source,
        superseded_by_filing_id=filing.superseded_by_filing_id,
        provenance_complete=provenance_complete,
        created_at=filing.created_at,
    )
