from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from typing import Optional
from app.database import get_db
from app.schemas import MarketSeriesItem, MarketPoint
from app import crud

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/series", response_model=list[MarketSeriesItem])
async def get_market_series(
    symbols: str = Query("SPY,DIA"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    freq: str = "d",
    db: AsyncSession = Depends(get_db),
):
    symbol_list = [s.strip() for s in symbols.split(",")]
    points = await crud.get_market_series(db, symbol_list, start, end, freq)

    # Group by symbol
    by_symbol: dict[str, list] = {}
    for p in points:
        by_symbol.setdefault(p.symbol, []).append(p)

    result = []
    for sym, pts in by_symbol.items():
        if pts:
            result.append(MarketSeriesItem(
                symbol=sym,
                freq=freq,
                start=pts[0].date,
                end=pts[-1].date,
                points=[MarketPoint(date=p.date, value=p.value) for p in pts],
            ))

    return result
