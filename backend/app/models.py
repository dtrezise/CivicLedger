import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Text, Date, Integer, Numeric, Boolean,
    ForeignKey, DateTime, Index, UniqueConstraint, CheckConstraint, text,
    event as sqlalchemy_event,
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
    source_system = Column(Text, nullable=False, default="unknown")
    source_filing_id = Column(Text, nullable=True)
    reporting_period_start = Column(Date, nullable=True)
    reporting_period_end = Column(Date, nullable=True)
    received_date = Column(Date, nullable=True)
    certified_date = Column(Date, nullable=True)
    amendment_number = Column(Integer, nullable=False, default=0)
    amends_filing_id = Column(UUID(as_uuid=True), ForeignKey("filings.id"), nullable=True)
    filing_status = Column(Text, nullable=False, default="filed")
    review_status = Column(Text, nullable=False, default="candidate")
    is_late = Column(Boolean, nullable=True)
    late_days = Column(Integer, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    person = relationship("Person", back_populates="filings")
    trades = relationship("Trade", back_populates="filing")
    raw_document = relationship("RawDocument", back_populates="filings")
    parser_artifacts = relationship("ParserArtifact", back_populates="filing")

    __table_args__ = (
        CheckConstraint(
            "reporting_period_end IS NULL OR reporting_period_start IS NULL "
            "OR reporting_period_end >= reporting_period_start",
            name="ck_filings_reporting_period",
        ),
        CheckConstraint("amendment_number >= 0", name="ck_filings_amendment_number"),
        CheckConstraint("length(btrim(source_system)) > 0", name="ck_filings_source_system"),
        CheckConstraint(
            "filing_status IN ('filed','amended','superseded','withdrawn','unknown')",
            name="ck_filings_status",
        ),
        CheckConstraint(
            "review_status IN ('candidate','reviewed','promoted','rejected','superseded')",
            name="ck_filings_review_status",
        ),
        CheckConstraint(
            "amends_filing_id IS NULL OR amends_filing_id <> id",
            name="ck_filings_not_self_amendment",
        ),
        CheckConstraint("late_days IS NULL OR late_days >= 0", name="ck_filings_late_days"),
        Index(
            "uq_filings_source_identity",
            "source_system",
            "source_filing_id",
            unique=True,
            postgresql_where=text("source_filing_id IS NOT NULL"),
        ),
        Index("idx_filings_person_period", "person_id", "reporting_period_start", "reporting_period_end"),
        Index("idx_filings_review_status", "review_status", "filed_date"),
        Index("idx_filings_amends", "amends_filing_id"),
    )


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    code = Column(Text, nullable=False)
    jurisdiction_type = Column(Text, nullable=False)
    country_code = Column(String(2), nullable=False, default="US")
    parent_jurisdiction_id = Column(
        UUID(as_uuid=True), ForeignKey("jurisdictions.id"), nullable=True
    )
    source_url = Column(Text, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    parent = relationship("Jurisdiction", remote_side=[id], back_populates="children")
    children = relationship("Jurisdiction", back_populates="parent")
    organizations = relationship("Organization", back_populates="jurisdiction")
    institutions = relationship("Institution", back_populates="jurisdiction")
    event_links = relationship("EventInstitutionLink", back_populates="jurisdiction")

    __table_args__ = (
        UniqueConstraint(
            "jurisdiction_type", "country_code", "code", name="uq_jurisdictions_identity"
        ),
        CheckConstraint(
            "parent_jurisdiction_id IS NULL OR parent_jurisdiction_id <> id",
            name="ck_jurisdictions_not_self_parent",
        ),
        Index("idx_jurisdictions_parent", "parent_jurisdiction_id"),
        Index("idx_jurisdictions_name", "name"),
    )


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_key = Column(Text, nullable=False)
    canonical_name = Column(Text, nullable=False)
    normalized_name = Column(Text, nullable=False)
    organization_type = Column(Text, nullable=False, default="company")
    country_code = Column(String(2), nullable=True)
    jurisdiction_id = Column(UUID(as_uuid=True), ForeignKey("jurisdictions.id"), nullable=True)
    website_url = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="active")
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    jurisdiction = relationship("Jurisdiction", back_populates="organizations")
    issuer_profile = relationship("Issuer", back_populates="organization", uselist=False)
    aliases = relationship("OrganizationAlias", back_populates="organization")
    identifiers = relationship("OrganizationIdentifier", back_populates="organization")
    parent_relationships = relationship(
        "OrganizationRelationship",
        foreign_keys="OrganizationRelationship.child_organization_id",
        back_populates="child_organization",
    )
    child_relationships = relationship(
        "OrganizationRelationship",
        foreign_keys="OrganizationRelationship.parent_organization_id",
        back_populates="parent_organization",
    )
    sector_assignments = relationship("OrganizationSector", back_populates="organization")
    ticker_histories = relationship("TickerHistory", back_populates="organization")
    institution = relationship("Institution", back_populates="organization", uselist=False)

    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_organizations_canonical_key"),
        CheckConstraint("length(btrim(canonical_name)) > 0", name="ck_organizations_name"),
        CheckConstraint("length(btrim(normalized_name)) > 0", name="ck_organizations_normalized_name"),
        CheckConstraint(
            "organization_type IN ('company','fund','government','nonprofit','partnership','trust','other')",
            name="ck_organizations_type",
        ),
        CheckConstraint(
            "status IN ('active','inactive','merged','dissolved','unknown')",
            name="ck_organizations_status",
        ),
        Index("idx_organizations_normalized_name", "normalized_name"),
        Index("idx_organizations_type_status", "organization_type", "status"),
        Index("idx_organizations_jurisdiction", "jurisdiction_id"),
    )


