from __future__ import annotations

from bisect import bisect_left
from datetime import date
import math
from typing import Iterable


DEFAULT_WINDOW_SESSIONS = (1, 5, 20)
MARKET_CONTEXT_LABEL = (
    "Descriptive price context only. Windows are anchored to the first common market "
    "date on or after the reported trade date. Date proximity and benchmark-adjusted "
    "arithmetic do not establish causation, intent, knowledge, legality, ethics, market "
    "impact, or investment performance."
)
PRICE_METHOD = "adjusted_close_preferred_else_close"


def _iso_date(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(value[:10]).isoformat()


def _price_value(point: dict) -> tuple[float | None, str | None]:
    if point.get("adj_close") is not None:
        value = point["adj_close"]
        field = "adj_close"
    elif point.get("close") is not None:
        value = point["close"]
        field = "close"
    elif point.get("value") is not None:
        value = point["value"]
        field = point.get("price_field") or "value"
    else:
        return None, None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, None
    if not math.isfinite(number) or number <= 0:
        return None, None
    return number, field


def build_price_index(market_prices: dict) -> dict[str, tuple[dict, ...]]:
    raw_series = market_prices.get("series", market_prices)
    index: dict[str, tuple[dict, ...]] = {}
    for raw_symbol, series in raw_series.items():
        if not isinstance(series, (dict, list, tuple)):
            continue
        symbol = str(raw_symbol).upper()
        points = series.get("points", []) if isinstance(series, dict) else series
        series_source = series.get("source") if isinstance(series, dict) else None
        by_date: dict[str, dict] = {}
        for point in points:
            if not isinstance(point, dict) or not point.get("date"):
                continue
            try:
                point_date = _iso_date(point["date"])
            except (TypeError, ValueError):
                continue
            value, price_field = _price_value(point)
            if value is None:
                continue
            by_date[point_date] = {
                "date": point_date,
                "value": value,
                "price_field": price_field,
                "source": point.get("source") or series_source,
            }
        if by_date:
            index[symbol] = tuple(by_date[key] for key in sorted(by_date))
    return index


def _return_pct(start_value: float, end_value: float) -> float:
    return round(((end_value / start_value) - 1) * 100, 6)


def _window_row(
    direction: str,
    session_count: int,
    asset_start: dict,
    asset_end: dict,
    benchmark_start: dict,
    benchmark_end: dict,
) -> dict:
    asset_return = _return_pct(asset_start["value"], asset_end["value"])
    benchmark_return = _return_pct(benchmark_start["value"], benchmark_end["value"])
    return {
        "direction": direction,
        "session_count": session_count,
        "window_label": f"{direction}_{session_count}_session"
        + ("s" if session_count != 1 else ""),
        "start_date": asset_start["date"],
        "end_date": asset_end["date"],
        "asset_start_value": round(asset_start["value"], 8),
        "asset_end_value": round(asset_end["value"], 8),
        "benchmark_start_value": round(benchmark_start["value"], 8),
        "benchmark_end_value": round(benchmark_end["value"], 8),
        "asset_return_pct": asset_return,
        "benchmark_return_pct": benchmark_return,
        "benchmark_adjusted_return_pct": round(asset_return - benchmark_return, 6),
        "adjustment_method": "asset_return_pct_minus_benchmark_return_pct",
    }


def _normalized_windows(window_sessions: Iterable[int]) -> tuple[int, ...]:
    windows = sorted({int(value) for value in window_sessions if int(value) > 0})
    if not windows:
        raise ValueError("window_sessions must contain at least one positive integer")
    return tuple(windows)


class MarketReactionCalculator:
    def __init__(self, market_prices: dict) -> None:
        self.price_index = build_price_index(market_prices)
        self._aligned_cache: dict[tuple[str, str], tuple[dict, ...]] = {}

    def _aligned_points(self, asset_symbol: str, benchmark_symbol: str) -> tuple[dict, ...]:
        cache_key = (asset_symbol, benchmark_symbol)
        if cache_key in self._aligned_cache:
            return self._aligned_cache[cache_key]

        asset_points = self.price_index.get(asset_symbol, ())
        benchmark_points = self.price_index.get(benchmark_symbol, ())
        asset_by_date = {point["date"]: point for point in asset_points}
        benchmark_by_date = {point["date"]: point for point in benchmark_points}
        common_dates = sorted(asset_by_date.keys() & benchmark_by_date.keys())
        aligned = tuple(
            {
                "date": point_date,
                "asset": asset_by_date[point_date],
                "benchmark": benchmark_by_date[point_date],
            }
            for point_date in common_dates
        )
        self._aligned_cache[cache_key] = aligned
        return aligned

    def compute(
        self,
        asset_symbol: str,
        benchmark_symbol: str,
        event_date: str | date,
        window_sessions: Iterable[int] = DEFAULT_WINDOW_SESSIONS,
    ) -> dict:
        asset_symbol = asset_symbol.upper()
        benchmark_symbol = benchmark_symbol.upper()
        event_date_iso = _iso_date(event_date)
        windows = _normalized_windows(window_sessions)

        base = {
            "asset_symbol": asset_symbol,
            "benchmark_symbol": benchmark_symbol,
            "event_date": event_date_iso,
            "anchor_date": None,
            "window_unit": "common_trading_sessions",
            "price_method": PRICE_METHOD,
            "requested_session_counts": list(windows),
            "pre_windows": [],
            "post_windows": [],
            "context_label": MARKET_CONTEXT_LABEL,
        }
        if asset_symbol not in self.price_index:
            return {**base, "status": "unavailable", "coverage_reason": "missing_asset_series"}
        if benchmark_symbol not in self.price_index:
            return {**base, "status": "unavailable", "coverage_reason": "missing_benchmark_series"}

        aligned = self._aligned_points(asset_symbol, benchmark_symbol)
        if not aligned:
            return {**base, "status": "unavailable", "coverage_reason": "no_common_market_dates"}
        dates = [point["date"] for point in aligned]
        anchor_index = bisect_left(dates, event_date_iso)
        if anchor_index >= len(aligned):
            return {
                **base,
                "status": "unavailable",
                "coverage_reason": "event_after_available_history",
            }

        anchor = aligned[anchor_index]
        pre_windows = []
        post_windows = []
        for session_count in windows:
            if anchor_index >= session_count:
                start = aligned[anchor_index - session_count]
                pre_windows.append(
                    _window_row(
                        "pre",
                        session_count,
                        start["asset"],
                        anchor["asset"],
                        start["benchmark"],
                        anchor["benchmark"],
                    )
                )
            if anchor_index + session_count < len(aligned):
                end = aligned[anchor_index + session_count]
                post_windows.append(
                    _window_row(
                        "post",
                        session_count,
                        anchor["asset"],
                        end["asset"],
                        anchor["benchmark"],
                        end["benchmark"],
                    )
                )

        available_count = len(pre_windows) + len(post_windows)
        requested_count = len(windows) * 2
        if not available_count:
            status = "unavailable"
            coverage_reason = "insufficient_window_history"
        elif available_count == requested_count:
            status = "covered"
            coverage_reason = "complete_requested_windows"
        else:
            status = "partial"
            coverage_reason = "some_requested_windows_unavailable"

        return {
            **base,
            "status": status,
            "coverage_reason": coverage_reason,
            "anchor_date": anchor["date"],
            "pre_windows": pre_windows,
            "post_windows": post_windows,
        }


def compute_market_reaction(
    market_prices: dict,
    asset_symbol: str,
    benchmark_symbol: str,
    event_date: str | date,
    window_sessions: Iterable[int] = DEFAULT_WINDOW_SESSIONS,
) -> dict:
    return MarketReactionCalculator(market_prices).compute(
        asset_symbol,
        benchmark_symbol,
        event_date,
        window_sessions,
    )


def compute_pre_post_windows(
    market_prices: dict,
    asset_symbol: str,
    benchmark_symbol: str,
    event_date: str | date,
    window_sessions: Iterable[int] = DEFAULT_WINDOW_SESSIONS,
) -> dict:
    return compute_market_reaction(
        market_prices,
        asset_symbol,
        benchmark_symbol,
        event_date,
        window_sessions,
    )
