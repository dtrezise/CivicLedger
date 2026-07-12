from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata


TARGET_ASSET_CLASSES = frozenset({"etf", "fund", "mutual_fund", "529", "529_portfolio"})


@dataclass(frozen=True)
class AssetReference:
    identifier: str
    identifier_type: str
    canonical_name: str
    issuer_name: str
    fund_family: str
    asset_class: str
    sector: str
    benchmark_symbol: str
    aliases: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        row = asdict(self)
        row.pop("aliases")
        row["symbol"] = self.identifier
        row["market_symbol"] = self.identifier
        row["sectors"] = [self.sector]
        return row


def _etf(
    identifier: str,
    canonical_name: str,
    issuer_name: str,
    fund_family: str,
    sector: str,
    benchmark_symbol: str,
    *aliases: str,
) -> AssetReference:
    return AssetReference(
        identifier=identifier,
        identifier_type="ticker",
        canonical_name=canonical_name,
        issuer_name=issuer_name,
        fund_family=fund_family,
        asset_class="etf",
        sector=sector,
        benchmark_symbol=benchmark_symbol,
        aliases=aliases,
    )


def _mutual_fund(
    identifier: str,
    canonical_name: str,
    issuer_name: str,
    fund_family: str,
    sector: str,
    benchmark_symbol: str,
    *aliases: str,
) -> AssetReference:
    return AssetReference(
        identifier=identifier,
        identifier_type="mutual_fund_symbol",
        canonical_name=canonical_name,
        issuer_name=issuer_name,
        fund_family=fund_family,
        asset_class="mutual_fund",
        sector=sector,
        benchmark_symbol=benchmark_symbol,
        aliases=aliases,
    )


def _portfolio_529(
    identifier: str,
    canonical_name: str,
    issuer_name: str,
    fund_family: str,
    sector: str,
    benchmark_symbol: str,
    *aliases: str,
) -> AssetReference:
    return AssetReference(
        identifier=identifier,
        identifier_type="underlying_fund_symbol",
        canonical_name=canonical_name,
        issuer_name=issuer_name,
        fund_family=fund_family,
        asset_class="529_portfolio",
        sector=sector,
        benchmark_symbol=benchmark_symbol,
        aliases=aliases,
    )


# This table is intentionally explicit. Additions should be source-checked rather than
# inferred from similar-looking names or fund-family prefixes.
CURATED_ASSET_REFERENCES = {
    reference.identifier: reference
    for reference in (
        _portfolio_529(
            "PTTRX",
            "PIMCO Total Return 529 Portfolio",
            "PIMCO Funds",
            "PIMCO",
            "Fixed Income",
            "BND",
            "Bright Directions College Savings 529 Plan PIMCO Total Return 529 Portfolio PTTRX",
            "PIMCO Total Return 529 Portfolio PTTRX",
        ),
        _portfolio_529(
            "MTMCX",
            "MainStay Total Return Bond 529 Fund",
            "MainStay Funds",
            "New York Life Investments / MainStay",
            "Fixed Income",
            "BND",
            "Bright Directions College Savings 529 Plan MainStay Total Return Bond 529 Fund MTMCX",
            "MainStay Total Return Bond 529 Fund MTMCX",
        ),
        _mutual_fund(
            "VFIAX",
            "Vanguard 500 Index Fund Admiral Shares",
            "Vanguard 500 Index Fund",
            "Vanguard",
            "Broad Market",
            "SPY",
            "Vanguard 500 Index Fund",
            "Vanguard 500 Index Fund Retirement",
        ),
        _mutual_fund(
            "VINIX",
            "Vanguard Institutional Index Fund Institutional Shares",
            "Vanguard Institutional Index Fund",
            "Vanguard",
            "Broad Market",
            "SPY",
            "Vanguard Institutional Index Fund",
            "Vanguard Institutional Index Fund Retirement",
        ),
        _mutual_fund(
            "FXAIX",
            "Fidelity 500 Index Fund",
            "Fidelity 500 Index Fund",
            "Fidelity Investments",
            "Broad Market",
            "SPY",
            "Fidelity 500 Index FD AI",
            "Fidelity 500 Index FD Al",
        ),
        _mutual_fund(
            "DODIX",
            "Dodge & Cox Income Fund",
            "Dodge & Cox Income Fund",
            "Dodge & Cox",
            "Fixed Income",
            "BND",
            "Dodge Cox Income FD",
        ),
        _mutual_fund(
            "DODFX",
            "Dodge & Cox International Stock Fund",
            "Dodge & Cox International Stock Fund",
            "Dodge & Cox",
            "International Equity",
            "IEFA",
            "Dodge Cox Intl Stock FD",
        ),
        _mutual_fund(
            "POSKX",
            "PRIMECAP Odyssey Stock Fund",
            "PRIMECAP Odyssey Funds",
            "PRIMECAP Management Company",
            "U.S. Equity",
            "SPY",
            "PRIMECAP Odyssey Stock FD",
        ),
        _mutual_fund(
            "VWIUX",
            "Vanguard Intermediate-Term Tax-Exempt Fund Admiral Shares",
            "Vanguard Municipal Bond Funds",
            "Vanguard",
            "Municipal Fixed Income",
            "BND",
            "Vanguard INTM TRM T E ADM",
            "Vanguard I T Tax EXMPT ADM",
        ),
        _etf(
            "SPY",
            "SPDR S&P 500 ETF Trust",
            "SPDR S&P 500 ETF Trust",
            "State Street Global Advisors / SPDR",
            "Broad Market",
            "SPY",
            "State Street SPDR S&P 500 Trust ETF I",
            "SPDR S&P 500 ETF",
        ),
        _etf(
            "QQQ",
            "Invesco QQQ Trust",
            "Invesco QQQ Trust",
            "Invesco",
            "Large Cap Growth",
            "QQQ",
            "QQQ ETF",
        ),
        _etf(
            "DIA",
            "SPDR Dow Jones Industrial Average ETF Trust",
            "SPDR Dow Jones Industrial Average ETF Trust",
            "State Street Global Advisors / SPDR",
            "Blue Chip",
            "DIA",
            "DIA ETF",
            "SPDR Dow Jones Industrial Average ETF",
        ),
        _etf(
            "IWM",
            "iShares Russell 2000 ETF",
            "iShares Russell 2000 ETF",
            "BlackRock / iShares",
            "Small Cap",
            "IWM",
        ),
        _etf(
            "BND",
            "Vanguard Total Bond Market ETF",
            "Vanguard Total Bond Market ETF",
            "Vanguard",
            "Fixed Income",
            "BND",
        ),
        _etf(
            "VOO",
            "Vanguard S&P 500 ETF",
            "Vanguard S&P 500 ETF",
            "Vanguard",
            "Broad Market",
            "SPY",
            "Vanguard S&P 500 ETF Unsolicited",
        ),
        _etf(
            "VTI",
            "Vanguard Total Stock Market ETF",
            "Vanguard Total Stock Market ETF",
            "Vanguard",
            "Broad Market",
            "SPY",
            "Vanguard Total Stock Market",
        ),
        _etf(
            "VEA",
            "Vanguard FTSE Developed Markets ETF",
            "Vanguard FTSE Developed Markets ETF",
            "Vanguard",
            "International Equity",
            "IEFA",
        ),
        _etf(
            "VWO",
            "Vanguard FTSE Emerging Markets ETF",
            "Vanguard FTSE Emerging Markets ETF",
            "Vanguard",
            "Emerging Markets",
            "IEMG",
        ),
        _etf(
            "VGK",
            "Vanguard FTSE Europe ETF",
            "Vanguard FTSE Europe ETF",
            "Vanguard",
            "Europe Equity",
            "IEFA",
        ),
        _etf(
            "VIG",
            "Vanguard Dividend Appreciation ETF",
            "Vanguard Dividend Appreciation ETF",
            "Vanguard",
            "Dividend Equity",
            "SPY",
            "Vanguard Div Appreciation ETF",
            "Vanguard Dividend Appreciation ETF DNQ",
        ),
        _etf(
            "VUG",
            "Vanguard Growth ETF",
            "Vanguard Growth ETF",
            "Vanguard",
            "Large Cap Growth",
            "QQQ",
        ),
        _etf(
            "VB",
            "Vanguard Small-Cap ETF",
            "Vanguard Small-Cap ETF",
            "Vanguard",
            "Small Cap",
            "IWM",
            "Vanguard Small Cap ETF DNQ",
        ),
        _etf(
            "VOE",
            "Vanguard Mid-Cap Value ETF",
            "Vanguard Mid-Cap Value ETF",
            "Vanguard",
            "Mid Cap Value",
            "SPY",
            "Vanguard Mid Cap Value ETF DNQ",
        ),
        _etf(
            "VOT",
            "Vanguard Mid-Cap Growth ETF",
            "Vanguard Mid-Cap Growth ETF",
            "Vanguard",
            "Mid Cap Growth",
            "QQQ",
            "Vanguard Mid Cap Growth ETF DNQ",
        ),
        _etf(
            "VNQ",
            "Vanguard Real Estate ETF",
            "Vanguard Real Estate ETF",
            "Vanguard",
            "Real Estate",
            "IYR",
            "Vanguard REIT ETF DNQ",
        ),
        _etf(
            "VPU",
            "Vanguard Utilities ETF",
            "Vanguard Utilities ETF",
            "Vanguard",
            "Utilities",
            "SPY",
        ),
        _etf(
            "VDC",
            "Vanguard Consumer Staples ETF",
            "Vanguard Consumer Staples ETF",
            "Vanguard",
            "Consumer Staples",
            "XLP",
        ),
        _etf(
            "VCSH",
            "Vanguard Short-Term Corporate Bond ETF",
            "Vanguard Short-Term Corporate Bond ETF",
            "Vanguard",
            "Corporate Fixed Income",
            "BND",
        ),
        _etf(
            "BNDX",
            "Vanguard Total International Bond ETF",
            "Vanguard Total International Bond ETF",
            "Vanguard",
            "International Fixed Income",
            "BND",
            "Vanguard Total Intl Bond ETF",
        ),
        _etf(
            "IVV",
            "iShares Core S&P 500 ETF",
            "iShares Core S&P 500 ETF",
            "BlackRock / iShares",
            "Broad Market",
            "SPY",
        ),
        _etf(
            "IVE",
            "iShares S&P 500 Value ETF",
            "iShares S&P 500 Value ETF",
            "BlackRock / iShares",
            "Large Cap Value",
            "SPY",
        ),
        _etf(
            "IVW",
            "iShares S&P 500 Growth ETF",
            "iShares S&P 500 Growth ETF",
            "BlackRock / iShares",
            "Large Cap Growth",
            "QQQ",
        ),
        _etf(
            "IEFA",
            "iShares Core MSCI EAFE ETF",
            "iShares Core MSCI EAFE ETF",
            "BlackRock / iShares",
            "International Equity",
            "IEFA",
            "!Shares Core MSCI EAFE ETF",
        ),
        _etf(
            "EFA",
            "iShares MSCI EAFE ETF",
            "iShares MSCI EAFE ETF",
            "BlackRock / iShares",
            "International Equity",
            "IEFA",
        ),
        _etf(
            "IEMG",
            "iShares Core MSCI Emerging Markets ETF",
            "iShares Core MSCI Emerging Markets ETF",
            "BlackRock / iShares",
            "Emerging Markets",
            "IEMG",
            "iShares Core MSCI Emerging",
        ),
        _etf(
            "EWJ",
            "iShares MSCI Japan ETF",
            "iShares MSCI Japan ETF",
            "BlackRock / iShares",
            "Japan Equity",
            "IEFA",
            "!Shares MSCI Japan ETF",
            "iShares MSCI Japan ETF I",
        ),
        _etf(
            "SHV",
            "iShares Short Treasury Bond ETF",
            "iShares Short Treasury Bond ETF",
            "BlackRock / iShares",
            "Treasury Fixed Income",
            "BND",
            "iShares Short Treasury Bond",
        ),
        _etf(
            "LQD",
            "iShares iBoxx $ Investment Grade Corporate Bond ETF",
            "iShares iBoxx $ Investment Grade Corporate Bond ETF",
            "BlackRock / iShares",
            "Corporate Fixed Income",
            "BND",
        ),
        _etf(
            "HYG",
            "iShares iBoxx $ High Yield Corporate Bond ETF",
            "iShares iBoxx $ High Yield Corporate Bond ETF",
            "BlackRock / iShares",
            "High Yield Fixed Income",
            "BND",
        ),
        _etf(
            "IEF",
            "iShares 7-10 Year Treasury Bond ETF",
            "iShares 7-10 Year Treasury Bond ETF",
            "BlackRock / iShares",
            "Treasury Fixed Income",
            "BND",
        ),
        _etf(
            "TIP",
            "iShares TIPS Bond ETF",
            "iShares TIPS Bond ETF",
            "BlackRock / iShares",
            "Inflation-Protected Fixed Income",
            "BND",
        ),
        _etf(
            "IWD",
            "iShares Russell 1000 Value ETF",
            "iShares Russell 1000 Value ETF",
            "BlackRock / iShares",
            "Large Cap Value",
            "SPY",
        ),
        _etf(
            "IWF",
            "iShares Russell 1000 Growth ETF",
            "iShares Russell 1000 Growth ETF",
            "BlackRock / iShares",
            "Large Cap Growth",
            "QQQ",
        ),
        _etf(
            "IWN",
            "iShares Russell 2000 Value ETF",
            "iShares Russell 2000 Value ETF",
            "BlackRock / iShares",
            "Small Cap Value",
            "IWM",
        ),
        _etf(
            "PFF",
            "iShares Preferred and Income Securities ETF",
            "iShares Preferred and Income Securities ETF",
            "BlackRock / iShares",
            "Preferred Securities",
            "BND",
            "iShares U.S. Preferred Stock ETF",
            "iShares US Preferred Stock ETF",
        ),
        _etf(
            "IJR",
            "iShares Core S&P Small-Cap ETF",
            "iShares Core S&P Small-Cap ETF",
            "BlackRock / iShares",
            "Small Cap",
            "IWM",
        ),
        _etf(
            "IYR",
            "iShares U.S. Real Estate ETF",
            "iShares U.S. Real Estate ETF",
            "BlackRock / iShares",
            "Real Estate",
            "SPY",
        ),
        _etf(
            "EMB",
            "iShares J.P. Morgan USD Emerging Markets Bond ETF",
            "iShares J.P. Morgan USD Emerging Markets Bond ETF",
            "BlackRock / iShares",
            "Emerging Markets Fixed Income",
            "BND",
        ),
        _etf(
            "BBCA",
            "JPMorgan BetaBuilders Canada ETF",
            "JPMorgan BetaBuilders Canada ETF",
            "J.P. Morgan Asset Management",
            "Canada Equity",
            "IEFA",
        ),
        _etf(
            "BBEU",
            "JPMorgan BetaBuilders Europe ETF",
            "JPMorgan BetaBuilders Europe ETF",
            "J.P. Morgan Asset Management",
            "Europe Equity",
            "IEFA",
        ),
        _etf(
            "BBJP",
            "JPMorgan BetaBuilders Japan ETF",
            "JPMorgan BetaBuilders Japan ETF",
            "J.P. Morgan Asset Management",
            "Japan Equity",
            "IEFA",
        ),
        _etf(
            "BBAX",
            "JPMorgan BetaBuilders Developed Asia Pacific ex-Japan ETF",
            "JPMorgan BetaBuilders Developed Asia Pacific ex-Japan ETF",
            "J.P. Morgan Asset Management",
            "Asia Pacific Equity",
            "IEFA",
            "JPM BetaBuilders Developed Asia Ex Japan ETF",
        ),
        _etf(
            "RSP",
            "Invesco S&P 500 Equal Weight ETF",
            "Invesco S&P 500 Equal Weight ETF",
            "Invesco",
            "Broad Market",
            "SPY",
            "Guggenheim S&P 500 Equal Weight ETF",
            "RSP ETF",
        ),
        _etf(
            "SCHD",
            "Schwab U.S. Dividend Equity ETF",
            "Schwab U.S. Dividend Equity ETF",
            "Charles Schwab Investment Management",
            "Dividend Equity",
            "SPY",
            "Schwab US Dividend Equity ETF",
        ),
        _etf(
            "JEPI",
            "JPMorgan Equity Premium Income ETF",
            "JPMorgan Equity Premium Income ETF",
            "J.P. Morgan Asset Management",
            "Equity Income",
            "SPY",
        ),
        _etf(
            "XLP",
            "Consumer Staples Select Sector SPDR Fund",
            "Consumer Staples Select Sector SPDR Fund",
            "State Street Global Advisors / SPDR",
            "Consumer Staples",
            "XLP",
            "State Street Consumer Staples Select Sector SPDR ETF",
        ),
        _etf(
            "XLK",
            "Technology Select Sector SPDR Fund",
            "Technology Select Sector SPDR Fund",
            "State Street Global Advisors / SPDR",
            "Information Technology",
            "XLK",
        ),
        _etf(
            "XLF",
            "Financial Select Sector SPDR Fund",
            "Financial Select Sector SPDR Fund",
            "State Street Global Advisors / SPDR",
            "Financials",
            "XLF",
        ),
        _etf(
            "XLE",
            "Energy Select Sector SPDR Fund",
            "Energy Select Sector SPDR Fund",
            "State Street Global Advisors / SPDR",
            "Energy",
            "XLE",
            "State Street Energy Select Sector SPDR ETF",
        ),
        _etf(
            "XLV",
            "Health Care Select Sector SPDR Fund",
            "Health Care Select Sector SPDR Fund",
            "State Street Global Advisors / SPDR",
            "Health Care",
            "XLV",
        ),
        _etf(
            "XLI",
            "Industrial Select Sector SPDR Fund",
            "Industrial Select Sector SPDR Fund",
            "State Street Global Advisors / SPDR",
            "Industrials",
            "XLI",
        ),
    )
}

