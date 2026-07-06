from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import ParserArtifactItem, RawDocumentDetail

router = APIRouter(prefix="/raw-documents", tags=["raw-documents"])


@router.get("/{raw_document_id}", response_model=RawDocumentDetail)
async def get_raw_document(raw_document_id: UUID, db: AsyncSession = Depends(get_db)):
    raw_document = await crud.get_raw_document(db, raw_document_id)
    if not raw_document:
        raise HTTPException(status_code=404, detail="Raw document not found")
    return RawDocumentDetail.model_validate(raw_document)


@router.get("/{raw_document_id}/artifacts", response_model=list[ParserArtifactItem])
async def get_raw_document_artifacts(
    raw_document_id: UUID, db: AsyncSession = Depends(get_db)
):
    raw_document = await crud.get_raw_document(db, raw_document_id)
    if not raw_document:
        raise HTTPException(status_code=404, detail="Raw document not found")
    return await crud.get_parser_artifacts_for_raw_document(db, raw_document_id)
