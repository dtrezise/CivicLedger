from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas import PersonSummary
from app import crud

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/people", response_model=list[PersonSummary])
async def search_people(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    people = await crud.search_people(db, q)
    return [
        PersonSummary(
            person_id=p.id,
            full_name=p.full_name,
            chamber=p.chamber,
            state=p.state,
            party=p.party,
            service_start=p.service_start,
            service_end=p.service_end,
        )
        for p in people
    ]
