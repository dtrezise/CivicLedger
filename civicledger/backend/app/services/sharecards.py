from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ShareCard, Trade, Filing
from app.config import settings
from app import crud

DISCLAIMER = (
    "This share card is generated from publicly available congressional financial disclosures. "
    "It is not investment advice. Market comparisons use benchmark indices (SPY/DIA) and do not "
    "represent actual portfolio performance. All data is subject to reporting delays and potential "
    "parsing inaccuracies. See methodology for details."
)


async def generate_sharecard(
    db: AsyncSession,
    scope: str,
    person_id: UUID,
    trade_id: UUID | None = None,
    range_start=None,
    range_end=None,
    overlays: list[str] = None,
    include_events: bool = True,
) -> ShareCard:
    """Create and persist a share card record."""

    if overlays is None:
        overlays = ["SPY", "DIA"]

    # Gather sources
    sources = []
    if scope == "trade" and trade_id:
        trade = await crud.get_trade(db, trade_id)
        if trade:
            filing = await crud.get_filing(db, trade.filing_id)
            if filing:
                sources.append(filing.source_url)
    elif scope == "range":
        trades, _ = await crud.get_person_trades(
            db, person_id, start=range_start, end=range_end, page_size=100
        )
        filing_ids = set(t.filing_id for t in trades)
        for fid in filing_ids:
            filing = await crud.get_filing(db, fid)
            if filing:
                sources.append(filing.source_url)

    card = ShareCard(
        id=uuid4(),
        scope=scope,
        person_id=person_id,
        trade_id=trade_id,
        range_start=range_start,
        range_end=range_end,
        overlays=overlays,
        include_events=include_events,
        sources=list(set(sources)),
        disclaimer_text=DISCLAIMER,
        methodology_version=settings.METHODOLOGY_VERSION,
        render_url=None,  # MVP: no actual image render
    )

    return await crud.create_sharecard(db, card)
