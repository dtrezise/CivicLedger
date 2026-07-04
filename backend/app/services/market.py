from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app import crud


async def compute_benchmark_move(
    db: AsyncSession,
    symbol: str,
    start_date: date,
    horizon_days: int,
) -> Optional[dict]:
    """Compute benchmark % move from start_date over horizon_days."""
    end_date = start_date + timedelta(days=horizon_days + 10)  # extra buffer

    points = await crud.get_market_series(
        db, symbols=[symbol], start=start_date - timedelta(days=5), end=end_date
    )

    if not points:
        return None

    # Snap start to next available session
    start_point = None
    for p in points:
        if p.date >= start_date:
            start_point = p
            break

    if not start_point:
        return None

    # Snap end to prior available session
    target_end = start_date + timedelta(days=horizon_days)
    end_point = None
    for p in reversed(points):
        if p.date <= target_end:
            end_point = p
            break

    if not end_point or end_point.date <= start_point.date:
        return None

    start_val = float(start_point.value)
    end_val = float(end_point.value)

    if start_val == 0:
        return None

    pct_change = ((end_val - start_val) / start_val) * 100

    return {
        "symbol": symbol,
        "horizon_days": horizon_days,
        "start_date": str(start_point.date),
        "end_date": str(end_point.date),
        "start_value": start_val,
        "end_value": end_val,
        "pct_change": round(pct_change, 4),
    }
