from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import re
import unicodedata
import uuid
from typing import Iterable, Mapping, Sequence


SCHEMA_VERSION = "canonical-entity-reference-v1"
ENTITY_NAMESPACE = uuid.UUID("d9ca3325-3c7c-55de-9e6b-7a0df5018f8b")
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,14}$")
_CORPORATE_WORDS = frozenset(
    {
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "lp",
        "ltd",
        "plc",
        "the",
    }
)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_uuid(kind: str, key: str) -> str:
    return str(uuid.uuid5(ENTITY_NAMESPACE, f"{kind}:{key}"))


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _name_core(value: object) -> str:
    return " ".join(
        token for token in normalize_name(value).split() if token not in _CORPORATE_WORDS
    )


def _symbol(value: object) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if _SYMBOL_RE.fullmatch(normalized) else None


def _source_ref(
    source_id: str,
    *,
    record_id: str | None = None,
    field: str | None = None,
    url: str | None = None,
) -> dict:
    return {
        key: value
        for key, value in {
            "source_id": source_id,
            "source_record_id": record_id,
            "source_field": field,
            "source_url": url,
        }.items()
        if value is not None
    }


def _dedupe_dicts(rows: Iterable[Mapping]) -> list[dict]:
    unique = {canonical_json(dict(row)): dict(row) for row in rows}
    return [unique[key] for key in sorted(unique)]


def _hashed(record: dict) -> dict:
    result = dict(record)
    result["record_hash"] = stable_hash(result)
    return result


@dataclass
class _EntityDraft:
    internal_id: int
    names: list[tuple[int, str, dict]] = field(default_factory=list)
    aliases: dict[tuple[str, str], dict] = field(default_factory=dict)
    identifiers: dict[tuple[str, str], dict] = field(default_factory=dict)
    sectors: dict[tuple[str, str], dict] = field(default_factory=dict)
    symbols: set[str] = field(default_factory=set)
    ciks: set[str] = field(default_factory=set)
    source_entity_ids: set[str] = field(default_factory=set)
    organization_types: list[tuple[int, str]] = field(default_factory=list)
    source_ids: set[str] = field(default_factory=set)

    def add_name(self, name: object, priority: int, provenance: dict) -> None:
        value = str(name or "").strip()
        if not value:
            return
        self.names.append((priority, value, provenance))
        self.add_alias(value, "legal_or_issuer_name", provenance, confidence=1.0)

    def add_alias(
        self,
        alias: object,
        alias_type: str,
        provenance: dict,
        *,
        confidence: float | None = None,
        occurrence_count: int | None = None,
        source_datasets: Sequence[str] = (),
        sample_transaction_ids: Sequence[str] = (),
    ) -> None:
        value = str(alias or "").strip()
        normalized = normalize_name(value)
        if not normalized:
            return
        key = (normalized, alias_type)
        row = self.aliases.setdefault(
            key,
            {
                "alias": value,
                "normalized_alias": normalized,
                "alias_type": alias_type,
                "confidence": confidence,
                "occurrence_count": 0,
                "source_datasets": set(),
                "sample_transaction_ids": set(),
                "provenance": [],
            },
        )
        if (value.casefold(), value) < (row["alias"].casefold(), row["alias"]):
            row["alias"] = value
        if confidence is not None:
            row["confidence"] = max(row["confidence"] or 0.0, confidence)
        row["occurrence_count"] += occurrence_count or 0
        row["source_datasets"].update(str(item) for item in source_datasets if item)
        row["sample_transaction_ids"].update(
            str(item) for item in sample_transaction_ids if item
        )
        row["provenance"].append(provenance)

    def add_identifier(
        self,
        scheme: str,
        value: object,
        provenance: dict,
        *,
        is_primary: bool = False,
    ) -> None:
        normalized = str(value or "").strip()
        if not normalized:
            return
        key = (scheme, normalized)
        row = self.identifiers.setdefault(
            key,
            {
                "scheme": scheme,
                "value": normalized,
                "is_primary": False,
                "provenance": [],
            },
        )
        row["is_primary"] = row["is_primary"] or is_primary
        row["provenance"].append(provenance)

    def add_sector(
        self,
        taxonomy: str,
        code: object,
        name: object,
        provenance: dict,
        *,
        confidence: float | None = None,
        is_primary: bool = False,
    ) -> None:
        sector_name = str(name or "").strip()
        sector_code = str(code or "").strip()
        if not sector_name or not sector_code:
            return
        key = (taxonomy, sector_code)
        row = self.sectors.setdefault(
            key,
            {
                "taxonomy": taxonomy,
                "code": sector_code,
                "name": sector_name,
                "confidence": confidence,
                "is_primary": False,
                "provenance": [],
            },
        )
        if confidence is not None:
            row["confidence"] = max(row["confidence"] or 0.0, confidence)
        row["is_primary"] = row["is_primary"] or is_primary
        row["provenance"].append(provenance)