class Issuer(Base):
    __tablename__ = "issuers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    canonical_name = Column(Text, nullable=False)
    cik = Column(Text, nullable=True)
    lei = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    organization = relationship("Organization", back_populates="issuer_profile")
    assets = relationship("Asset", back_populates="issuer")

    __table_args__ = (
        UniqueConstraint("canonical_name", "cik", name="uq_issuers_name_cik"),
        UniqueConstraint("organization_id", name="uq_issuers_organization"),
        Index("idx_issuers_cik", "cik"),
        Index("idx_issuers_organization", "organization_id"),
    )


class OrganizationAlias(Base):
    __tablename__ = "organization_aliases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    alias = Column(Text, nullable=False)
    normalized_alias = Column(Text, nullable=False)
    alias_type = Column(Text, nullable=False, default="name")
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    confidence = Column(Numeric, nullable=True)
    source_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("event_source_snapshots.id"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="aliases")
    source_snapshot = relationship("EventSourceSnapshot")

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "normalized_alias", "alias_type", name="uq_organization_aliases_identity"
        ),
        CheckConstraint("length(btrim(alias)) > 0", name="ck_organization_aliases_alias"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_organization_aliases_dates",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_organization_aliases_confidence",
        ),
        Index("idx_organization_aliases_lookup", "normalized_alias"),
        Index("idx_organization_aliases_organization", "organization_id"),
    )


class OrganizationIdentifier(Base):
    __tablename__ = "organization_identifiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    scheme = Column(Text, nullable=False)
    value = Column(Text, nullable=False)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    source_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("event_source_snapshots.id"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="identifiers")
    source_snapshot = relationship("EventSourceSnapshot")

    __table_args__ = (
        UniqueConstraint("scheme", "value", name="uq_organization_identifiers_scheme_value"),
        CheckConstraint("length(btrim(value)) > 0", name="ck_organization_identifiers_value"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_organization_identifiers_dates",
        ),
        Index("idx_organization_identifiers_organization", "organization_id"),
        Index("idx_organization_identifiers_lookup", "scheme", "value"),
    )


class OrganizationRelationship(Base):
    __tablename__ = "organization_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    child_organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    relationship_type = Column(Text, nullable=False, default="parent")
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    ownership_percent = Column(Numeric, nullable=True)
    is_direct = Column(Boolean, nullable=False, default=True)
    source_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("event_source_snapshots.id"), nullable=True
    )
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    parent_organization = relationship(
        "Organization", foreign_keys=[parent_organization_id], back_populates="child_relationships"
    )
    child_organization = relationship(
        "Organization", foreign_keys=[child_organization_id], back_populates="parent_relationships"
    )
    source_snapshot = relationship("EventSourceSnapshot")

    __table_args__ = (
        CheckConstraint(
            "parent_organization_id <> child_organization_id",
            name="ck_organization_relationships_not_self",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_organization_relationships_dates",
        ),
        CheckConstraint(
            "ownership_percent IS NULL OR (ownership_percent >= 0 AND ownership_percent <= 100)",
            name="ck_organization_relationships_ownership",
        ),
        Index(
            "uq_organization_relationships_identity",
            "parent_organization_id",
            "child_organization_id",
            "relationship_type",
            "valid_from",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index("idx_organization_relationships_parent", "parent_organization_id", "valid_from", "valid_to"),
        Index("idx_organization_relationships_child", "child_organization_id", "valid_from", "valid_to"),
    )


class Sector(Base):
    __tablename__ = "sectors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    taxonomy = Column(Text, nullable=False)
    code = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    parent_sector_id = Column(UUID(as_uuid=True), ForeignKey("sectors.id"), nullable=True)
    level = Column(Integer, nullable=True)
    source_url = Column(Text, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    parent = relationship("Sector", remote_side=[id], back_populates="children")
    children = relationship("Sector", back_populates="parent")
    organization_assignments = relationship("OrganizationSector", back_populates="sector")

    __table_args__ = (
        UniqueConstraint("taxonomy", "code", name="uq_sectors_taxonomy_code"),
        CheckConstraint(
            "parent_sector_id IS NULL OR parent_sector_id <> id", name="ck_sectors_not_self_parent"
        ),
        CheckConstraint("level IS NULL OR level >= 0", name="ck_sectors_level"),
        Index("idx_sectors_parent", "parent_sector_id"),
        Index("idx_sectors_name", "taxonomy", "name"),
    )


class OrganizationSector(Base):
    __tablename__ = "organization_sectors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    sector_id = Column(UUID(as_uuid=True), ForeignKey("sectors.id"), nullable=False)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    confidence = Column(Numeric, nullable=True)
    source_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("event_source_snapshots.id"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="sector_assignments")
    sector = relationship("Sector", back_populates="organization_assignments")
    source_snapshot = relationship("EventSourceSnapshot")

    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_organization_sectors_dates",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_organization_sectors_confidence",
        ),
        Index(
            "uq_organization_sectors_identity",
            "organization_id",
            "sector_id",
            "valid_from",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "uq_organization_sectors_current_primary",
            "organization_id",
            unique=True,
            postgresql_where=text("is_primary AND valid_to IS NULL"),
        ),
        Index("idx_organization_sectors_sector", "sector_id", "valid_from", "valid_to"),
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
    ticker_histories = relationship("TickerHistory", back_populates="asset")

    __table_args__ = (
        UniqueConstraint(
            "canonical_name", "asset_class", "primary_symbol", name="uq_assets_identity"
        ),
        Index("idx_assets_symbol", "primary_symbol"),
        Index("idx_assets_issuer", "issuer_id"),
    )


class TickerHistory(Base):
    __tablename__ = "ticker_histories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    symbol = Column(Text, nullable=False)
    exchange = Column(Text, nullable=True)
    mic = Column(String(4), nullable=True)
    currency_code = Column(String(3), nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=True)
    source_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("event_source_snapshots.id"), nullable=True
    )
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="ticker_histories")
    organization = relationship("Organization", back_populates="ticker_histories")
    source_snapshot = relationship("EventSourceSnapshot")

    __table_args__ = (
        CheckConstraint("length(btrim(symbol)) > 0", name="ck_ticker_histories_symbol"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_ticker_histories_dates",
        ),
        Index(
            "uq_ticker_histories_identity",
            "asset_id",
            "symbol",
            "mic",
            "valid_from",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "uq_ticker_histories_current_primary",
            "asset_id",
            unique=True,
            postgresql_where=text("is_primary AND valid_to IS NULL"),
        ),
        Index("idx_ticker_histories_symbol_dates", "symbol", "valid_from", "valid_to"),
        Index("idx_ticker_histories_organization", "organization_id", "valid_from", "valid_to"),
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
    source_transaction_id = Column(Text, nullable=True)
    owner = Column(Text, nullable=False, default="unknown")
    asset_type_reported = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    source_page = Column(Integer, nullable=True)
    source_row = Column(Integer, nullable=True)
    capital_gains_over_200 = Column(Boolean, nullable=True)
    review_status = Column(Text, nullable=False, default="candidate")
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    person = relationship("Person", back_populates="trades")
    filing = relationship("Filing", back_populates="trades")
    asset = relationship("Asset", back_populates="trades")
    parser_artifacts = relationship("ParserArtifact", back_populates="trade")

    __table_args__ = (
        CheckConstraint(
            "owner IN ('self','spouse','dependent_child','joint','trust','other','unknown')",
            name="ck_trades_owner",
        ),
        CheckConstraint("source_page IS NULL OR source_page > 0", name="ck_trades_source_page"),
        CheckConstraint("source_row IS NULL OR source_row > 0", name="ck_trades_source_row"),
        CheckConstraint(
            "review_status IN ('candidate','reviewed','promoted','rejected','superseded')",
            name="ck_trades_review_status",
        ),
        Index(
            "uq_trades_source_transaction",
            "filing_id",
            "source_transaction_id",
            unique=True,
            postgresql_where=text("source_transaction_id IS NOT NULL"),
        ),
        Index("idx_trades_review_status", "review_status", "trade_date"),
    )


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
    institution_links = relationship("EventInstitutionLink", back_populates="event")


class EventSource(Base):
    __tablename__ = "event_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    url = Column(Text, nullable=False)
    source_type = Column(Text, nullable=False, default="web")
    title = Column(Text, nullable=True)
    publisher = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    event = relationship("Event", back_populates="sources")
    snapshots = relationship("EventSourceSnapshot", back_populates="event_source")

    __table_args__ = (
        Index("idx_event_sources_event", "event_id"),
        Index("idx_event_sources_url", "url"),
        Index("idx_event_sources_publisher", "publisher"),
    )


class EventSourceSnapshot(Base):
    __tablename__ = "event_source_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_source_id = Column(UUID(as_uuid=True), ForeignKey("event_sources.id"), nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
    hash_algorithm = Column(Text, nullable=False, default="sha256")
    content_hash = Column(Text, nullable=False)
    content_type = Column(Text, nullable=True)
    http_status = Column(Integer, nullable=True)
    final_url = Column(Text, nullable=True)
    storage_uri = Column(Text, nullable=True)
    content_length = Column(Integer, nullable=True)
    snapshot_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    event_source = relationship("EventSource", back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint(
            "event_source_id",
            "hash_algorithm",
            "content_hash",
            name="uq_event_source_snapshots_content",
        ),
        CheckConstraint("length(btrim(content_hash)) > 0", name="ck_event_source_snapshots_hash"),
        CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="ck_event_source_snapshots_http_status",
        ),
        CheckConstraint(
            "content_length IS NULL OR content_length >= 0",
            name="ck_event_source_snapshots_content_length",
        ),
        Index("idx_event_source_snapshots_source_retrieved", "event_source_id", "retrieved_at"),
        Index("idx_event_source_snapshots_hash", "hash_algorithm", "content_hash"),
    )


