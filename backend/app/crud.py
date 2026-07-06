from uuid import UUID
from datetime import date, datetime
from typing import Optional
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import (
    Person,
    Filing,
    Trade,
    Event,
    EventSource,
    MarketSeries,
    ShareCard,
    RawDocument,
    IngestionRun,
    ParserArtifact,
)


# ---- People ----

async def search_people(db: AsyncSession, q: str) -> list[Person]:
    query = select(Person).where(Person.full_name.ilike(f"%{q}%")).limit(20)
    result = await db.execute(query)
    return result.scalars().all()


async def list_people(
    db: AsyncSession,
    branch: Optional[str] = None,
    chamber: Optional[str] = None,
    agency: Optional[str] = None,
    court: Optional[str] = None,
    state: Optional[str] = None,
    party: Optional[str] = None,
    sort: str = "full_name",
    page: int = 1,
    page_size: int = 20,
):
    query = select(Person)
    count_query = select(func.count(Person.id))

    if branch:
        query = query.where(Person.branch == branch)
        count_query = count_query.where(Person.branch == branch)
    if chamber:
        query = query.where(Person.chamber == chamber)
        count_query = count_query.where(Person.chamber == chamber)
    if agency:
        query = query.where(Person.agency == agency)
        count_query = count_query.where(Person.agency == agency)
    if court:
        query = query.where(Person.court == court)
        count_query = count_query.where(Person.court == court)
    if state:
        query = query.where(Person.state == state)
        count_query = count_query.where(Person.state == state)
    if party:
        query = query.where(Person.party == party)
        count_query = count_query.where(Person.party == party)

    sort_col = getattr(Person, sort, Person.full_name)
    query = query.order_by(sort_col).offset((page - 1) * page_size).limit(page_size)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(query)
    items = result.scalars().all()

    return items, total


async def get_person(db: AsyncSession, person_id: UUID) -> Optional[Person]:
    result = await db.execute(select(Person).where(Person.id == person_id))
    return result.scalar_one_or_none()


async def get_person_trades(
    db: AsyncSession,
    person_id: UUID,
    start: Optional[date] = None,
    end: Optional[date] = None,
    action: Optional[str] = None,
    asset_class: Optional[str] = None,
    min_lag: Optional[int] = None,
    sort: str = "trade_date",
    page: int = 1,
    page_size: int = 20,
):
    query = select(Trade).where(Trade.person_id == person_id)
    count_query = select(func.count(Trade.id)).where(Trade.person_id == person_id)

    filters = []
    if start:
        filters.append(Trade.trade_date >= start)
    if end:
        filters.append(Trade.trade_date <= end)
    if action:
        filters.append(Trade.action == action)
    if asset_class:
        filters.append(Trade.asset_class == asset_class)
    if min_lag is not None:
        filters.append(Trade.disclosure_lag_days >= min_lag)

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    if sort.startswith("-"):
        sort_col = getattr(Trade, sort[1:], Trade.trade_date)
        query = query.order_by(desc(sort_col))
    else:
        sort_col = getattr(Trade, sort, Trade.trade_date)
        query = query.order_by(asc(sort_col))

    query = query.offset((page - 1) * page_size).limit(page_size)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(query)
    items = result.scalars().all()

    return items, total


async def get_trade(db: AsyncSession, trade_id: UUID) -> Optional[Trade]:
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    return result.scalar_one_or_none()


async def get_filing(db: AsyncSession, filing_id: UUID) -> Optional[Filing]:
    result = await db.execute(select(Filing).where(Filing.id == filing_id))
    return result.scalar_one_or_none()


async def get_raw_document(db: AsyncSession, raw_document_id: UUID) -> Optional[RawDocument]:
    result = await db.execute(select(RawDocument).where(RawDocument.id == raw_document_id))
    return result.scalar_one_or_none()


async def get_parser_artifacts_for_trade(db: AsyncSession, trade_id: UUID) -> list[ParserArtifact]:
    result = await db.execute(
        select(ParserArtifact)
        .where(ParserArtifact.trade_id == trade_id)
        .order_by(ParserArtifact.created_at, ParserArtifact.row_number)
    )
    return result.scalars().all()


