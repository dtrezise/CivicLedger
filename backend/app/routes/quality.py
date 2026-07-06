from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Filing, Trade
from app.schemas import (
    DuplicateFilingGroup,
    DuplicateReportResponse,
    DuplicateTradeGroup,
)

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("/duplicates", response_model=DuplicateReportResponse)
async def duplicate_report(db: AsyncSession = Depends(get_db)):
    trades_result = await db.execute(select(Trade))
    filings_result = await db.execute(select(Filing))
    trades = trades_result.scalars().all()
    filings = filings_result.scalars().all()

    trade_groups = defaultdict(list)
    for trade in trades:
        key = (
            str(trade.person_id),
            trade.trade_date.isoformat(),
            trade.action,
            trade.asset_display_name.strip().lower(),
            trade.value_range_label.strip().lower(),
        )
        trade_groups[key].append(trade)

    filing_groups = defaultdict(list)
    for filing in filings:
        key = (
            str(filing.person_id),
            filing.filed_date.isoformat(),
            filing.filing_type.strip().lower(),
            filing.file_hash,
        )
        filing_groups[key].append(filing)

    duplicate_trades = [
        DuplicateTradeGroup(
            duplicate_key="|".join(key),
            trade_ids=[trade.id for trade in group],
            person_id=group[0].person_id,
            trade_date=group[0].trade_date,
            action=group[0].action,
            asset_display_name=group[0].asset_display_name,
            value_range_label=group[0].value_range_label,
            count=len(group),
        )
        for key, group in trade_groups.items()
        if len(group) > 1
    ]
    duplicate_filings = [
        DuplicateFilingGroup(
            duplicate_key="|".join(key),
            filing_ids=[filing.id for filing in group],
            person_id=group[0].person_id,
            filed_date=group[0].filed_date,
            filing_type=group[0].filing_type,
            file_hash=group[0].file_hash,
            count=len(group),
        )
        for key, group in filing_groups.items()
        if len(group) > 1
    ]

    return DuplicateReportResponse(
        trade_groups=duplicate_trades,
        filing_groups=duplicate_filings,
    )
