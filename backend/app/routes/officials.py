from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import PublicOfficialRoleItem, PublicOfficialRoleListResponse


router = APIRouter(prefix="/officials", tags=["officials"])


def role_item(role) -> PublicOfficialRoleItem:
    return PublicOfficialRoleItem(
        role_id=role.id,
        person_id=role.person_id,
        external_role_id=role.external_role_id,
        external_person_id=role.external_person_id,
        full_name=role.person.full_name,
        branch=role.branch,
        presidential_term=role.presidential_term,
        administration=role.administration,
        role_category=role.role_category,
        role_title=role.role_title,
        office=role.office,
        agency=role.agency,
        court=role.court,
        service_start=role.service_start,
        service_end=role.service_end,
        appointing_president=role.appointing_president,
        source_id=role.source_id,
        source_name=role.source_name,
        source_url=role.source_url,
        source_tier=role.source_tier,
        source_retrieved_at=role.source_retrieved_at,
        source_metadata=role.source_metadata,
    )


@router.get("/roles", response_model=PublicOfficialRoleListResponse)
async def list_public_official_roles(
    branch: Optional[str] = None,
    presidential_term: Optional[str] = None,
    role_category: Optional[str] = None,
    chamber: Optional[str] = None,
    congress_number: Optional[int] = None,
    party: Optional[str] = None,
    state: Optional[str] = None,
    district: Optional[str] = None,
    source_id: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.list_public_official_roles(
        db,
        branch=branch,
        presidential_term=presidential_term,
        role_category=role_category,
        chamber=chamber,
        congress_number=congress_number,
        party=party,
        state=state,
        district=district,
        source_id=source_id,
        q=q,
        page=page,
        page_size=page_size,
    )
    return PublicOfficialRoleListResponse(
        items=[role_item(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )
