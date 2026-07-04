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
    chamber = Column(Text, nullable=False)
    state = Column(Text, nullable=False)
    party = Column(Text, nullable=False)
    district = Column(Text, nullable=True)
    service_start = Column(Date, nullable=False)
    service_end = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    filings = relationship("Filing", back_populates="person")
    trades = relationship("Trade", back_populates="person")


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
    superseded_by_filing_id = Column(UUID(as_uuid=True), ForeignKey("filings.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    person = relationship("Person", back_populates="filings")
    trades = relationship("Trade", back_populates="filing")


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
    methodology_version = Column(Text, nullable=False)
    render_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
