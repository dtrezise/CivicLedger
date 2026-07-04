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
from uuid import uuid4

from sqlalchemy import text
from app.database import sync_engine, SyncSessionLocal
from app.models import (
    Base, Person, Filing, Trade, Event, EventSource, MarketSeries
)

FIXTURES = Path(__file__).parent / "fixtures"
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
    ]


def create_filings_and_trades(person: Person):
    """Create 3-5 filings and 10-20 trades per person."""
    filings = []
    trades = []

    num_filings = random.randint(3, 5)
    # Spread filings across the time range
    filing_dates = sorted([
        date(2023, 1, 1) + timedelta(days=random.randint(0, 550))
        for _ in range(num_filings)
    ])

    for i, fdate in enumerate(filing_dates):
        filing_id = uuid4()
        source_idx = random.randint(1000, 9999)
        filing = Filing(
            id=filing_id,
            person_id=person.id,
            filing_type="PTR",
            filed_date=fdate,
            source_url=f"https://efds.senate.gov/search/view/ptr/{source_idx}/",
            retrieved_at=datetime(fdate.year, fdate.month, fdate.day, 12, 0, 0),
            file_hash=generate_hash(f"{person.full_name}-{fdate}-{i}"),
            retrieval_source="fixture",
        )
        filings.append(filing)

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

            trades.append(Trade(
                id=uuid4(),
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

    return filings, trades


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


def run_seed():
    print("🌱 Starting seed...")

    with SyncSessionLocal() as session:
        # Check if already seeded
        result = session.execute(text("SELECT COUNT(*) FROM people"))
        count = result.scalar()
        if count > 0:
            print("✅ Database already seeded, skipping.")
            return

        # People
        people = create_people()
        for p in people:
            session.add(p)
        session.flush()
        print(f"  → Created {len(people)} people")

        # Filings + Trades
        total_filings = 0
        total_trades = 0
        for person in people:
            filings, trades = create_filings_and_trades(person)
            for f in filings:
                session.add(f)
            session.flush()
            for t in trades:
                session.add(t)
            total_filings += len(filings)
            total_trades += len(trades)
        session.flush()
        print(f"  → Created {total_filings} filings")
        print(f"  → Created {total_trades} trades")

        # Market series
        market_data = generate_market_series()
        for m in market_data:
            session.add(m)
        session.flush()
        print(f"  → Created {len(market_data)} market data points")

        # Events
        load_events(session)
        print("  → Loaded 10 events")

        session.commit()
        print("✅ Seed complete!")


if __name__ == "__main__":
    run_seed()
