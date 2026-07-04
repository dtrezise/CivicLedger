from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from uuid import UUID
from typing import Optional
from app.database import get_db
from app.schemas import EventItem
from app import crud

router = APIRouter(prefix="/events", tags=["events"])


def to_event_item(event) -> EventItem:
    return EventItem(
        event_id=event.id,
        date=event.date,
        label=event.label,
        event_type=event.event_type,
        source_links=[s.url for s in event.sources],
        description=event.description,
    )


@router.get("", response_model=list[EventItem])
async def get_events(
    scope: Optional[str] = None,
    person_id: Optional[UUID] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    if person_id or (scope and scope != "global"):
        raise HTTPException(
            status_code=400,
            detail="Person-scoped event filtering is not modeled yet; request global events without person_id.",
        )
    events = await crud.get_events(db, person_id, start, end)
    return [to_event_item(e) for e in events]


@router.get("/{id}", response_model=EventItem)
async def get_event(id: UUID, db: AsyncSession = Depends(get_db)):
    event = await crud.get_event(db, id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return to_event_item(event)
