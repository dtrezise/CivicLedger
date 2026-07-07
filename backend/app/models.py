import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Text, Date, Integer, Numeric, Boolean,
    ForeignKey, DateTime, Index, UniqueConstraint
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


class Trade(Base):
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=False)
    filing_id = Column(UUID(as_uuid=True), ForeignKey("filings.id"), nullable=False)
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
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    sources = relationship("EventSource", back_populates="event")


class EventSource(Base):
    __tablename__ = "event_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    url = Column(Text, nullable=False)

    event = relationship("Event", back_populates="sources")


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
