from fastapi import APIRouter
from app.config import settings
from app.schemas import (
    MetaStatusResponse,
    MethodologyResponse,
    MethodologyBlock,
    OfficialSourcesResponse,
    SourceCompletenessResponse,
    SourceCompletenessItem,
)
from app.services.official_sources import get_official_sources_response
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app import crud

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/status", response_model=MetaStatusResponse)
async def get_status():
    return MetaStatusResponse(
        last_ingestion_run_at=None,
        dataset_version=settings.DATASET_VERSION,
        parser_version=settings.PARSER_VERSION,
        methodology_version=settings.METHODOLOGY_VERSION,
    )


@router.get("/methodology", response_model=MethodologyResponse)
async def get_methodology():
    blocks = [
        MethodologyBlock(
            title="Overview",
            content=(
                "CivicLedger tracks public financial disclosures filed by federal officials "
                "across the legislative, executive, and judicial branches. "
                "The current dataset is fixture/demo data and is intended for development "
                "and portfolio evaluation only."
            ),
        ),
        MethodologyBlock(
            title="Neutrality Principle",
            content=(
                "CivicLedger presents factual disclosure data without editorial judgment. "
                "We do not characterize trades as suspicious, well-timed, or improper. "
                "Market and event overlays provide temporal context only, not causation, "
                "intent, legality, ethics, or investment conclusions."
            ),
        ),
        MethodologyBlock(
            title="Market-Adjusted Comparison",
            content=(
                "Benchmark moves are calculated using SPY (S&P 500 proxy) and DIA (Dow proxy). "
                "Horizons of 30 and 90 days are used. Start dates snap to the next available "
                "market session; end dates snap to the prior available session. "
                "Per-asset price moves are omitted in MVP unless asset-level price fixtures exist."
            ),
        ),
        MethodologyBlock(
            title="Disclosure Lag",
            content=(
                "Disclosure lag = reported_date − trade_date. "
                "Negative values are flagged as data quality issues and reduce confidence scores."
            ),
        ),
        MethodologyBlock(
            title="Provenance",
            content=(
                "Every trade and filing includes: source URL, retrieval timestamp, and file hash. "
                "If any provenance field is missing, the API response includes provenance_complete=false."
            ),
        ),
        MethodologyBlock(
            title="Disclosure Completeness Scorecard",
            content=(
                "Completeness rating starts at 100. Deductions apply for: missing filings (-30), "
                "high median lag >90d (-25), elevated lag >45d (-15), negative lag trades (-10), "
                "low parsing confidence (-10). Grades: A (90+), B (80-89), C (70-79), D (60-69), F (<60)."
                " These are data-quality and reporting-timeliness indicators, not ethics ratings, "
                "compliance findings, integrity scores, or investment-performance assessments."
            ),
        ),
    ]
    key_rules = [
        "Neutrality: present facts, not judgments",
        "Market-adjusted benchmarks with disclosed methodology",
        "Full provenance chain for every data point",
        "Scorecard grading based on disclosure completeness and data-quality metrics",
        "Branch-aware source intake for legislative, executive, and judicial disclosures",
    ]
    return MethodologyResponse(blocks=blocks, key_rules=key_rules)


@router.get("/sources", response_model=OfficialSourcesResponse)
async def get_sources():
    return OfficialSourcesResponse.model_validate(get_official_sources_response())


@router.get("/source-completeness", response_model=SourceCompletenessResponse)
async def get_source_completeness(db: AsyncSession = Depends(get_db)):
    sources = get_official_sources_response()["sources"]
    completed = await crud.get_completed_ingestion_source_names(db)
    raw_counts = await crud.count_raw_documents_by_source(db)
    filing_counts = await crud.count_filings_by_source(db)

    items = []
    for source in sources:
        source_id = source["id"]
        has_completed = source_id in completed
        missing = []
        if not has_completed:
            missing.append("completed official-source ingestion")
        if raw_counts.get(source_id, 0) == 0:
            missing.append("archived raw documents")
        if filing_counts.get(source_id, 0) == 0:
            missing.append("normalized filings")

        items.append(
            SourceCompletenessItem(
                source_id=source_id,
                branch=source["branch"],
                ingestion_status=source["ingestion_status"],
                has_completed_ingestion=has_completed,
                raw_document_count=raw_counts.get(source_id, 0),
                filing_count=filing_counts.get(source_id, 0),
                provenance_requirements_count=len(source["provenance_requirements"]),
                missing_capabilities=missing,
            )
        )

    return SourceCompletenessResponse(dataset_version=settings.DATASET_VERSION, sources=items)