def _reject_event_source_snapshot_mutation(*_args, **_kwargs):
    raise ValueError("Event source snapshots are immutable; insert a new snapshot instead")


sqlalchemy_event.listen(
    EventSourceSnapshot, "before_update", _reject_event_source_snapshot_mutation, propagate=True
)
sqlalchemy_event.listen(
    EventSourceSnapshot, "before_delete", _reject_event_source_snapshot_mutation, propagate=True
)


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    institution_type = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    acronym = Column(Text, nullable=True)
    branch = Column(Text, nullable=True)
    chamber = Column(Text, nullable=True)
    jurisdiction_id = Column(UUID(as_uuid=True), ForeignKey("jurisdictions.id"), nullable=True)
    parent_institution_id = Column(
        UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=True
    )
    external_id = Column(Text, nullable=True)
    active_from = Column(Date, nullable=True)
    active_to = Column(Date, nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="institution")
    jurisdiction = relationship("Jurisdiction", back_populates="institutions")
    parent = relationship("Institution", remote_side=[id], back_populates="children")
    children = relationship("Institution", back_populates="parent")
    event_links = relationship("EventInstitutionLink", back_populates="institution")

    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_institutions_organization"),
        CheckConstraint(
            "institution_type IN ('agency','committee','subcommittee','court','office','legislature','other')",
            name="ck_institutions_type",
        ),
        CheckConstraint(
            "parent_institution_id IS NULL OR parent_institution_id <> id",
            name="ck_institutions_not_self_parent",
        ),
        CheckConstraint(
            "active_to IS NULL OR active_from IS NULL OR active_to >= active_from",
            name="ck_institutions_dates",
        ),
        Index("idx_institutions_type_name", "institution_type", "name"),
        Index("idx_institutions_jurisdiction", "jurisdiction_id"),
        Index("idx_institutions_parent", "parent_institution_id"),
        Index(
            "uq_institutions_external_identity",
            "institution_type",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )


class EventInstitutionLink(Base):
    __tablename__ = "event_institution_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    institution_id = Column(UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=False)
    jurisdiction_id = Column(UUID(as_uuid=True), ForeignKey("jurisdictions.id"), nullable=True)
    relationship_type = Column(Text, nullable=False)
    docket_number = Column(Text, nullable=True)
    proceeding_id = Column(Text, nullable=True)
    rationale = Column(Text, nullable=True)
    source_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("event_source_snapshots.id"), nullable=True
    )
    source_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    event = relationship("Event", back_populates="institution_links")
    institution = relationship("Institution", back_populates="event_links")
    jurisdiction = relationship("Jurisdiction", back_populates="event_links")
    source_snapshot = relationship("EventSourceSnapshot")

    __table_args__ = (
        Index(
            "uq_event_institution_links_identity",
            "event_id",
            "institution_id",
            "relationship_type",
            "docket_number",
            "proceeding_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index("idx_event_institution_links_event", "event_id"),
        Index("idx_event_institution_links_institution", "institution_id", "relationship_type"),
        Index("idx_event_institution_links_jurisdiction", "jurisdiction_id"),
        Index("idx_event_institution_links_docket", "docket_number"),
    )


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