async def get_parser_artifacts_for_filing(db: AsyncSession, filing_id: UUID) -> list[ParserArtifact]:
    result = await db.execute(
        select(ParserArtifact)
        .where(ParserArtifact.filing_id == filing_id)
        .order_by(ParserArtifact.created_at, ParserArtifact.row_number)
    )
    return result.scalars().all()


async def get_parser_artifacts_for_raw_document(
    db: AsyncSession, raw_document_id: UUID
) -> list[ParserArtifact]:
    result = await db.execute(
        select(ParserArtifact)
        .where(ParserArtifact.raw_document_id == raw_document_id)
        .order_by(ParserArtifact.created_at, ParserArtifact.row_number)
    )
    return result.scalars().all()


async def get_person_filings(db: AsyncSession, person_id: UUID) -> list[Filing]:
    result = await db.execute(
        select(Filing).where(Filing.person_id == person_id).order_by(Filing.filed_date.desc())
    )
    return result.scalars().all()


# ---- Market ----

async def get_market_series(
    db: AsyncSession,
    symbols: list[str],
    start: Optional[date] = None,
    end: Optional[date] = None,
    freq: str = "d",
):
    query = select(MarketSeries).where(
        MarketSeries.symbol.in_(symbols),
        MarketSeries.freq == freq,
    )
    if start:
        query = query.where(MarketSeries.date >= start)
    if end:
        query = query.where(MarketSeries.date <= end)
    query = query.order_by(MarketSeries.symbol, MarketSeries.date)

    result = await db.execute(query)
    return result.scalars().all()


# ---- Events ----

async def get_events(
    db: AsyncSession,
    person_id: Optional[UUID] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
):
    query = select(Event).options(selectinload(Event.sources))
    if start:
        query = query.where(Event.date >= start)
    if end:
        query = query.where(Event.date <= end)
    query = query.order_by(Event.date)

    result = await db.execute(query)
    return result.scalars().unique().all()


async def get_event(db: AsyncSession, event_id: UUID) -> Optional[Event]:
    result = await db.execute(
        select(Event).options(selectinload(Event.sources)).where(Event.id == event_id)
    )
    return result.scalars().unique().one_or_none()


# ---- ShareCards ----

async def create_sharecard(db: AsyncSession, card: ShareCard) -> ShareCard:
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


async def get_sharecard(db: AsyncSession, sharecard_id: UUID) -> Optional[ShareCard]:
    result = await db.execute(select(ShareCard).where(ShareCard.id == sharecard_id))
    return result.scalar_one_or_none()


# ---- Batch Stats ----

async def get_batch_stats(
    db: AsyncSession,
    person_ids: list[UUID],
    window_start: Optional[date] = None,
    window_end: Optional[date] = None,
):
    results = {}
    for pid in person_ids:
        trade_q = select(Trade).where(Trade.person_id == pid)
        if window_start:
            trade_q = trade_q.where(Trade.trade_date >= window_start)
        if window_end:
            trade_q = trade_q.where(Trade.trade_date <= window_end)

        trades_result = await db.execute(trade_q)
        trades = trades_result.scalars().all()

        filing_q = select(func.max(Filing.filed_date)).where(Filing.person_id == pid)
        filing_result = await db.execute(filing_q)
        last_filing = filing_result.scalar()

        lags = sorted([t.disclosure_lag_days for t in trades])
        median_lag = None
        if lags:
            mid = len(lags) // 2
            median_lag = float(lags[mid]) if len(lags) % 2 else float((lags[mid - 1] + lags[mid]) / 2)

        results[str(pid)] = {
            "trades_count": len(trades),
            "last_filing_processed_at": datetime.combine(last_filing, datetime.min.time()) if last_filing else None,
            "median_lag_days": median_lag,
        }

    return results


# ---- Source Completeness ----

async def get_completed_ingestion_source_names(db: AsyncSession) -> set[str]:
    result = await db.execute(
        select(IngestionRun.source_name).where(IngestionRun.status == "completed")
    )
    return set(result.scalars().all())


async def count_raw_documents_by_source(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(RawDocument.retrieval_source, func.count(RawDocument.id)).group_by(
            RawDocument.retrieval_source
        )
    )
    return {source: count for source, count in result.all()}


async def count_filings_by_source(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(Filing.retrieval_source, func.count(Filing.id)).group_by(
            Filing.retrieval_source
        )
    )
    return {source: count for source, count in result.all()}
