from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import datetime
from app.database import get_db
from app.schemas import ShareCardCreateRequest, ShareCardCreateResponse, ShareCardDetail
from app.services.sharecards import generate_sharecard
from app import crud

router = APIRouter(prefix="/sharecards", tags=["sharecards"])


@router.post("", response_model=ShareCardCreateResponse)
async def create_sharecard(
    req: ShareCardCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    if req.scope == "trade" and not req.trade_id:
        raise HTTPException(status_code=400, detail="trade_id required when scope=trade")
    if req.scope == "range" and (not req.start or not req.end):
        raise HTTPException(status_code=400, detail="start and end required when scope=range")

    card = await generate_sharecard(
        db,
        scope=req.scope,
        person_id=req.person_id,
        trade_id=req.trade_id,
        range_start=req.start,
        range_end=req.end,
        overlays=req.overlays,
        include_events=req.include_events,
    )

    return ShareCardCreateResponse(
        sharecard_id=card.id,
        render_url=card.render_url,
        permalink_url=None,
        sources=card.sources,
        disclaimer_text=card.disclaimer_text,
        generated_at=card.created_at or datetime.utcnow(),
    )


@router.get("/{sharecard_id}", response_model=ShareCardDetail)
async def get_sharecard(sharecard_id: UUID, db: AsyncSession = Depends(get_db)):
    card = await crud.get_sharecard(db, sharecard_id)
    if not card:
        raise HTTPException(status_code=404, detail="Share card not found")
    return ShareCardDetail.model_validate(card)
