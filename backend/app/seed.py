"""
Seed script: populates the database with fixture data on first run.
Run with: python -m app.seed
"""
import json
import hashlib
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import text
from app.config import settings
from app.database import sync_engine, SyncSessionLocal
from app.models import (
    Base,
    Person,
    IngestionRun,
    RawDocument,
    Filing,
    Trade,
    Event,
    EventSource,
    MarketSeries,
    ParserArtifact,
    PublicOfficialRole,
)

FIXTURES = Path(__file__).parent / "fixtures"
PUBLIC_OFFICIALS_DATA = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "public_officials"
    / "public_official_roles.json"
)
SEED_NAMESPACE = UUID("45e23791-3a49-4487-a6f3-739f7f9290b6")
random.seed(42)


def generate_market_series():
    """Generate synthetic but realistic daily market data for SPY and DIA."""
    series = []
    start = date(2023, 1, 3)
    end = date(2024, 8, 30)

    spy_price = 382.0
    dia_price = 332.0

    current = start
    while current <= end:
        # Skip weekends
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        # Random daily moves
        spy_change = random.gauss(0.0004, 0.012)
        dia_change = random.gauss(0.0003, 0.010)

        spy_price *= (1 + spy_change)
        dia_price *= (1 + dia_change)

        series.append(MarketSeries(
            id=uuid4(), symbol="SPY", freq="d",
            date=current, value=round(Decimal(str(spy_price)), 2)
        ))
        series.append(MarketSeries(
            id=uuid4(), symbol="DIA", freq="d",
            date=current, value=round(Decimal(str(dia_price)), 2)
        ))

        current += timedelta(days=1)

    return series


def generate_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


TICKERS = [
    ("AAPL", "Apple Inc.", "equity"),
    ("MSFT", "Microsoft Corp.", "equity"),
    ("GOOGL", "Alphabet Inc.", "equity"),
    ("AMZN", "Amazon.com Inc.", "equity"),
    ("NVDA", "NVIDIA Corp.", "equity"),
    ("META", "Meta Platforms Inc.", "equity"),
    ("TSLA", "Tesla Inc.", "equity"),
    ("JPM", "JPMorgan Chase & Co.", "equity"),
    ("V", "Visa Inc.", "equity"),
    ("JNJ", "Johnson & Johnson", "equity"),
    ("SPY", "SPDR S&P 500 ETF", "etf"),
    ("QQQ", "Invesco QQQ Trust", "etf"),
    ("IWM", "iShares Russell 2000 ETF", "etf"),
    ("BND", "Vanguard Total Bond Market ETF", "bond"),
    ("VFIAX", "Vanguard 500 Index Fund", "mutual_fund"),
]

VALUE_RANGES = [
    ("$1,001 - $15,000", 1001, 15000),
    ("$15,001 - $50,000", 15001, 50000),
    ("$50,001 - $100,000", 50001, 100000),
    ("$100,001 - $250,000", 100001, 250000),
    ("$250,001 - $500,000", 250001, 500000),
    ("$500,001 - $1,000,000", 500001, 1000000),
]