@dataclass
class _AssetDraft:
    entity_internal_id: int
    canonical_name: str
    asset_class: str
    primary_symbol: str | None
    aliases: set[str] = field(default_factory=set)
    provenance: list[dict] = field(default_factory=list)


class _Registry:
    def __init__(self) -> None:
        self.entities: list[_EntityDraft] = []
        self.by_cik: dict[str, int] = {}
        self.by_source_entity: dict[str, int] = {}
        self.by_symbol: dict[str, set[int]] = defaultdict(set)
        self.by_name: dict[str, set[int]] = defaultdict(set)
        self.quality_issues: list[dict] = []

    def _new(self) -> _EntityDraft:
        draft = _EntityDraft(len(self.entities))
        self.entities.append(draft)
        return draft

    def resolve(
        self,
        *,
        name: object,
        cik: str | None = None,
        source_entity_id: str | None = None,
        symbols: Iterable[str] = (),
        allow_name_match: bool = True,
        issue_source_id: str,
    ) -> _EntityDraft:
        candidates: set[int] = set()
        if cik and cik in self.by_cik:
            candidates.add(self.by_cik[cik])
        if source_entity_id and source_entity_id in self.by_source_entity:
            candidates.add(self.by_source_entity[source_entity_id])
        for item in symbols:
            candidates.update(self.by_symbol.get(item, set()))
        normalized = normalize_name(name)
        core = _name_core(name)
        if not candidates and allow_name_match:
            candidates.update(self.by_name.get(normalized, set()))
            if not candidates and core:
                candidates.update(self.by_name.get(f"core:{core}", set()))
        if len(candidates) == 1:
            return self.entities[next(iter(candidates))]
        if len(candidates) > 1:
            self.quality_issues.append(
                {
                    "issue_type": "ambiguous_entity_match",
                    "severity": "review",
                    "normalized_label": normalized,
                    "candidate_internal_ids": sorted(candidates),
                    "source_id": issue_source_id,
                }
            )
        return self._new()

    def index(
        self,
        entity: _EntityDraft,
        *,
        name: object,
        cik: str | None = None,
        source_entity_id: str | None = None,
        symbols: Iterable[str] = (),
    ) -> None:
        normalized = normalize_name(name)
        core = _name_core(name)
        if normalized:
            self.by_name[normalized].add(entity.internal_id)
        if core:
            self.by_name[f"core:{core}"].add(entity.internal_id)
        if cik:
            entity.ciks.add(cik)
            self.by_cik[cik] = entity.internal_id
        if source_entity_id:
            entity.source_entity_ids.add(source_entity_id)
            self.by_source_entity[source_entity_id] = entity.internal_id
        for item in symbols:
            symbol = _symbol(item)
            if symbol:
                entity.symbols.add(symbol)
                self.by_symbol[symbol].add(entity.internal_id)


def _context_sector_code(name: str) -> str:
    return normalize_name(name).replace(" ", "-")


def _source_date(source_snapshots: Sequence[Mapping]) -> str | None:
    values = [
        str(row.get("artifact_date"))[:10]
        for row in source_snapshots
        if row.get("artifact_date")
    ]
    return max(values) if values else None


