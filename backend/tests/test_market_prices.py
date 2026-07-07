import json
from pathlib import Path

from app.services.market_prices import (
    MARKET_PRICE_SYMBOLS,
    crypto_reference,
    normalize_asset_symbol,
    parse_nasdaq_prices,
    parse_tiingo_crypto_prices,
    parse_tiingo_prices,
    ticker_reference,
)


FIXTURES = Path(__file__).parent / "fixtures" / "market_prices"


def test_parse_tiingo_prices_normalizes_adjusted_fields():
    payload = json.loads((FIXTURES / "tiingo_prices.json").read_text())
    points = parse_tiingo_prices("SPY", payload)

    assert len(points) == 1
    assert points[0].symbol == "SPY"
    assert points[0].date == "2024-01-02"
    assert points[0].adj_close == 469.0941280398
    assert points[0].close == 472.65
    assert points[0].source == "tiingo"


def test_parse_nasdaq_prices_normalizes_close_fields():
    points = parse_nasdaq_prices(
        "AAPL",
        {
            "data": {
                "tradesTable": {
                    "rows": [
                        {
                            "date": "01/03/2024",
                            "close": "$185.64",
                            "volume": "58,460,000",
                            "open": "$184.22",
                            "high": "$185.88",
                            "low": "$183.43",
                        }
                    ]
                }
            }
        },
    )

    assert len(points) == 1
    assert points[0].symbol == "AAPL"
    assert points[0].date == "2024-01-03"
    assert points[0].close == 185.64
    assert points[0].adj_close is None
    assert points[0].source == "nasdaq"


def test_parse_tiingo_crypto_prices_normalizes_pair_metadata():
    points = parse_tiingo_crypto_prices(
        "BTC/USD",
        [
            {
                "ticker": "btcusd",
                "baseCurrency": "btc",
                "quoteCurrency": "usd",
                "priceData": [
                    {
                        "date": "2024-01-03T00:00:00+00:00",
                        "open": 44900.0,
                        "high": 45500.0,
                        "low": 44200.0,
                        "close": 45123.0,
                        "volume": 123.4,
                        "volumeNotional": 5560000.0,
                        "tradesDone": 3456,
                    }
                ],
            }
        ],
    )

    assert len(points) == 1
    assert points[0].symbol == "BTCUSD"
    assert points[0].date == "2024-01-03"
    assert points[0].close == 45123.0
    assert points[0].base_currency == "btc"
    assert points[0].quote_currency == "usd"
    assert points[0].source == "tiingo_crypto"


def test_market_price_symbols_cover_core_overlays():
    assert {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "JNJ"} <= set(
        MARKET_PRICE_SYMBOLS
    )
    assert {"SPY", "QQQ", "IWM", "BND", "VFIAX", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI"} <= set(
        MARKET_PRICE_SYMBOLS
    )


def test_ticker_reference_maps_issuer_sector_and_benchmark():
    reference = ticker_reference("aapl")

    assert reference == {
        "symbol": "AAPL",
        "issuer_name": "Apple Inc.",
        "asset_class": "equity",
        "sector": "Information Technology",
        "benchmark_symbol": "XLK",
    }


def test_crypto_reference_normalizes_common_disclosure_labels():
    assert normalize_asset_symbol("Bitcoin") == "BTCUSD"
    assert normalize_asset_symbol("ETH/USD") == "ETHUSD"
    assert normalize_asset_symbol("Dogecoin") == "DOGEUSD"
    assert normalize_asset_symbol("Cardano") == "ADAUSD"
    assert normalize_asset_symbol("Ripple") == "XRPUSD"
    assert crypto_reference("btc")["asset_class"] == "crypto"
    assert crypto_reference("doge")["issuer_name"] == "Dogecoin / U.S. Dollar"