def create_people():
    return [
        Person(
            id=uuid4(),
            full_name="Sen. Maria Chen",
            branch="Legislative",
            chamber="Senate",
            state="CA",
            party="Democrat",
            district=None,
            service_start=date(2019, 1, 3),
            service_end=None,
        ),
        Person(
            id=uuid4(),
            full_name="Sen. Robert J. Hargrove",
            branch="Legislative",
            chamber="Senate",
            state="TX",
            party="Republican",
            district=None,
            service_start=date(2015, 1, 6),
            service_end=None,
        ),
        Person(
            id=uuid4(),
            full_name="Rep. Diana Torres-Williams",
            branch="Legislative",
            chamber="House",
            state="FL",
            party="Democrat",
            district="FL-22",
            service_start=date(2021, 1, 3),
            service_end=None,
        ),
        Person(
            id=uuid4(),
            full_name="Secretary Elaine Park",
            branch="Executive",
            chamber=None,
            state=None,
            party=None,
            district=None,
            office="Secretary",
            agency="Department of Energy",
            court=None,
            service_start=date(2022, 2, 14),
            service_end=None,
        ),
        Person(
            id=uuid4(),
            full_name="Deputy Administrator Thomas Reed",
            branch="Executive",
            chamber=None,
            state=None,
            party=None,
            district=None,
            office="Deputy Administrator",
            agency="Environmental Protection Agency",
            court=None,
            service_start=date(2021, 8, 2),
            service_end=None,
        ),
        Person(
            id=uuid4(),
            full_name="Judge Amelia Ortiz",
            branch="Judicial",
            chamber=None,
            state=None,
            party=None,
            district=None,
            office="Circuit Judge",
            agency=None,
            court="U.S. Court of Appeals for the Ninth Circuit",
            service_start=date(2020, 6, 1),
            service_end=None,
        ),
        Person(
            id=uuid4(),
            full_name="Judge Malcolm Price",
            branch="Judicial",
            chamber=None,
            state=None,
            party=None,
            district=None,
            office="District Judge",
            agency=None,
            court="U.S. District Court for the District of Maryland",
            service_start=date(2018, 11, 15),
            service_end=None,
        ),
    ]


def source_id_for_person(person: Person) -> str:
    if person.branch == "Executive":
        return "oge-individual-disclosures"
    if person.branch == "Judicial":
        return "judicial-financial-disclosure"
    if person.chamber == "Senate":
        return "senate-public-financial-disclosure"
    return "house-financial-disclosure"


def filing_type_for_person(person: Person) -> str:
    if person.branch == "Executive":
        return random.choice(["OGE278e", "OGE278T"])
    if person.branch == "Judicial":
        return random.choice(["JFD", "JPTR"])
    return "PTR"


def create_filings_and_trades(person: Person, ingestion_run_id):
    """Create 3-5 filings and 10-20 trades per person."""
    raw_documents = []
    filings = []
    trades = []
    artifacts = []
    source_id = source_id_for_person(person)

    num_filings = random.randint(3, 5)
    # Spread filings across the time range
    filing_dates = sorted([
        date(2023, 1, 1) + timedelta(days=random.randint(0, 550))
        for _ in range(num_filings)
    ])

    for i, fdate in enumerate(filing_dates):
        filing_id = uuid4()
        raw_document_id = uuid4()
        source_idx = random.randint(1000, 9999)
        source_url = f"https://example.test/fixture/{source_id}/{source_idx}/"
        retrieved_at = datetime(fdate.year, fdate.month, fdate.day, 12, 0, 0)
        file_hash = generate_hash(f"{person.full_name}-{fdate}-{i}")
        raw_documents.append(RawDocument(
            id=raw_document_id,
            ingestion_run_id=ingestion_run_id,
            source_url=source_url,
            retrieved_at=retrieved_at,
            retrieval_source="fixture",
            content_type="application/pdf",
            file_hash=file_hash,
            storage_uri=f"fixture://raw_filings/{raw_document_id}.pdf",
            rights_status="public_record_fixture",
            parser_version=settings.PARSER_VERSION,
            provenance_complete=True,
            source_metadata={
                "source_id": source_id,
                "branch": person.branch,
                "fixture": True,
            },
        ))
        filing = Filing(
            id=filing_id,
            person_id=person.id,
            filing_type=filing_type_for_person(person),
            filed_date=fdate,
            source_url=source_url,
            retrieved_at=retrieved_at,
            file_hash=file_hash,
            retrieval_source="fixture",
            raw_document_id=raw_document_id,
        )
        filings.append(filing)
        artifacts.append(ParserArtifact(
            id=uuid4(),
            source_id=source_id,
            raw_document_id=raw_document_id,
            filing_id=filing_id,
            artifact_type="filing",
            page_number=1,
            row_number=None,
            text_span={
                "label": "Fixture filing header",
                "text": f"{person.full_name} {person.branch} disclosure filed {fdate}",
            },
            parser_output={
                "filing_type": filing.filing_type,
                "filed_date": fdate.isoformat(),
                "retrieval_source": "fixture",
            },
            confidence=Decimal("0.98"),
        ))

        # 3-6 trades per filing
        num_trades = random.randint(3, 6)
        for j in range(num_trades):
            # Trade date is before filing date
            lag = random.randint(15, 90)
            trade_date = fdate - timedelta(days=lag)
            if trade_date < date(2023, 1, 1):
                trade_date = date(2023, 1, 1) + timedelta(days=random.randint(0, 30))
                lag = (fdate - trade_date).days

            ticker_info = random.choice(TICKERS)
            vrange = random.choice(VALUE_RANGES)
            action = random.choice(["BUY", "BUY", "SELL", "BUY", "SELL"])

            trade_id = uuid4()
            trades.append(Trade(
                id=trade_id,
                person_id=person.id,
                filing_id=filing_id,
                trade_date=trade_date,
                reported_date=fdate,
                action=action,
                raw_asset_text=f"{ticker_info[1]} ({ticker_info[0]})",
                asset_display_name=ticker_info[1],
                ticker=ticker_info[0],
                asset_class=ticker_info[2],
                value_range_label=vrange[0],
                value_range_min=Decimal(str(vrange[1])),
                value_range_max=Decimal(str(vrange[2])),
                disclosure_lag_days=lag,
                parsing_confidence=round(Decimal(str(random.uniform(0.85, 1.0))), 2),
                asset_match_confidence=round(Decimal(str(random.uniform(0.90, 1.0))), 2),
            ))
            artifacts.append(ParserArtifact(
                id=uuid4(),
                source_id=source_id,
                raw_document_id=raw_document_id,
                filing_id=filing_id,
                trade_id=trade_id,
                artifact_type="trade",
                page_number=1,
                row_number=j + 1,
                text_span={
                    "label": "Fixture transaction row",
                    "text": f"{action} {ticker_info[1]} {vrange[0]} reported {fdate}",
                },
                parser_output={
                    "trade_date": trade_date.isoformat(),
                    "reported_date": fdate.isoformat(),
                    "action": action,
                    "asset": ticker_info[1],
                    "ticker": ticker_info[0],
                    "value_range_label": vrange[0],
                },
                confidence=Decimal("0.94"),
            ))

    return raw_documents, filings, trades, artifacts


