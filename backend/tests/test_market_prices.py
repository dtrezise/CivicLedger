import json
from pathlib import Path

from app.services.market_prices import MARKET_PRICE_SYMBOLS, parse_tiingo_prices


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


def test_market_price_symbols_cover_core_overlays():
    assert MARKET_PRICE_SYMBOLS == ["SPY", "QQQ", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI"]
