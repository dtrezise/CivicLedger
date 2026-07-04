from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from typing import Optional


# ---- People ----

class PersonSummary(BaseModel):
    person_id: UUID
    full_name: str
    chamber: str
    state: str
    party: str
    service_start: date
    service_end: Optional[date] = None

    class Config:
        from_attributes = True


class PersonDetail(PersonSummary):
    branch: str
    district: Optional[str] = None
    created_at: Optional[datetime] = None


class PersonListResponse(BaseModel):
    items: list[PersonSummary]
    page: int
    page_size: int
    total: int


class PersonBatchStatsItem(BaseModel):
    trades_count: int
    last_filing_processed_at: Optional[datetime] = None
    median_lag_days: Optional[float] = None


class PersonBatchStatsResponse(BaseModel):
    by_id: dict[str, PersonBatchStatsItem]


# ---- Scorecard ----

class ScorecardMetrics(BaseModel):
    trade_count: int
    filing_count: int
    median_lag_days: Optional[float] = None
    negative_lag_count: int = 0
    low_parser_confidence_count: int = 0


class ScorecardDeduction(BaseModel):
    rule_id: str
    points: int
    explanation: str
    evidence_count: int


class ScorecardResponse(BaseModel):
    transaction_level_reporting: str
    typical_reporting_lag_days: Optional[float] = None
    disclosure_type: str = "transactions"
    completeness_rating: int
    grade: str
    notes: list[str]
    metrics: ScorecardMetrics
    deductions: list[ScorecardDeduction]


# ---- Timeline ----

class TimelineBucket(BaseModel):
    start: date
    end: date
    trade_count: int
    buy_count: int
    sell_count: int
    median_lag_days: Optional[float] = None


class TimelineGap(BaseModel):
    start: date
    end: date
    gap_type: str
    display_label: str


class TimelineResponse(BaseModel):
    bucket: str
    start: Optional[date] = None
    end: Optional[date] = None
    buckets: list[TimelineBucket]
    gaps: list[TimelineGap]


# ---- Trades ----

class TradeRow(BaseModel):
    id: UUID
    person_id: UUID
    filing_id: UUID
    trade_date: date
    reported_date: date
    action: str
    raw_asset_text: str
    asset_display_name: str
    ticker: Optional[str] = None
    asset_class: str
    value_range_label: str
    value_range_min: Optional[Decimal] = None
    value_range_max: Optional[Decimal] = None
    disclosure_lag_days: int
    parsing_confidence: Optional[Decimal] = None
    asset_match_confidence: Optional[Decimal] = None

    class Config:
        from_attributes = True


class TradeListResponse(BaseModel):
    items: list[TradeRow]
    page: int
    page_size: int
    total: int


class ProvenanceInfo(BaseModel):
    source_url: str
    retrieved_at: datetime
    file_hash: str
    provenance_complete: bool


class TradeDetail(TradeRow):
    provenance: ProvenanceInfo


# ---- Filings ----

class FilingDetail(BaseModel):
    id: UUID
    person_id: UUID
    filing_type: str
    filed_date: date
    source_url: str
    retrieved_at: datetime
    file_hash: str
    retrieval_source: str
    raw_document_id: Optional[UUID] = None
    superseded_by_filing_id: Optional[UUID] = None
    provenance_complete: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---- Market ----

class MarketPoint(BaseModel):
    date: date
    value: Decimal


class MarketSeriesItem(BaseModel):
    symbol: str
    freq: str
    start: date
    end: date
    points: list[MarketPoint]


# ---- Events ----

class EventItem(BaseModel):
    event_id: UUID
    date: date
    label: str
    event_type: str
    source_links: list[str]
    description: Optional[str] = None


# ---- ShareCards ----

class ShareCardCreateRequest(BaseModel):
    scope: str
    person_id: UUID
    trade_id: Optional[UUID] = None
    start: Optional[date] = None
    end: Optional[date] = None
    overlays: list[str] = ["SPY", "DIA"]
    include_events: bool = True


class ShareCardCreateResponse(BaseModel):
    sharecard_id: UUID
    render_url: Optional[str] = None
    permalink_url: Optional[str] = None
    sources: list[str]
    disclaimer_text: str
    dataset_version: str
    methodology_version: str
    generated_at: datetime


class ShareCardDetail(BaseModel):
    id: UUID
    scope: str
    person_id: UUID
    trade_id: Optional[UUID] = None
    range_start: Optional[date] = None
    range_end: Optional[date] = None
    overlays: list[str]
    include_events: bool
    sources: list[str]
    disclaimer_text: str
    dataset_version: str
    methodology_version: str
    render_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---- Meta ----

class MetaStatusResponse(BaseModel):
    last_ingestion_run_at: Optional[datetime] = None
    dataset_version: str
    parser_version: str
    methodology_version: str


class MethodologyBlock(BaseModel):
    title: str
    content: str


class MethodologyResponse(BaseModel):
    blocks: list[MethodologyBlock]
    key_rules: list[str]
