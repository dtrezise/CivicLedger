from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ShareCard, Trade, Filing
from app.config import settings
from app import crud

DISCLAIMER = (
    "This share card is generated from the dataset and methodology version shown. It may contain "
    "reporting delays, parsing errors, incomplete provenance, fixture data, or later-corrected "
    "records. Market and event overlays provide temporal context only and do not imply causation, "
    "intent, legality, ethics, or investment performance. Verify against original sources before "
    "quoting, publishing, or relying on it."
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
        dataset_version=settings.DATASET_VERSION,
        methodology_version=settings.METHODOLOGY_VERSION,
        render_url=None,  # MVP: no actual image render
    )

    return await crud.create_sharecard(db, card)
