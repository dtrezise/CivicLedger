from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import math
from pathlib import PurePosixPath
import re
from typing import Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings


TIINGO_BASE_URL = "https://api.tiingo.com/tiingo/daily"
TIINGO_CRYPTO_BASE_URL = "https://api.tiingo.com/tiingo/crypto"
NASDAQ_BASE_URL = "https://api.nasdaq.com/api/quote"
USER_AGENT = "CivicLedger data refresh"
_MARKET_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,14}$")

TICKER_REFERENCE = {
    "AAPL": {
        "issuer_name": "Apple Inc.",
        "asset_class": "equity",
        "sector": "Information Technology",
        "benchmark_symbol": "XLK",
    },
    "MSFT": {
        "issuer_name": "Microsoft Corp.",
        "asset_class": "equity",
        "sector": "Information Technology",
        "benchmark_symbol": "XLK",
    },
    "GOOGL": {
        "issuer_name": "Alphabet Inc.",
        "asset_class": "equity",
        "sector": "Communication Services",
        "benchmark_symbol": "QQQ",
    },
    "AMZN": {
        "issuer_name": "Amazon.com Inc.",
        "asset_class": "equity",
        "sector": "Consumer Discretionary",
        "benchmark_symbol": "QQQ",
    },
    "NVDA": {
        "issuer_name": "NVIDIA Corp.",
        "asset_class": "equity",
        "sector": "Information Technology",
        "benchmark_symbol": "XLK",
    },
    "META": {
        "issuer_name": "Meta Platforms Inc.",
        "asset_class": "equity",
        "sector": "Communication Services",
        "benchmark_symbol": "QQQ",
    },
    "TSLA": {
        "issuer_name": "Tesla Inc.",
        "asset_class": "equity",
        "sector": "Consumer Discretionary",
        "benchmark_symbol": "QQQ",
    },
    "JPM": {
        "issuer_name": "JPMorgan Chase & Co.",
        "asset_class": "equity",
        "sector": "Financials",
        "benchmark_symbol": "XLF",
    },
    "V": {
        "issuer_name": "Visa Inc.",
        "asset_class": "equity",
        "sector": "Financials",
        "benchmark_symbol": "XLF",
    },
    "JNJ": {
        "issuer_name": "Johnson & Johnson",
        "asset_class": "equity",
        "sector": "Health Care",
        "benchmark_symbol": "XLV",
    },
    "SPY": {
        "issuer_name": "SPDR S&P 500 ETF Trust",
        "asset_class": "etf",
        "sector": "Broad Market",
        "benchmark_symbol": "SPY",
    },
    "QQQ": {
        "issuer_name": "Invesco QQQ Trust",
        "asset_class": "etf",
        "sector": "Large Cap Growth",
        "benchmark_symbol": "QQQ",
    },
    "IWM": {
        "issuer_name": "iShares Russell 2000 ETF",
        "asset_class": "etf",
        "sector": "Small Cap",
        "benchmark_symbol": "IWM",
    },
    "BND": {
        "issuer_name": "Vanguard Total Bond Market ETF",
        "asset_class": "bond",
        "sector": "Fixed Income",
        "benchmark_symbol": "BND",
    },
    "VFIAX": {
        "issuer_name": "Vanguard 500 Index Fund Admiral Shares",
        "asset_class": "mutual_fund",
        "sector": "Broad Market",
        "benchmark_symbol": "SPY",
    },
    "DIA": {
        "issuer_name": "SPDR Dow Jones Industrial Average ETF Trust",
        "asset_class": "etf",
        "sector": "Blue Chip",
        "benchmark_symbol": "DIA",
    },
    "XLK": {
        "issuer_name": "Technology Select Sector SPDR Fund",
        "asset_class": "etf",
        "sector": "Information Technology",
        "benchmark_symbol": "XLK",
    },
    "XLF": {
        "issuer_name": "Financial Select Sector SPDR Fund",
        "asset_class": "etf",
        "sector": "Financials",
        "benchmark_symbol": "XLF",
    },
    "XLE": {
        "issuer_name": "Energy Select Sector SPDR Fund",
        "asset_class": "etf",
        "sector": "Energy",
        "benchmark_symbol": "XLE",
    },
    "XLV": {
        "issuer_name": "Health Care Select Sector SPDR Fund",
        "asset_class": "etf",
        "sector": "Health Care",
        "benchmark_symbol": "XLV",
    },
    "XLI": {
        "issuer_name": "Industrial Select Sector SPDR Fund",
        "asset_class": "etf",
        "sector": "Industrials",
        "benchmark_symbol": "XLI",
    },
}

