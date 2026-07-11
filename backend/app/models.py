import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Text, Date, Integer, Numeric, Boolean,
    ForeignKey, DateTime, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "people"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(Text, nullable=False)
    branch = Column(Text, nullable=False, default="Legislative")
    chamber = Column(Text, nullable=True)
    state = Column(Text, nullable=True)
    party = Column(Text, nullable=True)
    district = Column(Text, nullable=True)
    office = Column(Text, nullable=True)
    agency = Column(Text, nullable=True)
    court = Column(Text, nullable=True)
    service_start = Column(Date, nullable=False)
    service_end = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    filings = relationship("Filing", back_populates="person")
    trades = relationship("Trade", back_populates="person")
    public_official_roles = relationship("PublicOfficialRole", back_populates="person")
    congressional_service_terms = relationship("CongressionalServiceTerm", back_populates="person")
    service_periods = relationship("ServicePeriod", back_populates="person")


class PublicOfficialRole(Base):
    __tablename__ = "public_official_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=False)
    external_role_id = Column(Text, nullable=False, unique=True)
    external_person_id = Column(Text, nullable=False)
    branch = Column(Text, nullable=False)
    presidential_term = Column(Text, nullable=False)
    administration = Column(Text, nullable=False)
    role_category = Column(Text, nullable=False)
    role_title = Column(Text, nullable=False)
    office = Column(Text, nullable=True)
    agency = Column(Text, nullable=True)
    court = Column(Text, nullable=True)
    service_start = Column(Date, nullable=True)
    service_end = Column(Date, nullable=True)
    appointing_president = Column(Text, nullable=True)
    source_id = Column(Text, nullable=False)
    source_name = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    source_tier = Column(Text, nullable=False, default="official")
    source_retrieved_at = Column(Date, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    person = relationship("Person", back_populates="public_official_roles")


class CongressionalServiceTerm(Base):
    __tablename__ = "congressional_service_terms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=False)
    bioguide_id = Column(Text, nullable=False)
    congress_number = Column(Integer, nullable=False)
    chamber = Column(Text, nullable=False)
    state = Column(Text, nullable=True)
    district = Column(Text, nullable=True)
    party = Column(Text, nullable=True)
    service_start = Column(Date, nullable=True)
    service_end = Column(Date, nullable=True)
    source_id = Column(Text, nullable=False)
    source_name = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    source_retrieved_at = Column(Date, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    person = relationship("Person", back_populates="congressional_service_terms")

    __table_args__ = (
        UniqueConstraint(
            "bioguide_id",
            "congress_number",
            "chamber",
            "state",
            "district",
            name="uq_congressional_service_terms_identity",
        ),
        Index("idx_congressional_service_terms_person", "person_id"),
        Index("idx_congressional_service_terms_bioguide", "bioguide_id"),
        Index("idx_congressional_service_terms_congress", "congress_number", "chamber"),
        Index("idx_congressional_service_terms_state_party", "state", "party"),
    )


class ServicePeriod(Base):
    __tablename__ = "service_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=False)
    public_official_role_id = Column(
        UUID(as_uuid=True), ForeignKey("public_official_roles.id"), nullable=True
    )
    branch = Column(Text, nullable=False)
    role_title = Column(Text, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    source_id = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    person = relationship("Person", back_populates="service_periods")

    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "role_title",
            "start_date",
            "source_id",
            name="uq_service_periods_identity",
        ),
        Index("idx_service_periods_person_dates", "person_id", "start_date", "end_date"),
        Index("idx_service_periods_branch_dates", "branch", "start_date", "end_date"),
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name = Column(Text, nullable=False)
    source_url = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Text, nullable=False)
    dataset_version = Column(Text, nullable=False)
    parser_version = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    raw_documents = relationship("RawDocument", back_populates="ingestion_run")


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingestion_run_id = Column(UUID(as_uuid=True), ForeignKey("ingestion_runs.id"), nullable=False)
    source_url = Column(Text, nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    retrieval_source = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False)
    file_hash = Column(Text, nullable=False)
    storage_uri = Column(Text, nullable=True)
    rights_status = Column(Text, nullable=False, default="public_record")
    parser_version = Column(Text, nullable=False)
    provenance_complete = Column(Boolean, nullable=False, default=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    ingestion_run = relationship("IngestionRun", back_populates="raw_documents")
    filings = relationship("Filing", back_populates="raw_document")
    parser_artifacts = relationship("ParserArtifact", back_populates="raw_document")


class Filing(Base):
    __tablename__ = "filings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=False)
    filing_type = Column(Text, nullable=False, default="PTR")
    filed_date = Column(Date, nullable=False)
    source_url = Column(Text, nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    file_hash = Column(Text, nullable=False)
    retrieval_source = Column(Text, nullable=False, default="fixture")
    raw_document_id = Column(UUID(as_uuid=True), ForeignKey("raw_documents.id"), nullable=True)
    superseded_by_filing_id = Column(UUID(as_uuid=True), ForeignKey("filings.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    person = relationship("Person", back_populates="filings")
    trades = relationship("Trade", back_populates="filing")
    raw_document = relationship("RawDocument", back_populates="filings")
    parser_artifacts = relationship("ParserArtifact", back_populates="filing")


class Issuer(Base):
    __tablename__ = "issuers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name = Column(Text, nullable=False)
    cik = Column(Text, nullable=True)
    lei = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    assets = relationship("Asset", back_populates="issuer")

    __table_args__ = (
        UniqueConstraint("canonical_name", "cik", name="uq_issuers_name_cik"),
        Index("idx_issuers_cik", "cik"),
    )


class Asset(Base):
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issuer_id = Column(UUID(as_uuid=True), ForeignKey("issuers.id"), nullable=True)
    canonical_name = Column(Text, nullable=False)
    asset_class = Column(Text, nullable=False)
    primary_symbol = Column(Text, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    issuer = relationship("Issuer", back_populates="assets")
    trades = relationship("Trade", back_populates="asset")

    __table_args__ = (
        UniqueConstraint(
            "canonical_name", "asset_class", "primary_symbol", name="uq_assets_identity"
        ),
        Index("idx_assets_symbol", "primary_symbol"),
        Index("idx_assets_issuer", "issuer_id"),
    )


class Trade(Base):
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=False)
    filing_id = Column(UUID(as_uuid=True), ForeignKey("filings.id"), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True)
    trade_date = Column(Date, nullable=False)
    reported_date = Column(Date, nullable=False)
    action = Column(Text, nullable=False)
    raw_asset_text = Column(Text, nullable=False)
    asset_display_name = Column(Text, nullable=False)
    ticker = Column(Text, nullable=True)
    asset_class = Column(Text, nullable=False)
    value_range_label = Column(Text, nullable=False)
    value_range_min = Column(Numeric, nullable=True)
    value_range_max = Column(Numeric, nullable=True)
    disclosure_lag_days = Column(Integer, nullable=False)
    parsing_confidence = Column(Numeric, nullable=True)
    asset_match_confidence = Column(Numeric, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    person = relationship("Person", back_populates="trades")
    filing = relationship("Filing", back_populates="trades")
    asset = relationship("Asset", back_populates="trades")
    parser_artifacts = relationship("ParserArtifact", back_populates="trade")


class ParserArtifact(Base):
    __tablename__ = "parser_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(Text, nullable=False)
    raw_document_id = Column(UUID(as_uuid=True), ForeignKey("raw_documents.id"), nullable=False)
    filing_id = Column(UUID(as_uuid=True), ForeignKey("filings.id"), nullable=True)
    trade_id = Column(UUID(as_uuid=True), ForeignKey("trades.id"), nullable=True)
    artifact_type = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    row_number = Column(Integer, nullable=True)
    text_span = Column(JSONB, nullable=False, default=dict)
    parser_output = Column(JSONB, nullable=False, default=dict)
    confidence = Column(Numeric, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    raw_document = relationship("RawDocument", back_populates="parser_artifacts")
    filing = relationship("Filing", back_populates="parser_artifacts")
    trade = relationship("Trade", back_populates="parser_artifacts")


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(Date, nullable=False)
    label = Column(Text, nullable=False)
    event_type = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    announcement_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    publication_date = Column(Date, nullable=True)
    source_tier = Column(Text, nullable=False, default="official")
    editor_status = Column(Text, nullable=False, default="curated")
    methodology_version = Column(Text, nullable=False, default="event-relevance-v1")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    sources = relationship("EventSource", back_populates="event")
    relationships = relationship("EventRelationship", back_populates="event")
    trade_candidates = relationship("TradeEventCandidate", back_populates="event")


class EventSource(Base):
    __tablename__ = "event_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    url = Column(Text, nullable=False)

    event = relationship("Event", back_populates="sources")


class EventRelationship(Base):
    __tablename__ = "event_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True)
    organization_name = Column(Text, nullable=True)
    relationship_type = Column(Text, nullable=False)
    evidence_tier = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    methodology_version = Column(Text, nullable=False)
    review_status = Column(Text, nullable=False, default="candidate")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    event = relationship("Event", back_populates="relationships")

    __table_args__ = (
        CheckConstraint(
            "person_id IS NOT NULL OR asset_id IS NOT NULL OR organization_name IS NOT NULL",
            name="ck_event_relationships_target",
        ),
        Index("idx_event_relationships_event", "event_id"),
        Index("idx_event_relationships_person", "person_id"),
        Index("idx_event_relationships_asset", "asset_id"),
        Index("idx_event_relationships_tier", "evidence_tier", "review_status"),
    )


class TradeEventCandidate(Base):
    __tablename__ = "trade_event_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id = Column(UUID(as_uuid=True), ForeignKey("trades.id"), nullable=False)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    days_from_event = Column(Integer, nullable=False)
    evidence_tier = Column(Text, nullable=False)
    relationship_reasons = Column(JSONB, nullable=False, default=list)
    internal_rank = Column(Numeric, nullable=True)
    methodology_version = Column(Text, nullable=False)
    review_status = Column(Text, nullable=False, default="candidate")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    event = relationship("Event", back_populates="trade_candidates")
    reviews = relationship("RelationshipReview", back_populates="candidate")

    __table_args__ = (
        UniqueConstraint(
            "trade_id", "event_id", "methodology_version", name="uq_trade_event_candidates_version"
        ),
        Index("idx_trade_event_candidates_trade", "trade_id"),
        Index("idx_trade_event_candidates_event", "event_id"),
        Index("idx_trade_event_candidates_tier", "evidence_tier", "review_status"),
    )


class RelationshipReview(Base):
    __tablename__ = "relationship_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(
        UUID(as_uuid=True), ForeignKey("trade_event_candidates.id"), nullable=False
    )
    decision = Column(Text, nullable=False)
    reviewer = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    candidate = relationship("TradeEventCandidate", back_populates="reviews")

    __table_args__ = (Index("idx_relationship_reviews_candidate", "candidate_id"),)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(Text, nullable=False)
    issue_type = Column(Text, nullable=False)
    severity = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="open")
    details = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_data_quality_issues_entity", "entity_type", "entity_id"),
        Index("idx_data_quality_issues_status", "status", "severity"),
    )


class MarketSeries(Base):
    __tablename__ = "market_series"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(Text, nullable=False)
    freq = Column(Text, nullable=False, default="d")
    date = Column(Date, nullable=False)
    value = Column(Numeric, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "freq", "date"),
    )


class ShareCard(Base):
    __tablename__ = "sharecards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(Text, nullable=False)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=False)
    trade_id = Column(UUID(as_uuid=True), ForeignKey("trades.id"), nullable=True)
    range_start = Column(Date, nullable=True)
    range_end = Column(Date, nullable=True)
    overlays = Column(JSONB, nullable=False, default=["SPY", "DIA"])
    include_events = Column(Boolean, nullable=False, default=True)
    sources = Column(JSONB, nullable=False, default=[])
    disclaimer_text = Column(Text, nullable=False)
    dataset_version = Column(Text, nullable=False)
    methodology_version = Column(Text, nullable=False)
    render_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