CURATED_ASSET_MAPPINGS = {
    identifier: {**reference.as_dict(), "aliases": list(reference.aliases)}
    for identifier, reference in CURATED_ASSET_REFERENCES.items()
}


_DISCLOSURE_SUFFIX_RE = re.compile(
    r"\b(?:FILING\s+STATUS|SUBHOLDING\s+OF|LOCATION|DESCRIPTION)\s*:",
    re.IGNORECASE,
)
_FORM_CODE_RE = re.compile(r"\[(?:EF|ETF|MF|OT|ST)\]", re.IGNORECASE)
_OWNERSHIP_NOTE_RE = re.compile(r"\((?:S|DC|RETIREMENT)\)", re.IGNORECASE)
_DERIVATIVE_RE = re.compile(r"^\s*(?:CALL|PUT)(?:\s|/)", re.IGNORECASE)
_STANDALONE_529_RE = re.compile(r"(?<![A-Z0-9])529(?![A-Z0-9])", re.IGNORECASE)


def normalize_asset_name(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"(?<![A-Z])!SHARES", "ISHARES", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMSC!\b", "MSCI", text, flags=re.IGNORECASE)
    suffix = _DISCLOSURE_SUFFIX_RE.search(text)
    if suffix:
        text = text[: suffix.start()]
    text = _FORM_CODE_RE.sub(" ", text)
    text = _OWNERSHIP_NOTE_RE.sub(" ", text)
    text = re.sub(r"\b(?:UNSOLICITED|SOLICITED)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+DNQ\b|\bDNQ\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().upper()


def is_target_asset(asset_name: str | None, asset_class: str | None) -> bool:
    normalized_class = (asset_class or "").strip().lower().replace("-", "_")
    return normalized_class in TARGET_ASSET_CLASSES or bool(
        asset_name and _STANDALONE_529_RE.search(asset_name)
    )


def _build_alias_index() -> dict[str, AssetReference]:
    index: dict[str, AssetReference] = {}
    for reference in CURATED_ASSET_REFERENCES.values():
        for alias in (reference.canonical_name, *reference.aliases):
            normalized = normalize_asset_name(alias)
            previous = index.get(normalized)
            if previous and previous.identifier != reference.identifier:
                raise ValueError(f"Ambiguous curated asset alias: {alias}")
            index[normalized] = reference
    return index


_ALIAS_INDEX = _build_alias_index()


def _known_symbol_candidates(value: str, disclosed_ticker: str | None) -> list[str]:
    normalized = normalize_asset_name(value)
    tokens = set(normalized.split())
    candidates = {symbol for symbol in CURATED_ASSET_REFERENCES if symbol in tokens}
    ticker = (disclosed_ticker or "").strip().upper()
    if ticker in CURATED_ASSET_REFERENCES:
        # A disclosed ticker is accepted only when it also appears as a standalone
        # token. This rejects parser guesses such as JPM for a JPMorgan fund name.
        if ticker in tokens:
            candidates.add(ticker)
    return sorted(candidates)


def resolve_asset_name(
    asset_name: str | None,
    disclosed_ticker: str | None = None,
    asset_class: str | None = None,
) -> dict | None:
    if not asset_name or _DERIVATIVE_RE.search(asset_name):
        return None
    normalized = normalize_asset_name(asset_name)
    if not normalized:
        return None

    reference = _ALIAS_INDEX.get(normalized)
    match_method = "curated_normalized_name"
    matched_value = normalized
    if reference is None:
        candidates = _known_symbol_candidates(asset_name, disclosed_ticker)
        if len(candidates) != 1:
            return None
        matched_value = candidates[0]
        reference = CURATED_ASSET_REFERENCES[matched_value]
        match_method = "curated_explicit_symbol"

    if asset_class and not is_target_asset(asset_name, asset_class):
        return None

    return {
        "resolution_status": "resolved",
        "match_method": match_method,
        "matched_value": matched_value,
        "normalized_name": normalized,
        **reference.as_dict(),
    }


def resolve_asset(
    asset_name: str | None,
    disclosed_ticker: str | None = None,
    asset_class: str | None = None,
) -> dict | None:
    return resolve_asset_name(asset_name, disclosed_ticker, asset_class)


def asset_resolution_record(
    asset_name: str | None,
    disclosed_ticker: str | None = None,
    asset_class: str | None = None,
) -> dict:
    resolved = resolve_asset_name(asset_name, disclosed_ticker, asset_class)
    if resolved:
        return resolved
    return {
        "resolution_status": "unresolved",
        "match_method": None,
        "matched_value": None,
        "normalized_name": normalize_asset_name(asset_name),
        "identifier": None,
        "identifier_type": None,
        "symbol": None,
        "market_symbol": None,
        "canonical_name": None,
        "issuer_name": None,
        "fund_family": None,
        "asset_class": None,
        "sector": None,
        "sectors": [],
        "benchmark_symbol": None,
    }


def curated_asset_reference(identifier: str | None) -> dict | None:
    if not identifier:
        return None
    reference = CURATED_ASSET_REFERENCES.get(identifier.upper())
    return reference.as_dict() if reference else None


def asset_reference(identifier: str | None) -> dict | None:
    return curated_asset_reference(identifier)
