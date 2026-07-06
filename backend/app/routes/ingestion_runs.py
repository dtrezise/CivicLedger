from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import IngestionRunListResponse

router = APIRouter(prefix="/ingestion-runs", tags=["ingestion-runs"])


@router.get("", response_model=IngestionRunListResponse)
async def list_ingestion_runs(
    source_name: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.list_ingestion_runs(
        db,
        source_name=source_name,
        status=status,
        page=page,
        page_size=page_size,
    )
    return IngestionRunListResponse(items=items, page=page, page_size=page_size, total=total)
