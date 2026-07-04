from fastapi import APIRouter
from app.config import settings
from app.schemas import MetaStatusResponse, MethodologyResponse, MethodologyBlock

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
                "CivicLedger tracks financial disclosures filed by members of U.S. Congress "
                "under the STOCK Act. All data is sourced from publicly available Periodic "
                "Transaction Reports (PTRs) filed with the Clerk of the House and the "
                "Secretary of the Senate."
            ),
        ),
        MethodologyBlock(
            title="Neutrality Principle",
            content=(
                "CivicLedger presents factual disclosure data without editorial judgment. "
                "We do not characterize trades as suspicious, well-timed, or improper. "
                "Market overlay comparisons provide context, not conclusions."
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
            title="Scorecard Grading",
            content=(
                "Completeness rating starts at 100. Deductions apply for: missing filings (-30), "
                "high median lag >90d (-25), elevated lag >45d (-15), negative lag trades (-10), "
                "low parsing confidence (-10). Grades: A (90+), B (80-89), C (70-79), D (60-69), F (<60)."
            ),
        ),
    ]
    key_rules = [
        "Neutrality: present facts, not judgments",
        "Market-adjusted benchmarks with disclosed methodology",
        "Full provenance chain for every data point",
        "Scorecard grading based on disclosure quality metrics",
    ]
    return MethodologyResponse(blocks=blocks, key_rules=key_rules)