def build_entity_reference(
    *,
    asset_resolution: Mapping,
    company_entity_reference: Mapping,
    sec_filing_events: Mapping,
    market_prices: Mapping,
    disclosure_rows: Iterable[Mapping],
    ticker_history: Iterable[Mapping],
    source_snapshots: Sequence[Mapping],
) -> dict:
    """Build a conservative canonical reference without fuzzy identity guesses."""

    registry = _Registry()
    assets: dict[tuple[int, str, str, str], _AssetDraft] = {}
    ticker_rows: list[dict] = []

    def add_asset(
        entity: _EntityDraft,
        *,
        canonical_name: str,
        asset_class: str,
        symbol: str | None,
        aliases: Iterable[str],
        provenance: dict,
    ) -> None:
        normalized_symbol = _symbol(symbol)
        identity = (
            entity.internal_id,
            normalized_symbol or "",
            normalize_name(canonical_name),
            asset_class or "unknown",
        )
        if normalized_symbol:
            same_symbol = [
                key
                for key in assets
                if key[0] == entity.internal_id and key[1] == normalized_symbol
            ]
            if same_symbol:
                identity = same_symbol[0]
        draft = assets.setdefault(
            identity,
            _AssetDraft(
                entity_internal_id=entity.internal_id,
                canonical_name=canonical_name,
                asset_class=asset_class or "unknown",
                primary_symbol=normalized_symbol,
            ),
        )
        draft.aliases.update(str(item).strip() for item in aliases if str(item).strip())
        draft.provenance.append(provenance)

    # SEC CIK and ticker evidence is the strongest identity anchor.
    companies: dict[str, dict] = {}
    for event in sec_filing_events.get("events", []):
        company = event.get("company") or {}
        cik = str(company.get("cik") or "").strip()
        if not cik:
            continue
        aggregate = companies.setdefault(
            cik,
            {
                "names": set(),
                "tickers": set(),
                "exchanges": set(),
                "sic": None,
                "sic_description": None,
                "urls": set(),
            },
        )
        aggregate["names"].add(str(company.get("name") or "").strip())
        aggregate["tickers"].update(filter(None, (_symbol(x) for x in company.get("tickers", []))))
        aggregate["exchanges"].update(str(x) for x in company.get("exchanges", []) if x)
        aggregate["sic"] = company.get("sic") or aggregate["sic"]
        aggregate["sic_description"] = (
            company.get("sic_description") or aggregate["sic_description"]
        )
        aggregate["urls"].update(str(x) for x in event.get("source_urls", []) if x)

    for cik, company in sorted(companies.items()):
        name = sorted(filter(None, company["names"]), key=lambda x: (len(x), x))[0]
        symbols = sorted(company["tickers"])
        source_url = next(
            (url for url in sorted(company["urls"]) if "data.sec.gov/submissions" in url),
            None,
        )
        provenance = _source_ref(
            "sec_filing_events", record_id=f"sec-company:{cik}", url=source_url
        )
        entity = registry.resolve(
            name=name,
            cik=cik,
            symbols=symbols,
            issue_source_id="sec_filing_events",
        )
        entity.add_name(name, 80, provenance)
        entity.add_identifier("SEC_CIK", cik, provenance, is_primary=True)
        entity.organization_types.append((100, "company"))
        entity.source_ids.add("sec_filing_events")
        if company["sic"] and company["sic_description"]:
            entity.add_sector(
                "SEC_SIC",
                company["sic"],
                company["sic_description"],
                provenance,
                confidence=1.0,
                is_primary=True,
            )
        registry.index(entity, name=name, cik=cik, symbols=symbols)
        for ticker in symbols:
            add_asset(
                entity,
                canonical_name=name,
                asset_class="unknown_security",
                symbol=ticker,
                aliases=(ticker,),
                provenance=provenance,
            )

    # The market reference supplies current issuer/security labels and contextual sectors.
    for ticker, reference in sorted((market_prices.get("ticker_reference") or {}).items()):
        symbol = _symbol(ticker)
        name = str(reference.get("issuer_name") or "").strip()
        if not symbol or not name:
            continue
        provenance = _source_ref(
            "market_prices", record_id=f"ticker-reference:{symbol}", field="ticker_reference"
        )
        entity = registry.resolve(
            name=name,
            symbols=(symbol,),
            issue_source_id="market_prices",
        )
        entity.add_name(name, 90, provenance)
        entity.add_alias(symbol, "ticker_symbol", provenance, confidence=1.0)
        entity.organization_types.append(
            (80, "fund" if reference.get("asset_class") in {"etf", "fund", "mutual_fund"} else "company")
        )
        entity.source_ids.add("market_prices")
        sector = str(reference.get("sector") or "").strip()
        if sector:
            entity.add_sector(
                "CIVICLEDGER_CONTEXT",
                _context_sector_code(sector),
                sector,
                provenance,
                confidence=0.9,
                is_primary=True,
            )
        registry.index(entity, name=name, symbols=(symbol,))
        add_asset(
            entity,
            canonical_name=name,
            asset_class=str(reference.get("asset_class") or "unknown"),
            symbol=symbol,
            aliases=(name, symbol),
            provenance=provenance,
        )

    # The company map contains contextual aliases and scopes. Ticker scope is not
    # treated as issuer history because it also contains comparison benchmarks.
    for row in sorted(
        company_entity_reference.get("entities", []), key=lambda item: str(item.get("entity_id"))
    ):
        source_entity_id = str(row.get("entity_id") or "").strip()
        name = str(row.get("issuer_name") or "").strip()
        aliases = [str(item).strip() for item in row.get("aliases", []) if str(item).strip()]
        issuer_symbols = sorted(
            {
                symbol
                for alias in aliases
                if (symbol := _symbol(alias)) and symbol in registry.by_symbol
            }
        )
        provenance = _source_ref(
            "company_entity_reference", record_id=source_entity_id or None
        )
        entity = registry.resolve(
            name=name,
            source_entity_id=source_entity_id or None,
            symbols=issuer_symbols,
            issue_source_id="company_entity_reference",
        )
        entity.add_name(name, 95, provenance)
        entity.add_identifier(
            "CIVICLEDGER_ENTITY_ID", source_entity_id, provenance, is_primary=not entity.ciks
        )
        entity.organization_types.append(
            (70, "other" if "Crypto" in row.get("sector_scope", []) else "company")
        )
        entity.source_ids.add("company_entity_reference")
        for alias in aliases:
            alias_type = "ticker_symbol" if _symbol(alias) else "context_alias"
            entity.add_alias(alias, alias_type, provenance, confidence=0.8)
        for sector in sorted(set(row.get("sector_scope", []))):
            entity.add_sector(
                "CIVICLEDGER_CONTEXT",
                _context_sector_code(sector),
                sector,
                provenance,
                confidence=0.8,
                is_primary=False,
            )
        registry.index(
            entity,
            name=name,
            source_entity_id=source_entity_id or None,
            symbols=issuer_symbols,
        )
        if "Crypto" in row.get("sector_scope", []):
            for alias in aliases:
                symbol = _symbol(alias)
                if symbol and symbol.endswith("USD"):
                    registry.index(entity, name=name, symbols=(symbol,))
                    add_asset(
                        entity,
                        canonical_name=name,
                        asset_class="crypto",
                        symbol=symbol,
                        aliases=(name, symbol),
                        provenance=provenance,
                    )

    # Resolved curated assets add funds and disclosure-observed aliases. Unresolved
    # assets become explicit quality records and never create organizations.
    for row in sorted(asset_resolution.get("assets", []), key=lambda item: str(item.get("id"))):
        source_id = "asset_resolution"
        provenance = _source_ref(source_id, record_id=str(row.get("id") or "") or None)
        if row.get("resolution_status") != "resolved" or not row.get("issuer_name"):
            registry.quality_issues.append(
                {
                    "issue_type": "unresolved_asset_resolution",
                    "severity": "review",
                    "normalized_label": row.get("normalized_name"),
                    "observed_names": sorted(set(row.get("observed_names", []))),
                    "occurrence_count": int(row.get("occurrence_count") or 0),
                    "source_datasets": sorted(set(row.get("source_datasets", []))),
                    "sample_transaction_ids": sorted(set(row.get("transaction_ids", [])))[:10],
                    "source_id": source_id,
                    "source_record_id": row.get("id"),
                }
            )
            continue
        issuer_name = str(row["issuer_name"]).strip()
        symbol = _symbol(row.get("symbol") or row.get("identifier"))
        entity = registry.resolve(
            name=issuer_name,
            symbols=(symbol,) if symbol else (),
            issue_source_id=source_id,
        )
        entity.add_name(issuer_name, 70, provenance)
        entity.organization_types.append((90, "fund"))
        entity.source_ids.add(source_id)
        entity.add_alias(
            row.get("canonical_name"), "managed_asset_name", provenance, confidence=0.9
        )
        for observed in sorted(set(row.get("observed_names", []))):
            entity.add_alias(
                observed,
                "disclosure_asset_label",
                provenance,
                confidence=0.9,
                occurrence_count=int(row.get("occurrence_count") or 0),
                source_datasets=row.get("source_datasets", []),
                sample_transaction_ids=row.get("transaction_ids", [])[:5],
            )
        for sector in sorted(set(row.get("sectors", []))):
            entity.add_sector(
                "CIVICLEDGER_CONTEXT",
                _context_sector_code(sector),
                sector,
                provenance,
                confidence=0.9,
                is_primary=True,
            )
        registry.index(entity, name=issuer_name, symbols=(symbol,) if symbol else ())
        add_asset(
            entity,
            canonical_name=str(row.get("canonical_name") or issuer_name),
            asset_class=str(row.get("asset_class") or "unknown"),
            symbol=symbol,
            aliases=row.get("observed_names", []),
            provenance=provenance,
        )

    # Disclosure labels are linked only through a unique, already-supported ticker.
    disclosure_groups: dict[tuple[str, str, str], dict] = {}
    for row in disclosure_rows:
        label = str(row.get("asset_display_name") or row.get("raw_asset_text") or "").strip()
        ticker = _symbol(row.get("ticker"))
        if not label:
            continue
        key = (normalize_name(label), ticker or "", str(row.get("source_dataset") or "unknown"))
        aggregate = disclosure_groups.setdefault(
            key,
            {
                "label": label,
                "ticker": ticker,
                "count": 0,
                "transaction_ids": set(),
                "source_snapshot_ids": set(),
            },
        )
        aggregate["count"] += 1
        if row.get("id"):
            aggregate["transaction_ids"].add(str(row["id"]))
        if row.get("_source_snapshot_id"):
            aggregate["source_snapshot_ids"].add(str(row["_source_snapshot_id"]))

    unlinked_without_ticker = 0
    for (normalized, ticker, source_dataset), aggregate in sorted(disclosure_groups.items()):
        if not ticker:
            unlinked_without_ticker += aggregate["count"]
            continue
        candidates = registry.by_symbol.get(ticker, set())
        if len(candidates) != 1:
            registry.quality_issues.append(
                {
                    "issue_type": (
                        "unresolved_disclosed_ticker" if not candidates else "ambiguous_disclosed_ticker"
                    ),
                    "severity": "review",
                    "normalized_label": normalized,
                    "observed_label": aggregate["label"],
                    "ticker": ticker,
                    "occurrence_count": aggregate["count"],
                    "source_datasets": [source_dataset],
                    "candidate_internal_ids": sorted(candidates),
                    "sample_transaction_ids": sorted(aggregate["transaction_ids"])[:10],
                    "source_id": "disclosure_labels",
                }
            )
            continue
        entity = registry.entities[next(iter(candidates))]
        source_ids = sorted(aggregate["source_snapshot_ids"])
        provenance = _source_ref(
            source_ids[0] if len(source_ids) == 1 else "disclosure_labels",
            record_id=sorted(aggregate["transaction_ids"])[0]
            if aggregate["transaction_ids"]
            else None,
            field="asset_display_name",
        )
        entity.add_alias(
            aggregate["label"],
            "disclosure_asset_label",
            provenance,
            confidence=1.0,
            occurrence_count=aggregate["count"],
            source_datasets=(source_dataset,),
            sample_transaction_ids=sorted(aggregate["transaction_ids"])[:5],
        )

    # Build stable organization IDs after all external identifiers are known.
    organization_ids: dict[int, str] = {}
    canonical_names: dict[int, str] = {}
    for entity in registry.entities:
        canonical_name = sorted(
            entity.names,
            key=lambda item: (-item[0], len(item[1]), item[1].casefold(), item[1]),
        )[0][1]
        stable_key = (
            f"cik:{sorted(entity.ciks)[0]}"
            if entity.ciks
            else f"source:{sorted(entity.source_entity_ids)[0]}"
            if entity.source_entity_ids
            else f"symbol:{sorted(entity.symbols)[0]}"
            if entity.symbols
            else f"name:{normalize_name(canonical_name)}"
        )
        organization_ids[entity.internal_id] = stable_uuid("organization", stable_key)
        canonical_names[entity.internal_id] = canonical_name

    asset_rows: list[dict] = []
    asset_ids_by_key: dict[tuple[int, str, str, str], str] = {}
    for key, asset in sorted(assets.items(), key=lambda item: item[0]):
        org_id = organization_ids[asset.entity_internal_id]
        stable_key = "|".join(
            [org_id, asset.primary_symbol or "", normalize_name(asset.canonical_name), asset.asset_class]
        )
        asset_id = stable_uuid("asset", stable_key)
        asset_ids_by_key[key] = asset_id
        asset_rows.append(
            _hashed(
                {
                    "id": asset_id,
                    "organization_id": org_id,
                    "canonical_name": asset.canonical_name,
                    "asset_class": asset.asset_class,
                    "primary_symbol": asset.primary_symbol,
                    "aliases": sorted(asset.aliases, key=lambda x: (normalize_name(x), x)),
                    "provenance": _dedupe_dicts(asset.provenance),
                }
            )
        )

    assets_by_org_symbol: dict[tuple[int, str], str] = {}
    for key, asset_id in asset_ids_by_key.items():
        if key[1]:
            assets_by_org_symbol[(key[0], key[1])] = asset_id

    explicit_history_symbols: set[tuple[int, str]] = set()
    for mapping in sorted(
        ticker_history,
        key=lambda row: (
            str(row.get("disclosed_symbol")),
            str(row.get("valid_from") or ""),
            str(row.get("valid_to") or "9999-12-31"),
        ),
    ):
        disclosed = _symbol(mapping.get("disclosed_symbol"))
        market_symbol = _symbol(mapping.get("market_symbol"))
        candidates = registry.by_symbol.get(market_symbol or "", set())
        if not disclosed or not market_symbol or len(candidates) != 1:
            registry.quality_issues.append(
                {
                    "issue_type": "unresolved_ticker_history",
                    "severity": "review",
                    "mapping": dict(mapping),
                    "candidate_internal_ids": sorted(candidates),
                    "source_id": "market_ticker_history",
                }
            )
            continue
        internal_id = next(iter(candidates))
        asset_id = assets_by_org_symbol.get((internal_id, market_symbol))
        if not asset_id:
            continue
        explicit_history_symbols.add((internal_id, disclosed))
        ticker_rows.append(
            {
                "id": stable_uuid(
                    "ticker_history",
                    "|".join(
                        [
                            asset_id,
                            disclosed,
                            str(mapping.get("valid_from") or ""),
                            str(mapping.get("valid_to") or ""),
                        ]
                    ),
                ),
                "asset_id": asset_id,
                "organization_id": organization_ids[internal_id],
                "symbol": disclosed,
                "market_symbol": market_symbol,
                "exchange": None,
                "mic": None,
                "currency_code": None,
                "valid_from": mapping.get("valid_from"),
                "valid_to": mapping.get("valid_to"),
                "date_precision": "source_bounded",
                "is_primary": mapping.get("valid_to") is None,
                "change_type": mapping.get("change_type"),
                "provenance": [
                    _source_ref(
                        "market_ticker_history",
                        record_id=f"{disclosed}:{mapping.get('valid_from') or 'open'}",
                    )
                ],
            }
        )

    for entity in registry.entities:
        org_id = organization_ids[entity.internal_id]
        for symbol in sorted(entity.symbols):
            if (entity.internal_id, symbol) in explicit_history_symbols:
                continue
            asset_id = assets_by_org_symbol.get((entity.internal_id, symbol))
            if not asset_id:
                continue
            exchanges = sorted(
                {
                    exchange
                    for company in companies.values()
                    if symbol in company["tickers"]
                    for exchange in company["exchanges"]
                }
            )
            ticker_rows.append(
                {
                    "id": stable_uuid("ticker_history", f"{asset_id}|{symbol}|undated"),
                    "asset_id": asset_id,
                    "organization_id": org_id,
                    "symbol": symbol,
                    "market_symbol": symbol,
                    "exchange": exchanges[0] if len(exchanges) == 1 else None,
                    "mic": None,
                    "currency_code": None,
                    "valid_from": None,
                    "valid_to": None,
                    "date_precision": "undated_source_observation",
                    "is_primary": True,
                    "change_type": "source_observation",
                    "provenance": [
                        _source_ref(
                            "market_prices"
                            if symbol in (market_prices.get("ticker_reference") or {})
                            else "sec_filing_events",
                            record_id=f"ticker:{symbol}",
                        )
                    ],
                }
            )

    ticker_rows = [_hashed(row) for row in sorted(ticker_rows, key=lambda x: x["id"])]

    organizations: list[dict] = []
    sector_catalog: dict[tuple[str, str], dict] = {}
    for entity in registry.entities:
        org_id = organization_ids[entity.internal_id]
        canonical_name = canonical_names[entity.internal_id]
        aliases = []
        for row in entity.aliases.values():
            aliases.append(
                _hashed(
                    {
                        "id": stable_uuid(
                            "organization_alias",
                            f"{org_id}|{row['normalized_alias']}|{row['alias_type']}",
                        ),
                        "alias": row["alias"],
                        "normalized_alias": row["normalized_alias"],
                        "alias_type": row["alias_type"],
                        "confidence": row["confidence"],
                        "occurrence_count": row["occurrence_count"] or None,
                        "source_datasets": sorted(row["source_datasets"]),
                        "sample_transaction_ids": sorted(row["sample_transaction_ids"])[:5],
                        "provenance": _dedupe_dicts(row["provenance"]),
                    }
                )
            )
        identifiers = []
        for row in entity.identifiers.values():
            identifiers.append(
                _hashed(
                    {
                        "id": stable_uuid(
                            "organization_identifier",
                            f"{row['scheme']}|{row['value']}",
                        ),
                        "scheme": row["scheme"],
                        "value": row["value"],
                        "is_primary": row["is_primary"],
                        "valid_from": None,
                        "valid_to": None,
                        "provenance": _dedupe_dicts(row["provenance"]),
                    }
                )
            )
        sectors = []
        for row in entity.sectors.values():
            sector_key = (row["taxonomy"], row["code"])
            sector_id = stable_uuid("sector", "|".join(sector_key))
            catalog = sector_catalog.setdefault(
                sector_key,
                {
                    "id": sector_id,
                    "taxonomy": row["taxonomy"],
                    "code": row["code"],
                    "name": row["name"],
                    "provenance": [],
                },
            )
            catalog["provenance"].extend(row["provenance"])
            sectors.append(
                _hashed(
                    {
                        "sector_id": sector_id,
                        "valid_from": None,
                        "valid_to": None,
                        "is_primary": row["is_primary"],
                        "confidence": row["confidence"],
                        "provenance": _dedupe_dicts(row["provenance"]),
                    }
                )
            )
        org_type = sorted(entity.organization_types, key=lambda x: (-x[0], x[1]))[0][1]
        issuer = None
        if org_type in {"company", "fund"}:
            issuer = {
                "canonical_name": canonical_name,
                "cik": sorted(entity.ciks)[0] if entity.ciks else None,
                "lei": None,
                "identifier_status": "source_backed" if entity.ciks else "no_cik_in_sources",
            }
        organizations.append(
            _hashed(
                {
                    "id": org_id,
                    "canonical_key": (
                        f"sec-cik:{sorted(entity.ciks)[0]}"
                        if entity.ciks
                        else f"source-entity:{sorted(entity.source_entity_ids)[0]}"
                        if entity.source_entity_ids
                        else f"ticker:{sorted(entity.symbols)[0]}"
                        if entity.symbols
                        else f"name:{normalize_name(canonical_name)}"
                    ),
                    "canonical_name": canonical_name,
                    "normalized_name": normalize_name(canonical_name),
                    "organization_type": org_type,
                    "country_code": None,
                    "status": "unknown",
                    "issuer": issuer,
                    "aliases": sorted(aliases, key=lambda x: x["id"]),
                    "identifiers": sorted(identifiers, key=lambda x: x["id"]),
                    "sector_assignments": sorted(sectors, key=lambda x: x["sector_id"]),
                    "source_ids": sorted(entity.source_ids),
                }
            )
        )

    sectors = [
        _hashed({**row, "provenance": _dedupe_dicts(row["provenance"])})
        for _, row in sorted(sector_catalog.items())
    ]

    quality_issues = []
    for issue in registry.quality_issues:
        row = dict(issue)
        candidates = row.pop("candidate_internal_ids", [])
        if candidates:
            row["candidate_organization_ids"] = [
                organization_ids[item] for item in candidates if item in organization_ids
            ]
        identity = stable_hash(row)
        quality_issues.append(
            _hashed({"id": stable_uuid("entity_quality_issue", identity), **row})
        )
    quality_issues.sort(key=lambda row: row["id"])

    snapshots = sorted(
        (_hashed(dict(row)) for row in source_snapshots), key=lambda row: row["source_id"]
    )
    source_ids = {row["source_id"] for row in snapshots}
    referenced_source_ids = {
        ref["source_id"]
        for organization in organizations
        for alias in organization["aliases"]
        for ref in alias["provenance"]
    }
    missing_source_ids = sorted(referenced_source_ids - source_ids)
    if missing_source_ids:
        raise ValueError(f"Missing source snapshots for provenance: {missing_source_ids}")

    issue_counts = Counter(row["issue_type"] for row in quality_issues)
    dataset = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _source_date(source_snapshots),
        "context_label": (
            "Canonical entity reference compiled from source-backed CivicLedger context. "
            "Unresolved or ambiguous labels are retained for review; no identifier, "
            "ownership relationship, or effective date is inferred."
        ),
        "methodology": {
            "identity_resolution": (
                "Deterministic exact matching on SEC CIK, source entity ID, unique supported "
                "ticker, or exact normalized issuer name. Fuzzy matching is disabled."
            ),
            "ticker_dates": (
                "Only explicit source-checked effective ranges receive dates; all other "
                "ticker observations remain undated."
            ),
            "relationship_policy": (
                "Parent and subsidiary relationships require an explicit source assertion. "
                "Fund-family, partner, sector, and benchmark labels are not ownership evidence."
            ),
            "quality_policy": (
                "Unsupported and multiply matched labels remain review issues and do not create links."
            ),
        },
        "source_snapshots": snapshots,
        "summary": {
            "organization_count": len(organizations),
            "issuer_count": sum(1 for row in organizations if row["issuer"] is not None),
            "asset_count": len(asset_rows),
            "alias_count": sum(len(row["aliases"]) for row in organizations),
            "identifier_count": sum(len(row["identifiers"]) for row in organizations),
            "sector_count": len(sectors),
            "ticker_history_count": len(ticker_rows),
            "dated_ticker_history_count": sum(
                1 for row in ticker_rows if row["date_precision"] == "source_bounded"
            ),
            "relationship_count": 0,
            "quality_issue_count": len(quality_issues),
            "quality_issue_counts": dict(sorted(issue_counts.items())),
            "unlinked_disclosure_label_occurrence_count": unlinked_without_ticker,
        },
        "organizations": sorted(organizations, key=lambda row: row["id"]),
        "assets": sorted(asset_rows, key=lambda row: row["id"]),
        "sectors": sorted(sectors, key=lambda row: row["id"]),
        "ticker_histories": ticker_rows,
        "relationships": [],
        "quality_issues": quality_issues,
    }
    dataset["dataset_hash"] = stable_hash(dataset)
    return dataset
