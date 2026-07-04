from uuid import UUID
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models import Trade, Filing
from app.schemas import ScorecardDeduction, ScorecardMetrics, ScorecardResponse


async def compute_scorecard(db: AsyncSession, person_id: UUID) -> ScorecardResponse:
    """Compute scorecard per CivicLedger canvas rules."""

    # Get all trades for this person
    trades_result = await db.execute(
        select(Trade).where(Trade.person_id == person_id).order_by(Trade.trade_date)
    )
    trades = trades_result.scalars().all()

    # Get filings
    filings_result = await db.execute(
        select(Filing).where(Filing.person_id == person_id)
    )
    filings = filings_result.scalars().all()

    notes = []
    deductions = []
    trade_count = len(trades)

    # Transaction level reporting
    if trade_count > 0:
        transaction_level = "Yes"
    else:
        transaction_level = "No"
        notes.append("No trades on record.")

    # Median lag (last 24 months or all if < 10 trades)
    cutoff = date.today() - timedelta(days=730)  # ~24 months
    recent_trades = [t for t in trades if t.trade_date >= cutoff]
    if len(recent_trades) < 10:
        recent_trades = list(trades)

    lags = sorted([t.disclosure_lag_days for t in recent_trades])
    median_lag = None
    if lags:
        mid = len(lags) // 2
        if len(lags) % 2:
            median_lag = float(lags[mid])
        else:
            median_lag = float((lags[mid - 1] + lags[mid]) / 2)

    # Completeness rating (start at 100, deductions)
    completeness = 100

    # Deduction: no filings
    if not filings:
        completeness -= 30
        notes.append("No filings found.")
        deductions.append(ScorecardDeduction(
            rule_id="missing_filings",
            points=30,
            explanation="No filing records found for this person.",
            evidence_count=0,
        ))

    # Deduction: high median lag
    if median_lag is not None:
        if median_lag > 90:
            completeness -= 25
            notes.append(f"High median disclosure lag: {median_lag:.0f} days.")
            deductions.append(ScorecardDeduction(
                rule_id="median_lag_over_90_days",
                points=25,
                explanation=f"Median disclosure lag is {median_lag:.0f} days.",
                evidence_count=len(lags),
            ))
        elif median_lag > 45:
            completeness -= 15
            notes.append(f"Elevated median disclosure lag: {median_lag:.0f} days.")
            deductions.append(ScorecardDeduction(
                rule_id="median_lag_over_45_days",
                points=15,
                explanation=f"Median disclosure lag is {median_lag:.0f} days.",
                evidence_count=len(lags),
            ))

    # Deduction: negative lag (flags)
    neg_lag_trades = [t for t in trades if t.disclosure_lag_days < 0]
    if neg_lag_trades:
        completeness -= 10
        notes.append(f"{len(neg_lag_trades)} trade(s) with negative disclosure lag (data quality flag).")
        deductions.append(ScorecardDeduction(
            rule_id="negative_disclosure_lag",
            points=10,
            explanation="One or more trades have a reported date before the trade date.",
            evidence_count=len(neg_lag_trades),
        ))

    # Deduction: low parsing confidence
    low_conf = [t for t in trades if t.parsing_confidence is not None and float(t.parsing_confidence) < 0.5]
    if low_conf:
        completeness -= 10
        notes.append(f"{len(low_conf)} trade(s) with low parsing confidence.")
        deductions.append(ScorecardDeduction(
            rule_id="low_parser_confidence",
            points=10,
            explanation="One or more trades have parser confidence below 0.5.",
            evidence_count=len(low_conf),
        ))

    completeness = max(0, min(100, completeness))

    # Grade mapping
    if completeness >= 90:
        grade = "A"
    elif completeness >= 80:
        grade = "B"
    elif completeness >= 70:
        grade = "C"
    elif completeness >= 60:
        grade = "D"
    else:
        grade = "F"

    if not notes:
        notes.append("No data-quality notes triggered.")

    return ScorecardResponse(
        transaction_level_reporting=transaction_level,
        typical_reporting_lag_days=median_lag,
        disclosure_type="transactions",
        completeness_rating=completeness,
        grade=grade,
        notes=notes,
        metrics=ScorecardMetrics(
            trade_count=trade_count,
            filing_count=len(filings),
            median_lag_days=median_lag,
            negative_lag_count=len(neg_lag_trades),
            low_parser_confidence_count=len(low_conf),
        ),
        deductions=deductions,
    )
