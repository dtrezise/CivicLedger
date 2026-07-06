from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import EvidenceSearchResponse

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/search", response_model=EvidenceSearchResponse)
async def search_evidence(
    q: str = Query(..., min_length=2),
    source_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.search_parser_artifacts(
        db,
        q=q,
        source_id=source_id,
        page=page,
        page_size=page_size,
    )
    return EvidenceSearchResponse(items=items, page=page, page_size=page_size, total=total)