MARKET_PRICE_SYMBOLS = list(TICKER_REFERENCE)

CRYPTO_REFERENCE = {
    "BTCUSD": {
        "issuer_name": "Bitcoin / U.S. Dollar",
        "asset_class": "crypto",
        "sector": "Crypto",
        "base_currency": "btc",
        "quote_currency": "usd",
        "benchmark_symbol": "BTCUSD",
    },
    "ETHUSD": {
        "issuer_name": "Ethereum / U.S. Dollar",
        "asset_class": "crypto",
        "sector": "Crypto",
        "base_currency": "eth",
        "quote_currency": "usd",
        "benchmark_symbol": "ETHUSD",
    },
    "SOLUSD": {
        "issuer_name": "Solana / U.S. Dollar",
        "asset_class": "crypto",
        "sector": "Crypto",
        "base_currency": "sol",
        "quote_currency": "usd",
        "benchmark_symbol": "BTCUSD",
    },
    "XRPUSD": {
        "issuer_name": "XRP / U.S. Dollar",
        "asset_class": "crypto",
        "sector": "Crypto",
        "base_currency": "xrp",
        "quote_currency": "usd",
        "benchmark_symbol": "BTCUSD",
    },
    "ADAUSD": {
        "issuer_name": "Cardano / U.S. Dollar",
        "asset_class": "crypto",
        "sector": "Crypto",
        "base_currency": "ada",
        "quote_currency": "usd",
        "benchmark_symbol": "BTCUSD",
    },
    "DOGEUSD": {
        "issuer_name": "Dogecoin / U.S. Dollar",
        "asset_class": "crypto",
        "sector": "Crypto",
        "base_currency": "doge",
        "quote_currency": "usd",
        "benchmark_symbol": "BTCUSD",
    },
    "USDCUSD": {
        "issuer_name": "USD Coin / U.S. Dollar",
        "asset_class": "crypto",
        "sector": "Crypto",
        "base_currency": "usdc",
        "quote_currency": "usd",
        "benchmark_symbol": "BTCUSD",
    },
}

CRYPTO_PRICE_SYMBOLS = list(CRYPTO_REFERENCE)


@dataclass(frozen=True)
class TickerHistoryMapping:
    """A date-bounded disclosed-symbol to price-series mapping."""

    disclosed_symbol: str
    market_symbol: str
    valid_from: str | None
    valid_to: str | None
    issuer_name: str
    change_type: str
    provenance: str

    def as_dict(self) -> dict:
        return asdict(self)


# Keep this table small and explicit. A current-symbol price series can include the
# issuer's pre-change history, but only within the source-checked effective range.
TICKER_HISTORY = (
    TickerHistoryMapping(
        disclosed_symbol="FB",
        market_symbol="META",
        valid_from="2012-05-18",
        valid_to="2022-06-08",
        issuer_name="Meta Platforms Inc.",
        change_type="ticker_change",
        provenance="issuer_ticker_history",
    ),
    TickerHistoryMapping(
        disclosed_symbol="META",
        market_symbol="META",
        valid_from="2022-06-09",
        valid_to=None,
        issuer_name="Meta Platforms Inc.",
        change_type="current_symbol",
        provenance="issuer_ticker_history",
    ),
)