def load_events(session):
    events_file = FIXTURES / "events" / "events.json"
    with open(events_file) as f:
        events_data = json.load(f)

    for ed in events_data:
        event = Event(
            id=uuid4(),
            date=date.fromisoformat(ed["date"]),
            label=ed["label"],
            event_type=ed["event_type"],
            description=ed.get("description"),
        )
        session.add(event)
        session.flush()

        for url in ed.get("sources", []):
            session.add(EventSource(
                id=uuid4(),
                event_id=event.id,
                url=url,
            ))


def parse_optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def stable_seed_uuid(value: str):
    return uuid5(SEED_NAMESPACE, value)


def load_public_official_roles(session):
    if not PUBLIC_OFFICIALS_DATA.exists():
        print("  → Public officials dataset missing, skipping official roles")
        return 0

    data = json.loads(PUBLIC_OFFICIALS_DATA.read_text())
    role_rows = data.get("roles", [])
    person_rows = {}
    for role in role_rows:
        person = person_rows.setdefault(
            role["external_person_id"],
            {
                "external_person_id": role["external_person_id"],
                "full_name": role["full_name"],
                "branch": role["branch"],
                "roles": [],
            },
        )
        person["roles"].append(role)

    person_id_by_external_id = {}
    for external_person_id, person_row in person_rows.items():
        person_id = stable_seed_uuid(f"public-official-person:{external_person_id}")
        role_dates = [
            parse_optional_date(role.get("service_start"))
            for role in person_row["roles"]
            if role.get("service_start")
        ]
        first_role = sorted(
            person_row["roles"],
            key=lambda role: (
                role.get("service_start") or "9999-12-31",
                role.get("role_title") or "",
            ),
        )[0]
        if session.get(Person, person_id) is None:
            session.add(
                Person(
                    id=person_id,
                    full_name=person_row["full_name"],
                    branch=person_row["branch"],
                    chamber=None,
                    state=None,
                    party=None,
                    district=None,
                    office=first_role.get("office"),
                    agency=first_role.get("agency"),
                    court=first_role.get("court"),
                    service_start=min(role_dates) if role_dates else date(2017, 1, 20),
                    service_end=None,
                )
            )
        person_id_by_external_id[external_person_id] = person_id

    session.flush()

    created_roles = 0
    for role in role_rows:
        role_id = stable_seed_uuid(f"public-official-role:{role['external_role_id']}")
        if session.get(PublicOfficialRole, role_id) is not None:
            continue
        session.add(
            PublicOfficialRole(
                id=role_id,
                person_id=person_id_by_external_id[role["external_person_id"]],
                external_role_id=role["external_role_id"],
                external_person_id=role["external_person_id"],
                branch=role["branch"],
                presidential_term=role["presidential_term"],
                administration=role["administration"],
                role_category=role["role_category"],
                role_title=role["role_title"],
                office=role.get("office"),
                agency=role.get("agency"),
                court=role.get("court"),
                service_start=parse_optional_date(role.get("service_start")),
                service_end=parse_optional_date(role.get("service_end")),
                appointing_president=role.get("appointing_president"),
                source_id=role["source_id"],
                source_name=role["source_name"],
                source_url=role["source_url"],
                source_tier=role["source_tier"],
                source_retrieved_at=parse_optional_date(role.get("source_retrieved_at")),
                source_metadata=role.get("source_metadata") or {},
            )
        )
        created_roles += 1

    session.flush()
    print(f"  → Loaded {len(person_rows)} public official people")
    print(f"  → Loaded {created_roles} public official roles")
    return created_roles


