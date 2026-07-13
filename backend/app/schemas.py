from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID
from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


# ---- People ----

class PersonSummary(BaseModel):
    person_id: UUID
    full_name: str
    branch: str
    chamber: Optional[str] = None
    state: Optional[str] = None
    party: Optional[str] = None
    office: Optional[str] = None
    agency: Optional[str] = None
    court: Optional[str] = None
    service_start: date
    service_end: Optional[date] = None

    class Config:
        from_attributes = True


class PersonDetail(PersonSummary):
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


# ---- Public Official Roles ----

class PublicOfficialRoleItem(BaseModel):
    role_id: UUID
    person_id: UUID
    external_role_id: str
    external_person_id: str
    full_name: str
    branch: str
    presidential_term: str
    administration: str
    role_category: str
    role_title: str
    office: Optional[str] = None
    agency: Optional[str] = None
    court: Optional[str] = None
    service_start: Optional[date] = None
    service_end: Optional[date] = None
    appointing_president: Optional[str] = None
    source_id: str
    source_name: str
    source_url: str
    source_tier: str
    source_retrieved_at: Optional[date] = None
    source_metadata: dict


class PublicOfficialRoleListResponse(BaseModel):
    items: list[PublicOfficialRoleItem]
    page: int
    page_size: int
    total: int


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


class RawDocumentDetail(BaseModel):
    id: UUID
    ingestion_run_id: UUID
    source_url: str
    retrieved_at: datetime
    retrieval_source: str
    content_type: str
    file_hash: str
    storage_uri: Optional[str] = None
    rights_status: str
    parser_version: str
    provenance_complete: bool
    source_metadata: dict
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


class OfficialSourceInfo(BaseModel):
    id: str
    name: str
    branch: str
    chamber: Optional[str] = None
    source_url: str
    search_url: Optional[str] = None
    download_url: Optional[str] = None
    access_mode: Optional[str] = None
    public_sample_url: Optional[str] = None
    ingestion_status: str
    records_scope: str
    rights_note: str
    provenance_requirements: list[str]


class OfficialSourcesResponse(BaseModel):
    dataset_version: str
    methodology_version: str
    sources: list[OfficialSourceInfo]


class SourceCompletenessItem(BaseModel):
    source_id: str
    branch: str
    ingestion_status: str
    has_completed_ingestion: bool
    raw_document_count: int
    filing_count: int
    provenance_requirements_count: int
    missing_capabilities: list[str]


class SourceCompletenessResponse(BaseModel):
    dataset_version: str
    sources: list[SourceCompletenessItem]


class ParserArtifactItem(BaseModel):
    id: UUID
    source_id: str
    raw_document_id: UUID
    filing_id: Optional[UUID] = None
    trade_id: Optional[UUID] = None
    artifact_type: str
    page_number: Optional[int] = None
    row_number: Optional[int] = None
    text_span: dict
    parser_output: dict
    confidence: Optional[Decimal] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ParserArtifactListResponse(BaseModel):
    items: list[ParserArtifactItem]
    page: int
    page_size: int
    total: int


class PromotePreviewRequest(BaseModel):
    reviewer: str
    person_name: str
    branch: str
    chamber: Optional[str] = None
    state: Optional[str] = None
    party: Optional[str] = None
    office: Optional[str] = None
    agency: Optional[str] = None
    court: Optional[str] = None


class PromotePreviewResponse(BaseModel):
    filing_id: UUID
    trade_count: int


class RollbackFilingRequest(BaseModel):
    reviewer: str
    reason: str


class RollbackFilingResponse(BaseModel):
    filing_id: str
    reviewed_by: str
    reason: str
    deleted_trade_count: int
    deleted_artifact_count: int


class SupersedeFilingRequest(BaseModel):
    superseded_by_filing_id: UUID
    reviewer: str
    reason: str


# ---- Relationship Candidate Review ----