def _date_or_none(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def validate_ticker_history(
    mappings: Iterable[TickerHistoryMapping] = TICKER_HISTORY,
) -> tuple[TickerHistoryMapping, ...]:
    """Validate and deterministically order non-overlapping ticker ranges."""

    ordered = tuple(
        sorted(
            mappings,
            key=lambda row: (
                row.disclosed_symbol.upper(),
                row.valid_from or "",
                row.valid_to or "9999-12-31",
                row.market_symbol.upper(),
            ),
        )
    )
    prior_by_symbol: dict[str, tuple[date | None, date | None]] = {}
    for row in ordered:
        disclosed = row.disclosed_symbol.upper()
        market = row.market_symbol.upper()
        if not _MARKET_SYMBOL_RE.fullmatch(disclosed) or not _MARKET_SYMBOL_RE.fullmatch(market):
            raise ValueError(f"Invalid ticker-history symbol: {disclosed}->{market}")
        start = _date_or_none(row.valid_from)
        end = _date_or_none(row.valid_to)
        if start and end and start > end:
            raise ValueError(f"Ticker-history range starts after it ends: {disclosed}")
        previous = prior_by_symbol.get(disclosed)
        if previous:
            previous_end = previous[1]
            if previous_end is None or start is None or start <= previous_end:
                raise ValueError(f"Overlapping ticker-history ranges for {disclosed}")
        prior_by_symbol[disclosed] = (start, end)
    return ordered


def resolve_ticker_history(
    symbol: str | None,
    effective_date: str | date | None,
    mappings: Iterable[TickerHistoryMapping] = TICKER_HISTORY,
) -> dict:
    """Resolve a disclosed ticker as of a date without guessing outside known ranges."""

    disclosed = str(symbol or "").strip().upper()
    if not _MARKET_SYMBOL_RE.fullmatch(disclosed):
        return {
            "status": "invalid_symbol",
            "disclosed_symbol": disclosed or None,
            "market_symbol": None,
            "effective_date": None,
            "mapping": None,
        }
    if effective_date is None:
        return {
            "status": "missing_effective_date",
            "disclosed_symbol": disclosed,
            "market_symbol": None,
            "effective_date": None,
            "mapping": None,
        }
    on_date = _date_or_none(effective_date)
    assert on_date is not None
    history = [row for row in validate_ticker_history(mappings) if row.disclosed_symbol.upper() == disclosed]
    if not history:
        return {
            "status": "passthrough_no_history",
            "disclosed_symbol": disclosed,
            "market_symbol": disclosed,
            "effective_date": on_date.isoformat(),
            "mapping": None,
        }
    matches = [
        row
        for row in history
        if (_date_or_none(row.valid_from) is None or _date_or_none(row.valid_from) <= on_date)
        and (_date_or_none(row.valid_to) is None or on_date <= _date_or_none(row.valid_to))
    ]
    if len(matches) != 1:
        return {
            "status": "outside_effective_range" if not matches else "ambiguous_effective_range",
            "disclosed_symbol": disclosed,
            "market_symbol": None,
            "effective_date": on_date.isoformat(),
            "mapping": None,
            "known_ranges": [row.as_dict() for row in history],
        }
    mapping = matches[0]
    return {
        "status": "date_bounded_mapping",
        "disclosed_symbol": disclosed,
        "market_symbol": mapping.market_symbol.upper(),
        "effective_date": on_date.isoformat(),
        "mapping": mapping.as_dict(),
    }


def symbol_year_partition_key(symbol: str, year: int | str) -> str:
    normalized = str(symbol).strip().upper()
    year_number = int(year)
    if not _MARKET_SYMBOL_RE.fullmatch(normalized):
        raise ValueError(f"Invalid market symbol: {symbol}")
    if year_number < 1900 or year_number > 9999:
        raise ValueError(f"Invalid market-price partition year: {year}")
    return f"{normalized}:{year_number}"


def symbol_year_partition_path(symbol: str, year: int | str) -> str:
    key = symbol_year_partition_key(symbol, year)
    normalized, normalized_year = key.split(":", 1)
    return PurePosixPath("symbols", normalized, f"{normalized_year}.json").as_posix()


def partition_price_points_by_symbol_year(
    series: Mapping[str, dict | list | tuple],
) -> dict[str, tuple[dict, ...]]:
    """Create deterministic symbol/year partitions without writing files."""

    grouped: dict[str, list[dict]] = {}
    for raw_symbol, raw_series in sorted(series.items()):
        symbol = str(raw_symbol).upper()
        points = raw_series.get("points", []) if isinstance(raw_series, dict) else raw_series
        for point in points:
            if not isinstance(point, dict) or not point.get("date"):
                continue
            point_date = _date_or_none(point["date"])
            if point_date is None:
                continue
            grouped.setdefault(symbol_year_partition_key(symbol, point_date.year), []).append(dict(point))
    return {
        key: tuple(sorted(points, key=lambda row: (str(row.get("date")), json.dumps(row, sort_keys=True))))
        for key, points in sorted(grouped.items())
    }


def diagnose_price_series(
    symbol: str,
    points: Iterable[dict],
    *,
    as_of: str | date,
    stale_after_days: int = 7,
    extreme_move_pct: float = 35.0,
) -> dict:
    """Report corporate actions, stale coverage, duplicates, and suspicious moves."""

    rows = [dict(point) for point in points if isinstance(point, dict) and point.get("date")]
    parsed_rows = []
    invalid_date_count = 0
    for position, row in enumerate(rows):
        try:
            point_date = _date_or_none(row["date"])
        except (TypeError, ValueError):
            invalid_date_count += 1
            continue
        assert point_date is not None
        parsed_rows.append((position, point_date, row))
    sorted_rows = sorted(parsed_rows, key=lambda item: (item[1], item[0]))
    dates = [item[1] for item in sorted_rows]
    duplicate_date_count = len(dates) - len(set(dates))
    out_of_order_count = sum(
        1 for prior, current in zip(parsed_rows, parsed_rows[1:]) if current[1] < prior[1]
    )
    corporate_actions = []
    extreme_moves = []
    prior_value = None
    prior_date = None
    for _, point_date, row in sorted_rows:
        split_factor = row.get("split_factor")
        dividend = row.get("div_cash")
        try:
            has_dividend = dividend is not None and float(dividend) != 0
        except (TypeError, ValueError):
            has_dividend = False
        if split_factor not in {None, 1, 1.0} or has_dividend:
            corporate_actions.append(
                {
                    "date": point_date.isoformat(),
                    "split_factor": split_factor,
                    "div_cash": dividend,
                    "source": row.get("source"),
                }
            )
        raw_value = row.get("adj_close") if row.get("adj_close") is not None else row.get("close")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = None
        if value is not None and math.isfinite(value) and value > 0:
            if prior_value:
                pct_change = ((value / prior_value) - 1) * 100
                if abs(pct_change) >= extreme_move_pct:
                    extreme_moves.append(
                        {
                            "date": point_date.isoformat(),
                            "previous_date": prior_date.isoformat(),
                            "pct_change": round(pct_change, 6),
                        }
                    )
            prior_value = value
            prior_date = point_date
    as_of_date = _date_or_none(as_of)
    assert as_of_date is not None
    last_date = max(dates) if dates else None
    stale_days = (as_of_date - last_date).days if last_date and as_of_date >= last_date else None
    stale = last_date is None or (stale_days is not None and stale_days > stale_after_days)
    diagnostic_codes = []
    if stale:
        diagnostic_codes.append("stale_or_missing_series")
    if duplicate_date_count:
        diagnostic_codes.append("duplicate_market_dates")
    if out_of_order_count:
        diagnostic_codes.append("source_points_out_of_order")
    if invalid_date_count:
        diagnostic_codes.append("invalid_market_dates")
    if corporate_actions:
        diagnostic_codes.append("corporate_actions_present")
    if extreme_moves:
        diagnostic_codes.append("extreme_price_moves_present")
    return {
        "symbol": str(symbol).upper(),
        "point_count": len(parsed_rows),
        "first_date": min(dates).isoformat() if dates else None,
        "last_date": last_date.isoformat() if last_date else None,
        "as_of": as_of_date.isoformat(),
        "stale_after_days": stale_after_days,
        "stale_days": stale_days,
        "is_stale": stale,
        "duplicate_date_count": duplicate_date_count,
        "out_of_order_count": out_of_order_count,
        "invalid_date_count": invalid_date_count,
        "corporate_action_count": len(corporate_actions),
        "corporate_actions": corporate_actions,
        "extreme_move_count": len(extreme_moves),
        "extreme_moves": extreme_moves,
        "diagnostic_codes": diagnostic_codes,
    }


def ticker_reference(symbol: str | None) -> dict | None:
    if not symbol:
        return None
    reference = TICKER_REFERENCE.get(symbol.upper())
    if not reference:
        return None
    return {"symbol": symbol.upper(), **reference}


def crypto_reference(symbol: str | None) -> dict | None:
    if not symbol:
        return None
    normalized = normalize_asset_symbol(symbol)
    reference = CRYPTO_REFERENCE.get(normalized)
    if not reference:
        return None
    return {"symbol": normalized, **reference}


def normalize_asset_symbol(symbol: str | None) -> str:
    if not symbol:
        return ""
    cleaned = symbol.upper().replace("/", "").replace("-", "").replace(" ", "")
    aliases = {
        "BTC": "BTCUSD",
        "BITCOIN": "BTCUSD",
        "XBTUSD": "BTCUSD",
        "ETH": "ETHUSD",
        "ETHEREUM": "ETHUSD",
        "SOL": "SOLUSD",
        "SOLANA": "SOLUSD",
        "XRP": "XRPUSD",
        "RIPPLE": "XRPUSD",
        "ADA": "ADAUSD",
        "CARDANO": "ADAUSD",
        "DOGE": "DOGEUSD",
        "DOGECOIN": "DOGEUSD",
        "USDC": "USDCUSD",
        "USDCOIN": "USDCUSD",
    }
    return aliases.get(cleaned, cleaned)


@dataclass(frozen=True)
class MarketPricePoint:
    symbol: str
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    adj_open: float | None
    adj_high: float | None
    adj_low: float | None
    adj_close: float | None
    adj_volume: int | None
    div_cash: float | None
    split_factor: float | None
    source: str = "tiingo"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CryptoPricePoint:
    symbol: str
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    volume_notional: float | None
    trades_done: int | None
    base_currency: str | None
    quote_currency: str | None
    source: str = "tiingo_crypto"

    def as_dict(self) -> dict:
        return asdict(self)


def parse_tiingo_price_row(symbol: str, row: dict) -> MarketPricePoint:
    return MarketPricePoint(
        symbol=symbol.upper(),
        date=row["date"][:10],
        open=row.get("open"),
        high=row.get("high"),
        low=row.get("low"),
        close=row.get("close"),
        volume=row.get("volume"),
        adj_open=row.get("adjOpen"),
        adj_high=row.get("adjHigh"),
        adj_low=row.get("adjLow"),
        adj_close=row.get("adjClose"),
        adj_volume=row.get("adjVolume"),
        div_cash=row.get("divCash"),
        split_factor=row.get("splitFactor"),
    )


def parse_tiingo_prices(symbol: str, payload: list[dict]) -> list[MarketPricePoint]:
    return [parse_tiingo_price_row(symbol, row) for row in payload]


def _number_from_market_string(value: str | int | float | None) -> float | int | None:
    if value in {None, "", "N/A"}:
        return None
    if isinstance(value, int | float):
        return value
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    number = float(cleaned)
    return int(number) if number.is_integer() else number


def parse_nasdaq_price_row(symbol: str, row: dict) -> MarketPricePoint:
    trade_date = datetime.strptime(row["date"], "%m/%d/%Y").date().isoformat()
    return MarketPricePoint(
        symbol=symbol.upper(),
        date=trade_date,
        open=_number_from_market_string(row.get("open")),
        high=_number_from_market_string(row.get("high")),
        low=_number_from_market_string(row.get("low")),
        close=_number_from_market_string(row.get("close")),
        volume=_number_from_market_string(row.get("volume")),
        adj_open=None,
        adj_high=None,
        adj_low=None,
        adj_close=None,
        adj_volume=None,
        div_cash=None,
        split_factor=None,
        source="nasdaq",
    )


def parse_nasdaq_prices(symbol: str, payload: dict) -> list[MarketPricePoint]:
    rows = payload.get("data", {}).get("tradesTable", {}).get("rows") or []
    return sorted(
        [parse_nasdaq_price_row(symbol, row) for row in rows if row.get("date")],
        key=lambda point: point.date,
    )


def parse_tiingo_crypto_price_row(symbol: str, metadata: dict, row: dict) -> CryptoPricePoint:
    return CryptoPricePoint(
        symbol=normalize_asset_symbol(symbol),
        date=row["date"][:10],
        open=row.get("open"),
        high=row.get("high"),
        low=row.get("low"),
        close=row.get("close"),
        volume=row.get("volume"),
        volume_notional=row.get("volumeNotional"),
        trades_done=row.get("tradesDone"),
        base_currency=metadata.get("baseCurrency"),
        quote_currency=metadata.get("quoteCurrency"),
    )


def parse_tiingo_crypto_prices(symbol: str, payload: list[dict]) -> list[CryptoPricePoint]:
    rows = []
    normalized = normalize_asset_symbol(symbol)
    for item in payload:
        if normalize_asset_symbol(item.get("ticker")) != normalized:
            continue
        metadata = {
            "baseCurrency": item.get("baseCurrency"),
            "quoteCurrency": item.get("quoteCurrency"),
        }
        for row in item.get("priceData", []):
            if row.get("date"):
                rows.append(parse_tiingo_crypto_price_row(normalized, metadata, row))
    return sorted(rows, key=lambda point: point.date)


class TiingoClient:
    def __init__(self, api_key: str | None = None, base_url: str = TIINGO_BASE_URL) -> None:
        self.api_key = api_key or settings.TIINGO_API_KEY
        self.base_url = base_url.rstrip("/")

    def historical_prices(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[MarketPricePoint]:
        if not self.api_key:
            raise RuntimeError("TIINGO_API_KEY is required for live market price refreshes")
        query = urlencode(
            {
                "startDate": start_date,
                "endDate": end_date,
                "token": self.api_key,
            }
        )
        request = Request(
            f"{self.base_url}/{symbol.lower()}/prices?{query}",
            headers={"User-Agent": USER_AGENT},
        )
        with urlopen(request, timeout=45) as response:
            return parse_tiingo_prices(symbol, json.loads(response.read().decode("utf-8")))


class TiingoCryptoClient:
    def __init__(self, api_key: str | None = None, base_url: str = TIINGO_CRYPTO_BASE_URL) -> None:
        self.api_key = api_key or settings.TIINGO_API_KEY
        self.base_url = base_url.rstrip("/")

    def historical_prices(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str | None = None,
        resample_freq: str = "1day",
    ) -> list[CryptoPricePoint]:
        if not self.api_key:
            raise RuntimeError("TIINGO_API_KEY is required for live crypto price refreshes")
        normalized = normalize_asset_symbol(symbol).lower()
        query = {
            "tickers": normalized,
            "startDate": start_date,
            "resampleFreq": resample_freq,
            "token": self.api_key,
        }
        if end_date:
            query["endDate"] = end_date
        request = Request(
            f"{self.base_url}/prices?{urlencode(query)}",
            headers={"User-Agent": USER_AGENT},
        )
        with urlopen(request, timeout=45) as response:
            return parse_tiingo_crypto_prices(normalized, json.loads(response.read().decode("utf-8")))


class NasdaqClient:
    def __init__(self, base_url: str = NASDAQ_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def historical_prices(
        self,
        symbol: str,
        *,
        start_date: str,
        end_date: str,
        asset_class: str | None = None,
    ) -> list[MarketPricePoint]:
        nasdaq_asset_class = {
            "equity": "stocks",
            "etf": "etf",
            "bond": "etf",
            "mutual_fund": "mutualfunds",
        }.get(asset_class or "equity", "stocks")
        query = urlencode(
            {
                "assetclass": nasdaq_asset_class,
                "fromdate": start_date,
                "todate": end_date,
                "limit": 9999,
            }
        )
        request = Request(
            f"{self.base_url}/{symbol.upper()}/historical?{query}",
            headers={
                "Accept": "application/json",
                "Origin": "https://www.nasdaq.com",
                "Referer": "https://www.nasdaq.com/",
                "User-Agent": "Mozilla/5.0 CivicLedger data refresh",
            },
        )
        with urlopen(request, timeout=45) as response:
            return parse_nasdaq_prices(symbol, json.loads(response.read().decode("utf-8")))