def run_seed():
    print("🌱 Starting seed...")

    with SyncSessionLocal() as session:
        # Check if already seeded
        result = session.execute(text("SELECT COUNT(*) FROM people"))
        count = result.scalar()
        if count > 0:
            role_count = session.execute(text("SELECT COUNT(*) FROM public_official_roles")).scalar()
            if role_count == 0:
                load_public_official_roles(session)
                session.commit()
            print("✅ Database already seeded, skipping fixture reload.")
            return

        # People
        ingestion_run = IngestionRun(
            id=uuid4(),
            source_name="fixture-seed",
            source_url="fixture://seed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            status="completed",
            dataset_version=settings.DATASET_VERSION,
            parser_version=settings.PARSER_VERSION,
            notes="Synthetic fixture data for local development and portfolio demonstration.",
        )
        session.add(ingestion_run)
        session.flush()

        people = create_people()
        for p in people:
            session.add(p)
        session.flush()
        print(f"  → Created {len(people)} people")

        # Filings + Trades
        total_raw_documents = 0
        total_filings = 0
        total_trades = 0
        total_artifacts = 0
        for person in people:
            raw_documents, filings, trades, artifacts = create_filings_and_trades(person, ingestion_run.id)
            for raw_document in raw_documents:
                session.add(raw_document)
            session.flush()
            for f in filings:
                session.add(f)
            session.flush()
            for t in trades:
                session.add(t)
            session.flush()
            for artifact in artifacts:
                session.add(artifact)
            total_raw_documents += len(raw_documents)
            total_filings += len(filings)
            total_trades += len(trades)
            total_artifacts += len(artifacts)
        session.flush()
        print(f"  → Created {total_raw_documents} raw documents")
        print(f"  → Created {total_filings} filings")
        print(f"  → Created {total_trades} trades")
        print(f"  → Created {total_artifacts} parser artifacts")

        # Market series
        market_data = generate_market_series()
        for m in market_data:
            session.add(m)
        session.flush()
        print(f"  → Created {len(market_data)} market data points")

        # Events
        load_events(session)
        print("  → Loaded 10 events")

        # Public officials
        load_public_official_roles(session)

        session.commit()
        print("✅ Seed complete!")


if __name__ == "__main__":
    run_seed()
