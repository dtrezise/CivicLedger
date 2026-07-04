from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from uuid import UUID
from typing import Optional
from app.database import get_db
from app.schemas import EventItem
from app import crud

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventItem])
async def get_events(
    scope: Optional[str] = None,
    person_id: Optional[UUID] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    events = await crud.get_events(db, person_id, start, end)
    return [
        EventItem(
            event_id=e.id,
            date=e.date,
            label=e.label,
            event_type=e.event_type,
            source_links=[s.url for s in e.sources],
            description=e.description,
        )
        for e in events
    ]
