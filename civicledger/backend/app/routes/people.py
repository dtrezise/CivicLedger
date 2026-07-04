from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from datetime import date, timedelta
from typing import Optional
from app.database import get_db
from app.schemas import (
    PersonSummary, PersonDetail, PersonListResponse,
    PersonBatchStatsResponse, PersonBatchStatsItem,
    ScorecardResponse, TimelineResponse, TimelineBucket, TimelineGap,
    TradeRow, TradeListResponse,
)
from app import crud
from app.services.scorecard import compute_scorecard
from dateutil.relativedelta import relativedelta

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=PersonListResponse)
async def list_people(
    chamber: Optional[str] = None,
    state: Optional[str] = None,
    party: Optional[str] = None,
    sort: str = "full_name",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.list_people(db, chamber, state, party, sort, page, page_size)
    return PersonListResponse(
        items=[
            PersonSummary(
                id=p.id,
                full_name=p.full_name,
                chamber=p.chamber,
                state=p.state,
                party=p.party,
                service_start=p.service_start,
                service_end=p.service_end,
            )
            for p in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/batch_stats", response_model=PersonBatchStatsResponse)
async def batch_stats(
    ids: str = Query(...),
    window_start: Optional[date] = None,
    window_end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    person_ids = [UUID(x.strip()) for x in ids.split(",") if x.strip()]
    stats = await crud.get_batch_stats(db, person_ids, window_start, window_end)
    return PersonBatchStatsResponse(
        by_id={k: PersonBatchStatsItem(**v) for k, v in stats.items()}
    )


@router.get("/{person_id}", response_model=PersonDetail)
async def get_person(person_id: UUID, db: AsyncSession = Depends(get_db)):
    person = await crud.get_person(db, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return PersonDetail(
        id=person.id,
        full_name=person.full_name,
        branch=person.branch,
        chamber=person.chamber,
        state=person.state,
        party=person.party,
        district=person.district,
        service_start=person.service_start,
        service_end=person.service_end,
        created_at=person.created_at,
    )


@router.get("/{person_id}/scorecard", response_model=ScorecardResponse)
async def get_scorecard(person_id: UUID, db: AsyncSession = Depends(get_db)):
    person = await crud.get_person(db, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return await compute_scorecard(db, person_id)


@router.get("/{person_id}/timeline", response_model=TimelineResponse)
async def get_timeline(
    person_id: UUID,
    start: Optional[date] = None,
    end: Optional[date] = None,
    bucket: str = Query("month", regex="^(month|week|day)$"),
    db: AsyncSession = Depends(get_db),
):
    person = await crud.get_person(db, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    all_trades, _ = await crud.get_person_trades(db, person_id, start=start, end=end, page_size=10000)

    if not all_trades:
        return TimelineResponse(buckets=[], gaps=[])

    # Determine range
    trade_dates = [t.trade_date for t in all_trades]
    range_start = start or min(trade_dates)
    range_end = end or max(trade_dates)

    # Build buckets
    buckets = []
    current = range_start

    while current <= range_end:
        if bucket == "month":
            bucket_end = (current + relativedelta(months=1)) - timedelta(days=1)
        elif bucket == "week":
            bucket_end = current + timedelta(days=6)
        else:
            bucket_end = current

        bucket_end = min(bucket_end, range_end)
        bucket_trades = [t for t in all_trades if current <= t.trade_date <= bucket_end]

        lags = sorted([t.disclosure_lag_days for t in bucket_trades])
        median_lag = None
        if lags:
            mid = len(lags) // 2
            median_lag = float(lags[mid]) if len(lags) % 2 else float((lags[mid - 1] + lags[mid]) / 2)

        buckets.append(TimelineBucket(
            start=current,
            end=bucket_end,
            trade_count=len(bucket_trades),
            buy_count=len([t for t in bucket_trades if t.action == "BUY"]),
            sell_count=len([t for t in bucket_trades if t.action == "SELL"]),
            median_lag_days=median_lag,
        ))

        if bucket == "month":
            current = current + relativedelta(months=1)
        elif bucket == "week":
            current = current + timedelta(days=7)
        else:
            current = current + timedelta(days=1)

    # Detect gaps (months with 0 trades)
    gaps = []
    for b in buckets:
        if b.trade_count == 0:
            gaps.append(TimelineGap(
                start=b.start,
                end=b.end,
                gap_type="no_trades",
                display_label=f"No trades {b.start.strftime('%b %Y')}",
            ))

    return TimelineResponse(buckets=buckets, gaps=gaps)


@router.get("/{person_id}/trades", response_model=TradeListResponse)
async def get_person_trades(
    person_id: UUID,
    start: Optional[date] = None,
    end: Optional[date] = None,
    type: Optional[str] = None,
    asset_class: Optional[str] = None,
    min_lag: Optional[int] = None,
    sort: str = "trade_date",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.get_person_trades(
        db, person_id, start, end, type, asset_class, min_lag, sort, page, page_size
    )
    return TradeListResponse(
        items=[TradeRow.model_validate(t) for t in items],
        page=page,
        page_size=page_size,
        total=total,
    )
