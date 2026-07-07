from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings


TIINGO_BASE_URL = "https://api.tiingo.com/tiingo/daily"
TIINGO_CRYPTO_BASE_URL = "https://api.tiingo.com/tiingo/crypto"
NASDAQ_BASE_URL = "https://api.nasdaq.com/api/quote"
USER_AGENT = "CivicLedger data refresh"

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
