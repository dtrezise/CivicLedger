from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.database import get_db
from app.schemas import TradeDetail, ProvenanceInfo, ParserArtifactItem
from app import crud

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/{trade_id}", response_model=TradeDetail)
async def get_trade(trade_id: UUID, db: AsyncSession = Depends(get_db)):
    trade = await crud.get_trade(db, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    filing = await crud.get_filing(db, trade.filing_id)

    provenance_complete = bool(
        filing and filing.source_url and filing.retrieved_at and filing.file_hash
    )

    provenance = ProvenanceInfo(
        source_url=filing.source_url if filing else "",
        retrieved_at=filing.retrieved_at if filing else None,
        file_hash=filing.file_hash if filing else "",
        provenance_complete=provenance_complete,
    )

    return TradeDetail(
        **{k: v for k, v in trade.__dict__.items() if not k.startswith("_")},
        provenance=provenance,
    )


@router.get("/{trade_id}/artifacts", response_model=list[ParserArtifactItem])
async def get_trade_artifacts(trade_id: UUID, db: AsyncSession = Depends(get_db)):
    trade = await crud.get_trade(db, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return await crud.get_parser_artifacts_for_trade(db, trade_id)