class RelationshipReviewDecision(str, Enum):
    ACCEPT = "accept"
    NARROW = "narrow"
    REJECT = "reject"
    SUPERSEDE = "supersede"


class RelationshipCandidateStatus(str, Enum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    NARROWED = "narrowed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class RelationshipCandidateSort(str, Enum):
    PRIORITY = "priority"
    NEWEST = "newest"
    OLDEST = "oldest"
    EVENT_DATE = "event_date"
    TRADE_DATE = "trade_date"


class RelationshipReviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: RelationshipReviewDecision
    reviewer: str = Field(min_length=1, max_length=200)
    evidence_note: str = Field(
        min_length=1,
        max_length=5000,
        validation_alias=AliasChoices("evidence_note", "reason"),
    )
    expected_status: RelationshipCandidateStatus | None = None
    expected_revision: str | None = Field(default=None, min_length=64, max_length=64)
    review_session_id: UUID | None = None

    @field_validator("reviewer", "evidence_note")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RelationshipReviewHistoryItem(BaseModel):
    id: UUID
    candidate_id: UUID
    decision: RelationshipReviewDecision
    reviewer: str
    evidence_note: str
    reviewed_at: datetime


class RelationshipBulkReviewTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    expected_status: RelationshipCandidateStatus
    expected_revision: str = Field(min_length=64, max_length=64)


class RelationshipBulkReviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: RelationshipReviewDecision
    reviewer: str = Field(min_length=1, max_length=200)
    evidence_note: str = Field(min_length=1, max_length=5000)
    targets: list[RelationshipBulkReviewTarget] = Field(min_length=1, max_length=100)
    review_session_id: UUID | None = None

    @field_validator("reviewer", "evidence_note")
    @classmethod
    def strip_bulk_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("targets")
    @classmethod
    def reject_duplicate_targets(
        cls, targets: list[RelationshipBulkReviewTarget]
    ) -> list[RelationshipBulkReviewTarget]:
        candidate_ids = [target.candidate_id for target in targets]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_id values must be unique")
        return targets


class TradeEventCandidateReviewItem(BaseModel):
    id: UUID
    trade_id: UUID
    event_id: UUID
    person_id: UUID
    person_name: str
    trade_date: date
    reported_date: date
    action: str
    asset_display_name: str
    ticker: Optional[str] = None
    asset_class: str
    value_range_label: str
    event_date: date
    event_label: str
    event_type: str
    event_description: Optional[str] = None
    days_from_event: int
    evidence_tier: str
    relationship_reasons: list[str | dict]
    internal_rank: Optional[Decimal] = None
    methodology_version: str
    review_status: RelationshipCandidateStatus
    review_revision: str
    created_at: Optional[datetime] = None
    reviews: list[RelationshipReviewHistoryItem]


class TradeEventCandidateReviewListResponse(BaseModel):
    items: list[TradeEventCandidateReviewItem]
    page: int
    page_size: int
    total: int
    sort: RelationshipCandidateSort = RelationshipCandidateSort.PRIORITY


class RelationshipBulkReviewResponse(BaseModel):
    updated_count: int
    items: list[TradeEventCandidateReviewItem]


class RelationshipAuditExportRecord(BaseModel):
    review_id: UUID
    candidate_id: UUID
    trade_id: UUID
    event_id: UUID
    methodology_version: str
    decision: RelationshipReviewDecision
    reviewer: str
    evidence_note: str
    reviewed_at: datetime
    review_session_id: UUID | None = None


class ReviewAssignmentAction(str, Enum):
    ASSIGN = "assign"
    RELEASE = "release"
    COMPLETE = "complete"


class ReviewAssignmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    action: ReviewAssignmentAction
    assignee: str | None = Field(default=None, max_length=200)
    actor: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("assignee", "actor", "note")
    @classmethod
    def strip_assignment_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ReviewAssignmentItem(BaseModel):
    id: UUID
    candidate_id: UUID
    action: ReviewAssignmentAction
    assignee: str | None
    actor: str
    note: str | None
    occurred_at: datetime


class ReviewFilterCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RelationshipCandidateStatus | None = None
    evidence_tier: str | None = Field(default=None, max_length=100)
    event_type: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, max_length=200)
    max_abs_days: int | None = Field(default=None, ge=0, le=3650)
    min_internal_rank: float | None = Field(default=None, ge=0)
    has_reviews: bool | None = None
    sort: RelationshipCandidateSort = RelationshipCandidateSort.PRIORITY
    page_size: int = Field(default=25, ge=1, le=100)


class ReviewSavedFilterCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    criteria: ReviewFilterCriteria

    @field_validator("owner", "name")
    @classmethod
    def strip_filter_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ReviewSavedFilterItem(BaseModel):
    id: UUID
    owner: str
    name: str
    criteria: ReviewFilterCriteria
    created_at: datetime


class ReviewSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=200)
    filter_snapshot: ReviewFilterCriteria = Field(default_factory=ReviewFilterCriteria)

    @field_validator("reviewer")
    @classmethod
    def strip_session_reviewer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ReviewSessionCloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=200)

    @field_validator("reviewer")
    @classmethod
    def strip_close_reviewer(cls, value: str) -> str:
        return value.strip()


class ReviewSessionItem(BaseModel):
    id: UUID
    reviewer: str
    status: str
    filter_snapshot: ReviewFilterCriteria
    started_at: datetime
    completed_at: datetime | None
    decision_count: int
    decision_counts: dict[str, int]


class RelationshipAuditExportResponse(BaseModel):
    schema_version: str
    export_id: str
    content_sha256: str
    snapshot_through: datetime | None
    record_count: int
    interpretation_boundary: str
    records: list[RelationshipAuditExportRecord]


class ReviewerTelemetrySummary(BaseModel):
    refresh_run_count: int
    measured_refresh_count: int
    failed_refresh_count: int
    source_failure_count: int
    data_drift_count: int


class ReviewerRefreshRun(BaseModel):
    run_id: str
    source_id: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    failure_count: int


class ReviewerRefreshDuration(BaseModel):
    unit: str
    p50: float | None
    p95: float | None
    maximum: float | None
    runs: list[ReviewerRefreshRun]


class ReviewerSourceFailure(BaseModel):
    source_id: str
    source_artifact: str
    metric: str
    failure_count: int


class ReviewerDataDrift(BaseModel):
    source_id: str
    path: str
    status: str
    baseline_schema_version: str | None
    current_schema_version: str | None
    count_metric: str
    baseline_record_count: int | None
    current_record_count: int | None
    baseline_summary_sha256: str | None
    current_summary_sha256: str | None


class ReviewerTelemetryResponse(BaseModel):
    schema_version: str
    generated_at: date
    status: str
    interpretation_boundary: str
    summary: ReviewerTelemetrySummary
    refresh_duration: ReviewerRefreshDuration
    source_failures: list[ReviewerSourceFailure]
    data_drift: list[ReviewerDataDrift]


class IngestionRunItem(BaseModel):
    id: UUID
    source_name: str
    source_url: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    dataset_version: str
    parser_version: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IngestionRunListResponse(BaseModel):
    items: list[IngestionRunItem]
    page: int
    page_size: int
    total: int


class EvidenceSearchResponse(BaseModel):
    items: list[ParserArtifactItem]
    page: int
    page_size: int
    total: int


class DuplicateTradeGroup(BaseModel):
    duplicate_key: str
    trade_ids: list[UUID]
    person_id: UUID
    trade_date: date
    action: str
    asset_display_name: str
    value_range_label: str
    count: int


class DuplicateFilingGroup(BaseModel):
    duplicate_key: str
    filing_ids: list[UUID]
    person_id: UUID
    filed_date: date
    filing_type: str
    file_hash: str
    count: int


class DuplicateReportResponse(BaseModel):
    trade_groups: list[DuplicateTradeGroup]
    filing_groups: list[DuplicateFilingGroup]
