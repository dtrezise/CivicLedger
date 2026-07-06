from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Filing, ParserArtifact, Person, RawDocument, Trade


VALUE_RANGE_DEFAULTS = {
    "$1,001 - $15,000": (Decimal("1001"), Decimal("15000")),
    "$15,001 - $50,000": (Decimal("15001"), Decimal("50000")),
    "$50,001 - $100,000": (Decimal("50001"), Decimal("100000")),
    "$100,001 - $250,000": (Decimal("100001"), Decimal("250000")),
    "$250,001 - $500,000": (Decimal("250001"), Decimal("500000")),
    "$500,001 - $1,000,000": (Decimal("500001"), Decimal("1000000")),
}


def parse_date(value: str | None, fallback: date | None = None) -> date:
    if value:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return fallback or date.today()


def parse_value_range(label: str) -> tuple[Decimal | None, Decimal | None]:
    if label in VALUE_RANGE_DEFAULTS:
        return VALUE_RANGE_DEFAULTS[label]
    return None, None


def disclosure_lag(trade_date: date, reported_date: date) -> int:
    return (reported_date - trade_date).days


def get_or_create_person(
    session: Session,
    *,
    full_name: str,
    branch: str,
    chamber: str | None = None,
    state: str | None = None,
    party: str | None = None,
    office: str | None = None,
    agency: str | None = None,
    court: str | None = None,
) -> Person:
    existing = session.execute(
        select(Person).where(Person.full_name == full_name, Person.branch == branch)
    ).scalar_one_or_none()
    if existing:
        return existing

    person = Person(
        id=uuid4(),
        full_name=full_name,
        branch=branch,
        chamber=chamber,
        state=state,
        party=party,
        office=office,
        agency=agency,
        court=court,
        service_start=date.today(),
    )
    session.add(person)
    session.flush()
    return person


def promote_preview_artifact(
    session: Session,
    *,
    preview_artifact_id: UUID,
    reviewer: str,
    person_name: str,
    branch: str,
    chamber: str | None = None,
    state: str | None = None,
    party: str | None = None,
    office: str | None = None,
    agency: str | None = None,
    court: str | None = None,
) -> tuple[Filing, list[Trade]]:
    preview = session.get(ParserArtifact, preview_artifact_id)
    if not preview:
        raise ValueError(f"Parser artifact not found: {preview_artifact_id}")
    if preview.artifact_type != "preview":
        raise ValueError("Only preview parser artifacts can be promoted.")

    raw_document = session.get(RawDocument, preview.raw_document_id)
    if not raw_document:
        raise ValueError(f"Raw document not found: {preview.raw_document_id}")

    parser_output = preview.parser_output or {}
    transactions = parser_output.get("transactions") or []
    if not transactions:
        raise ValueError("Preview artifact contains no parsed transactions to promote.")

    person = get_or_create_person(
        session,
        full_name=person_name,
        branch=branch,
        chamber=chamber,
        state=state,
        party=party,
        office=office,
        agency=agency,
        court=court,
    )

    filed_date = parse_date(parser_output.get("filing_date"), fallback=raw_document.retrieved_at.date())
    filing = Filing(
        id=uuid4(),
        person_id=person.id,
        filing_type=parser_output.get("report_type") or parser_output.get("document_type") or "disclosure",
        filed_date=filed_date,
        source_url=raw_document.source_url,
        retrieved_at=raw_document.retrieved_at,
        file_hash=raw_document.file_hash,
        retrieval_source=raw_document.retrieval_source,
        raw_document_id=raw_document.id,
    )
    session.add(filing)
    session.flush()

    filing_artifact = ParserArtifact(
        id=uuid4(),
        source_id=preview.source_id,
        raw_document_id=raw_document.id,
        filing_id=filing.id,
        artifact_type="filing",
        text_span={},
        parser_output={
            "reviewed_by": reviewer,
            "promoted_from_artifact_id": str(preview.id),
            "person_name": person_name,
            "branch": branch,
        },
        confidence=preview.confidence,
    )
    session.add(filing_artifact)

    trades = []
    for row in transactions:
        trade_date = parse_date(row.get("transaction_date"), fallback=filed_date)
        min_value, max_value = parse_value_range(row.get("amount") or "")
        trade = Trade(
            id=uuid4(),
            person_id=person.id,
            filing_id=filing.id,
            trade_date=trade_date,
            reported_date=filed_date,
            action=row.get("transaction_type") or "OTHER",
            raw_asset_text=row.get("asset") or "Unknown asset",
            asset_display_name=row.get("asset") or "Unknown asset",
            ticker=row.get("ticker"),
            asset_class="unknown",
            value_range_label=row.get("amount") or "Unknown",
            value_range_min=min_value,
            value_range_max=max_value,
            disclosure_lag_days=disclosure_lag(trade_date, filed_date),
            parsing_confidence=Decimal("0.85"),
            asset_match_confidence=None,
        )
        session.add(trade)
        session.flush()
        trades.append(trade)

        session.add(
            ParserArtifact(
                id=uuid4(),
                source_id=preview.source_id,
                raw_document_id=raw_document.id,
                filing_id=filing.id,
                trade_id=trade.id,
                artifact_type="trade",
                page_number=None,
                row_number=row.get("row_number"),
                text_span={"text": row.get("comment") or row.get("asset") or ""},
                parser_output={
                    "reviewed_by": reviewer,
                    "promoted_from_artifact_id": str(preview.id),
                    "row": row,
                },
                confidence=Decimal("0.85"),
            )
        )

    session.commit()
    session.refresh(filing)
    for trade in trades:
        session.refresh(trade)
    return filing, trades
