#!/usr/bin/env python3
"""Build source-backed market-relevant federal law and executive-order events."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.congress_sources import CongressGovClient  # noqa: E402
from app.services.supreme_court_historical import historical_decisions_for_range  # noqa: E402


OUTPUT = ROOT / "data" / "context" / "federal_events.json"
SUPREME_COURT_HISTORICAL = ROOT / "data" / "context" / "supreme_court_historical_decisions.json"
FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/documents.json"
SUPREME_COURT_TERM_URL = "https://www.supremecourt.gov/opinions/slipopinion/{term}"
USER_AGENT = "CivicLedger federal event research/0.1 (+https://github.com/dtrezise/CivicLedger)"
CONGRESSES = list(range(111, 120))
FEDERAL_REGISTER_AGENCY_DOCUMENT_TYPES = {
    "NOTICE": "Notice",
    "RULE": "Rule",
}
FEDERAL_REGISTER_YEAR_TYPE_LIMITS = {
    "Notice": 12,
    "Rule": 24,
}
FEDERAL_REGISTER_MAX_PAGES_PER_QUERY = 5
FEDERAL_REGISTER_FIELDS = [
    "document_number",
    "title",
    "type",
    "subtype",
    "publication_date",
    "effective_on",
    "html_url",
    "pdf_url",
    "abstract",
    "action",
    "agencies",
    "docket_ids",
    "regulation_id_numbers",
    "citation",
    "topics",
    "significant",
]

RULES = [
    {
        "id": "financial_markets",
        "pattern": r"\b(bank|banking|financial|finance|securit(?:y|ies)|investment|capital market|credit|mortgage|insurance|digital asset|cryptocurrency|payment system)\b",
        "sectors": ["Financials"],
        "jurisdictions": ["banking", "financial markets", "securities", "treasury"],
        "tickers": ["XLF", "JPM", "V"],
        "assets": ["equity", "etf", "fixed_income", "crypto"],
    },
    {
        "id": "technology",
        "pattern": r"\b(artificial intelligence|cyber|semiconductor|microchip|technology|telecommunication|broadband|internet|data privacy|quantum)\b",
        "sectors": ["Information Technology", "Communication Services"],
        "jurisdictions": ["technology", "commerce", "cybersecurity", "communications"],
        "tickers": ["XLK", "QQQ", "NVDA", "MSFT", "GOOGL", "META"],
        "assets": ["equity", "etf"],
    },
    {
        "id": "energy_environment",
        "pattern": r"\b(energy|oil|gas|coal|nuclear|electric|climate|environment|emission|renewable|pipeline|mineral)\b",
        "sectors": ["Energy", "Utilities"],
        "jurisdictions": ["energy", "environment", "epa", "interior"],
        "tickers": ["XLE", "SPY"],
        "assets": ["equity", "etf", "fixed_income"],
    },
    {
        "id": "health",
        "pattern": r"\b(health|medical|medicare|medicaid|drug|pharma|hospital|public health|vaccine)\b",
        "sectors": ["Health Care"],
        "jurisdictions": ["health", "hhs", "medicare", "medicaid"],
        "tickers": ["XLV", "JNJ"],
        "assets": ["equity", "etf"],
    },
    {
        "id": "industry_trade",
        "pattern": r"\b(tariff|trade|import|export|supply chains?|manufactur|procurement|industrial|critical infrastructure)\b",
        "sectors": ["Industrials", "Broad Market"],
        "jurisdictions": ["trade", "commerce", "supply chain", "manufacturing"],
        "tickers": ["XLI", "SPY", "DIA"],
        "assets": ["equity", "etf"],
    },
    {
        "id": "transportation_infrastructure",
        "pattern": r"\b(infrastructure|transportation|highway|rail|aviation|airport|maritime|shipping|transit)\b",
        "sectors": ["Industrials"],
        "jurisdictions": ["transportation", "infrastructure"],
        "tickers": ["XLI", "DIA"],
        "assets": ["equity", "etf", "fixed_income"],
    },
    {
        "id": "defense_space",
        "pattern": r"\b(defense|military|armed forces|national security|aerospace|space program|space exploration)\b",
        "sectors": ["Industrials"],
        "jurisdictions": ["defense", "armed services", "national security"],
        "tickers": ["XLI", "DIA"],
        "assets": ["equity", "etf"],
    },
    {
        "id": "fiscal",
        "pattern": r"\b(tax|budget|appropriation|fiscal|debt limit|debt ceiling|economic relief|emergency relief|stimulus)\b",
        "sectors": ["Broad Market", "Fixed Income"],
        "jurisdictions": ["tax", "budget", "appropriations", "treasury"],
        "tickers": ["SPY", "DIA", "BND"],
        "assets": ["equity", "etf", "fixed_income"],
    },
    {
        "id": "agriculture",
        "pattern": r"\b(agriculture|farm|food supply|crop|livestock)\b",
        "sectors": ["Consumer Staples", "Industrials"],
        "jurisdictions": ["agriculture", "food"],
        "tickers": ["SPY", "XLI"],
        "assets": ["equity", "etf", "commodity"],
    },
]


def classify(title: str) -> dict | None:
    matched = [rule for rule in RULES if re.search(rule["pattern"], title, re.IGNORECASE)]
    if not matched:
        return None
    return {
        "market_topic_ids": [rule["id"] for rule in matched],
        "sector_scope": sorted({value for rule in matched for value in rule["sectors"]}),
        "jurisdiction_scope": sorted({value for rule in matched for value in rule["jurisdictions"]}),
        "ticker_scope": sorted({value for rule in matched for value in rule["tickers"]}),
        "asset_scope": sorted({value for rule in matched for value in rule["assets"]}),
    }


def _canonical_hash(value: object) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _federal_register_query_id(year: int, document_type: str) -> str:
    return f"federal-register-significant-{year}-{document_type.lower()}"


def _federal_register_classification(row: dict) -> dict | None:
    evidence = []
    classifications = []
    fields = [
        ("title", row.get("title") or ""),
        ("topics", " ".join(str(value) for value in row.get("topics") or [])),
        ("action", row.get("action") or ""),
        ("abstract", row.get("abstract") or ""),
    ]
    for field, text in fields:
        classification = classify(text)
        if not classification:
            continue
        classifications.append(classification)
        evidence.append(
            {
                "field": field,
                "market_topic_ids": classification["market_topic_ids"],
            }
        )
    if not classifications:
        return None
    return {
        "market_topic_ids": sorted(
            {value for classification in classifications for value in classification["market_topic_ids"]}
        ),
        "sector_scope": sorted(
            {value for classification in classifications for value in classification["sector_scope"]}
        ),
        "jurisdiction_scope": sorted(
            {value for classification in classifications for value in classification["jurisdiction_scope"]}
        ),
        "ticker_scope": sorted(
            {value for classification in classifications for value in classification["ticker_scope"]}
        ),
        "asset_scope": sorted(
            {value for classification in classifications for value in classification["asset_scope"]}
        ),
        "market_relevance_evidence": evidence,
    }


def _agency_details(row: dict) -> list[dict]:
    agencies = []
    for agency in row.get("agencies") or []:
        if not isinstance(agency, dict):
            continue
        name = agency.get("name") or agency.get("raw_name")
        if not name:
            continue
        agencies.append(
            {
                key: agency.get(key)
                for key in ("id", "name", "raw_name", "parent_id", "slug", "url")
                if agency.get(key) is not None
            }
        )
    return sorted(
        agencies,
        key=lambda agency: (
            agency.get("name") or agency.get("raw_name") or "",
            agency.get("id") or 0,
        ),
    )


def federal_register_agency_event(row: dict) -> dict | None:
    """Convert one significant agency rule or notice into neutral market context."""

    document_number = str(row.get("document_number") or "").strip()
    publication_date = row.get("publication_date")
    document_type = row.get("type")
    title = str(row.get("title") or "").strip()
    if (
        not document_number
        or not publication_date
        or document_type not in set(FEDERAL_REGISTER_AGENCY_DOCUMENT_TYPES.values())
        or row.get("significant") is not True
        or not title
    ):
        return None
    classification = _federal_register_classification(row)
    if not classification:
        return None
    agencies = _agency_details(row)
    agency_names = sorted(
        {
            agency.get("name") or agency.get("raw_name")
            for agency in agencies
            if agency.get("name") or agency.get("raw_name")
        }
    )
    sources = sorted({url for url in (row.get("html_url"), row.get("pdf_url")) if url})
    source_query_ids = sorted(set(row.get("_source_query_ids") or []))
    source_record_sha256 = row.get("_source_record_sha256") or _canonical_hash(
        {field: row.get(field) for field in FEDERAL_REGISTER_FIELDS}
    )
    effective_date = row.get("effective_on")
    return {
        "id": f"federal-register-agency-{document_number.lower()}",
        "date": publication_date,
        "announcement_date": publication_date,
        "effective_date": effective_date,
        "publication_date": publication_date,
        "label": title,
        "event_type": "agency_rule" if document_type == "Rule" else "agency_notice",
        "description": row.get("abstract") or title,
        "source": "Federal Register",
        "sources": sources,
        "source_tier": "official",
        "editor_status": "source_ingested",
        "branch_scope": ["Executive"],
        "market_relevance": "significant_document_official_text_keyword_match",
        "significant": True,
        "federal_register_document_number": document_number,
        "federal_register_document_type": document_type,
        "federal_register_document_subtype": row.get("subtype"),
        "federal_register_citation": row.get("citation"),
        "agency_names": agency_names,
        "agency_details": agencies,
        "docket_ids": sorted(set(row.get("docket_ids") or [])),
        "regulation_id_numbers": sorted(set(row.get("regulation_id_numbers") or [])),
        "federal_register_action": row.get("action"),
        "federal_register_topics": sorted(set(row.get("topics") or [])),
        "source_record_id": f"federal-register:{document_number}",
        "source_record_sha256": source_record_sha256,
        "source_query_ids": source_query_ids,
        **classification,
    }


def _event_completeness(event: dict) -> tuple:
    return (
        sum(bool(event.get(field)) for field in ("effective_date", "federal_register_citation", "description")),
        len(event.get("agency_names") or []),
        len(event.get("docket_ids") or []),
        len(event.get("regulation_id_numbers") or []),
        len(event.get("market_relevance_evidence") or []),
        _canonical_hash(event),
    )


def deduplicate_federal_register_events(events: list[dict]) -> list[dict]:
    """Deduplicate repeated API rows by official source identity, never by title alone."""

    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        source_identity = event.get("source_record_id") or event.get("id")
        grouped[str(source_identity)].append(event)
    deduplicated = []
    for source_identity in sorted(grouped):
        candidates = grouped[source_identity]
        selected = dict(max(candidates, key=_event_completeness))
        for field in (
            "sources",
            "agency_names",
            "docket_ids",
            "regulation_id_numbers",
            "source_query_ids",
            "market_topic_ids",
            "sector_scope",
            "jurisdiction_scope",
            "ticker_scope",
            "asset_scope",
        ):
            selected[field] = sorted({value for candidate in candidates for value in candidate.get(field) or []})
        selected["source_record_hashes"] = sorted(
            {candidate.get("source_record_sha256") for candidate in candidates if candidate.get("source_record_sha256")}
        )
        evidence = {
            (item.get("field"), tuple(item.get("market_topic_ids") or [])): item
            for candidate in candidates
            for item in candidate.get("market_relevance_evidence") or []
        }
        selected["market_relevance_evidence"] = [evidence[key] for key in sorted(evidence)]
        deduplicated.append(selected)
    return sorted(deduplicated, key=lambda event: (event["date"], event["id"]))


def _selection_priority(event: dict) -> tuple:
    field_weights = {"title": 4, "topics": 3, "action": 2, "abstract": 1}
    evidence = event.get("market_relevance_evidence") or []
    strongest_evidence = max((field_weights.get(item.get("field"), 0) for item in evidence), default=0)
    return (
        strongest_evidence,
        len(evidence),
        len(event.get("market_topic_ids") or []),
        bool(event.get("regulation_id_numbers")),
        bool(event.get("docket_ids")),
        event["id"],
    )


def select_balanced_federal_register_events(
    events: list[dict],
    limits: dict[str, int] | None = None,
) -> list[dict]:
    """Apply independent annual quotas so recent publication volume cannot dominate."""

    if limits is None:
        limits = FEDERAL_REGISTER_YEAR_TYPE_LIMITS
    grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for event in deduplicate_federal_register_events(events):
        year = date.fromisoformat(event["publication_date"]).year
        grouped[(year, event["federal_register_document_type"])].append(event)
    selected = []
    for (year, document_type), candidates in sorted(grouped.items()):
        limit = max(0, int(limits.get(document_type, 0)))
        ranked = sorted(candidates, key=_selection_priority, reverse=True)
        for rank, event in enumerate(ranked[:limit], start=1):
            selected_event = dict(event)
            selected_event["selection_bucket"] = f"{year}:{document_type.lower()}"
            selected_event["selection_rank"] = rank
            selected_event["selection_bucket_limit"] = limit
            selected.append(selected_event)
    return sorted(selected, key=lambda event: (event["date"], event["id"]))


def fetch_federal_register_agency_documents(
    start_date: str,
    end_date: str,
) -> tuple[list[dict], list[dict]]:
    """Fetch significant final rules and notices in deterministic annual slices."""

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    documents = []
    query_snapshots = []
    for year in range(start.year, end.year + 1):
        query_start = max(start, date(year, 1, 1)).isoformat()
        query_end = min(end, date(year, 12, 31)).isoformat()
        for api_type, document_type in sorted(FEDERAL_REGISTER_AGENCY_DOCUMENT_TYPES.items()):
            query_id = _federal_register_query_id(year, document_type)
            query_conditions = {
                "significant": True,
                "type": api_type,
                "publication_date_gte": query_start,
                "publication_date_lte": query_end,
            }
            params = [
                ("conditions[type][]", api_type),
                ("conditions[significant]", "1"),
                ("conditions[publication_date][gte]", query_start),
                ("conditions[publication_date][lte]", query_end),
            ]
            params.extend(("fields[]", field) for field in FEDERAL_REGISTER_FIELDS)
            params.extend([("per_page", "1000"), ("order", "oldest")])
            next_url = f"{FEDERAL_REGISTER_API}?{urlencode(params)}"
            page_snapshots = []
            raw_result_count = 0
            reported_count = None
            page_number = 0
            while next_url and page_number < FEDERAL_REGISTER_MAX_PAGES_PER_QUERY:
                page_number += 1
                request = Request(next_url, headers={"User-Agent": USER_AGENT})
                with urlopen(request, timeout=90) as response:
                    content = response.read()
                payload = json.loads(content)
                rows = payload.get("results") or []
                reported_count = payload.get("count", reported_count)
                page_snapshots.append(
                    {
                        "page": page_number,
                        "url": next_url,
                        "response_sha256": hashlib.sha256(content).hexdigest(),
                        "result_count": len(rows),
                    }
                )
                for row in rows:
                    source_row = {field: row.get(field) for field in FEDERAL_REGISTER_FIELDS}
                    source_record_sha256 = _canonical_hash(source_row)
                    source_row["_source_query_ids"] = [query_id]
                    source_row["_source_record_sha256"] = source_record_sha256
                    documents.append(source_row)
                raw_result_count += len(rows)
                next_url = payload.get("next_page_url")
            query_snapshots.append(
                {
                    "id": query_id,
                    "year": year,
                    "document_type": document_type,
                    "query_conditions": query_conditions,
                    "reported_result_count": reported_count,
                    "fetched_result_count": raw_result_count,
                    "truncated": bool(next_url),
                    "page_snapshots": page_snapshots,
                    "response_set_sha256": _canonical_hash(
                        [snapshot["response_sha256"] for snapshot in page_snapshots]
                    ),
                }
            )
    return documents, query_snapshots


def fetch_executive_orders(start_date: str, end_date: str) -> tuple[list[dict], str]:
    fields = [
        "document_number",
        "title",
        "publication_date",
        "signing_date",
        "executive_order_number",
        "html_url",
        "abstract",
    ]
    params = [
        ("conditions[type][]", "PRESDOCU"),
        ("conditions[presidential_document_type][]", "executive_order"),
        ("conditions[publication_date][gte]", start_date),
    ]
    params.extend(("fields[]", field) for field in fields)
    params.extend([("per_page", "1000"), ("order", "oldest")])
    request = Request(f"{FEDERAL_REGISTER_API}?{urlencode(params)}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        content = response.read()
    payload = json.loads(content)
    by_number = {}
    for row in payload.get("results", []):
        signing_date = row.get("signing_date")
        number = row.get("executive_order_number")
        if not number or not signing_date or not start_date <= signing_date <= end_date:
            continue
        by_number.setdefault(number, row)
    return list(by_number.values()), hashlib.sha256(content).hexdigest()


class SupremeCourtOpinionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.current_row = None
        self.current_cell = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self.current_row = []
        elif tag == "td" and self.current_row is not None:
            self.current_cell = {"text": [], "href": None, "title": None}
        elif tag == "a" and self.current_cell is not None:
            self.current_cell["href"] = attributes.get("href")
            self.current_cell["title"] = attributes.get("title")

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.current_cell is not None and self.current_row is not None:
            self.current_cell["text"] = " ".join("".join(self.current_cell["text"]).split())
            self.current_row.append(self.current_cell)
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if len(self.current_row) >= 4 and str(self.current_row[0]["text"]).isdigit():
                self.rows.append(self.current_row)
            self.current_row = None
            self.current_cell = None


def fetch_supreme_court_opinions(
    start_date: str,
    end_date: str,
) -> tuple[list[dict], list[dict]]:
    start_year = date.fromisoformat(start_date).year
    end_value = date.fromisoformat(end_date)
    last_term_year = end_value.year if end_value.month >= 10 else end_value.year - 1
    opinions = []
    source_snapshots = []
    first_structured_term_year = max(start_year - 1, 2017)
    for term_year in range(first_structured_term_year, last_term_year + 1):
        term = str(term_year)[-2:]
        page_url = SUPREME_COURT_TERM_URL.format(term=term)
        request = Request(page_url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=90) as response:
            content = response.read()
        parser = SupremeCourtOpinionParser()
        parser.feed(content.decode("utf-8", errors="replace"))
        source_snapshots.append(
            {
                "term_year": term_year,
                "url": page_url,
                "response_sha256": hashlib.sha256(content).hexdigest(),
                "row_count": len(parser.rows),
            }
        )
        for cells in parser.rows:
            try:
                decision_date = datetime.strptime(cells[1]["text"], "%m/%d/%y").date().isoformat()
            except (ValueError, IndexError):
                continue
            if not start_date <= decision_date <= end_date:
                continue
            opinions.append(
                {
                    "term_year": term_year,
                    "release_number": cells[0]["text"],
                    "decision_date": decision_date,
                    "docket_number": cells[2]["text"],
                    "case_name": cells[3]["text"],
                    "synopsis": cells[3].get("title") or "",
                    "opinion_url": urljoin(page_url, cells[3].get("href") or ""),
                    "source_page_url": page_url,
                    "citation": cells[5]["text"] if len(cells) > 5 else None,
                }
            )
    return opinions, source_snapshots


def congress_url(row: dict) -> str:
    bill_type = str(row["type"]).lower()
    type_labels = {
        "hr": "house-bill",
        "s": "senate-bill",
        "hjres": "house-joint-resolution",
        "sjres": "senate-joint-resolution",
    }
    return f"https://www.congress.gov/bill/{row['congress']}th-congress/{type_labels.get(bill_type, bill_type)}/{row['number']}"


def law_event(row: dict) -> dict | None:
    title = row.get("title") or ""
    classification = classify(title)
    if not classification:
        return None
    action = row.get("latestAction") or {}
    action_date = action.get("actionDate")
    if not action_date:
        return None
    funding = bool(re.search(r"\b(appropriation|authorization|relief|investment|infrastructure|funding)\b", title, re.IGNORECASE))
    law_number = next((law.get("number") for law in row.get("laws", []) if law.get("type") == "Public Law"), None)
    return {
        "id": f"congress-law-{row['congress']}-{str(row['type']).lower()}-{row['number']}",
        "date": action_date,
        "announcement_date": action_date,
        "effective_date": action_date,
        "publication_date": action_date,
        "label": title,
        "event_type": "funding" if funding else "legislation",
        "description": f"{action.get('text') or 'Enacted as federal law'} {title}",
        "source": "Congress.gov",
        "sources": [congress_url(row)],
        "source_tier": "official",
        "editor_status": "source_ingested",
        "branch_scope": ["Legislative", "Executive"],
        "market_relevance": "title_keyword_match",
        "law_number": law_number,
        **classification,
    }


def executive_order_event(row: dict) -> dict | None:
    title = row.get("title") or ""
    classification = classify(title)
    if not classification:
        return None
    return {
        "id": f"federal-register-eo-{row['executive_order_number']}",
        "date": row["signing_date"],
        "announcement_date": row["signing_date"],
        "effective_date": row["signing_date"],
        "publication_date": row.get("publication_date"),
        "label": f"Executive Order {row['executive_order_number']}: {title}",
        "event_type": "executive_order",
        "description": row.get("abstract") or title,
        "source": "Federal Register",
        "sources": [row["html_url"]],
        "source_tier": "official",
        "editor_status": "source_ingested",
        "branch_scope": ["Executive"],
        "market_relevance": "title_keyword_match",
        "executive_order_number": row["executive_order_number"],
        **classification,
    }


def supreme_court_event(row: dict) -> dict | None:
    subject_terms = " ".join(row.get("subject_terms") or [])
    classification = classify(f"{row['case_name']} {row.get('synopsis') or ''} {subject_terms}")
    if not classification:
        return None
    identifier = row.get("docket_number") or row["release_number"]
    stable_docket = re.sub(r"[^a-z0-9]+", "-", identifier.lower()).strip("-")
    event = {
        "id": f"scotus-{row['term_year']}-{row['release_number']}-{stable_docket}",
        "date": row["decision_date"],
        "announcement_date": row["decision_date"],
        "effective_date": row["decision_date"],
        "publication_date": row["decision_date"],
        "label": row["case_name"],
        "event_type": "court_decision",
        "description": row.get("synopsis") or f"Supreme Court opinion in {row['case_name']}.",
        "source": "Supreme Court of the United States",
        "sources": [row["opinion_url"], row["source_page_url"]],
        "source_tier": "official",
        "editor_status": "source_ingested",
        "branch_scope": ["Judicial"],
        "market_relevance": "title_and_synopsis_keyword_match",
        "court": "Supreme Court of the United States",
        "term_year": row["term_year"],
        "docket_number": row["docket_number"],
        "citation": row.get("citation"),
        **classification,
    }
    if row.get("historical_provenance"):
        event["historical_provenance"] = row["historical_provenance"]
    return event


def build_dataset(api_key: str, start_date: str, end_date: str) -> dict:
    client = CongressGovClient(api_key=api_key)
    laws = []
    raw_law_count = 0
    for congress in CONGRESSES:
        rows = client.laws_by_congress(congress)
        raw_law_count += len(rows)
        laws.extend(event for row in rows if (event := law_event(row)))
    orders, federal_register_hash = fetch_executive_orders(start_date, end_date)
    executive_orders = [event for row in orders if (event := executive_order_event(row))]
    agency_documents, federal_register_agency_snapshots = fetch_federal_register_agency_documents(
        start_date,
        end_date,
    )
    classified_agency_events = deduplicate_federal_register_events(
        [event for row in agency_documents if (event := federal_register_agency_event(row))]
    )
    agency_events = select_balanced_federal_register_events(classified_agency_events)
    classified_by_query = Counter(
        query_id for event in classified_agency_events for query_id in event.get("source_query_ids") or []
    )
    selected_by_query = Counter(
        query_id for event in agency_events for query_id in event.get("source_query_ids") or []
    )
    for snapshot in federal_register_agency_snapshots:
        snapshot["classified_result_count"] = classified_by_query[snapshot["id"]]
        snapshot["selected_result_count"] = selected_by_query[snapshot["id"]]
    historical_opinions, historical_snapshot = historical_decisions_for_range(
        SUPREME_COURT_HISTORICAL,
        start_date,
        end_date,
    )
    slip_opinions, supreme_court_snapshots = fetch_supreme_court_opinions(start_date, end_date)
    opinions = [*historical_opinions, *slip_opinions]
    court_decisions = [event for row in opinions if (event := supreme_court_event(row))]
    events = {
        event["id"]: event
        for event in [*laws, *executive_orders, *agency_events, *court_decisions]
    }
    sorted_events = sorted(events.values(), key=lambda event: (event["date"], event["id"]))
    return {
        "schema_version": "federal-market-events-v2",
        "generated_at": date.today().isoformat(),
        "scope": {
            "start_date": start_date,
            "end_date": end_date,
            "congresses": CONGRESSES,
            "selection_method": "Market-relevant official text keyword taxonomy v2",
            "federal_register_agency_selection": {
                "source_filter": "Federal Register significant=true; final rules and notices only",
                "classification_fields": ["title", "topics", "action", "abstract"],
                "annual_type_limits": FEDERAL_REGISTER_YEAR_TYPE_LIMITS,
                "balancing_method": "Independent deterministic calendar-year and document-type quotas",
                "causal_interpretation": "None; inclusion identifies possible market context only",
            },
            "structured_supreme_court_term_range": (
                [
                    min(opinion["term_year"] for opinion in opinions),
                    max(opinion["term_year"] for opinion in opinions),
                ]
                if opinions
                else []
            ),
            "supreme_court_pre_2017_status": historical_snapshot["status"],
        },
        "sources": [
            {
                "id": "congress-gov-laws",
                "url": "https://api.congress.gov/v3/law/{congress}",
                "source_tier": "official",
            },
            {
                "id": "federal-register-executive-orders",
                "url": FEDERAL_REGISTER_API,
                "source_tier": "official",
                "response_sha256": federal_register_hash,
            },
            {
                "id": "federal-register-significant-agency-documents",
                "url": FEDERAL_REGISTER_API,
                "source_tier": "official",
                "document_types": sorted(FEDERAL_REGISTER_AGENCY_DOCUMENT_TYPES.values()),
                "query_snapshots": federal_register_agency_snapshots,
            },
            {
                "id": "supreme-court-us-reports-historical",
                "url": "https://www.supremecourt.gov/opinions/USReports.aspx",
                "source_tier": "official",
                "artifact_snapshot": historical_snapshot,
            },
            {
                "id": "supreme-court-slip-opinions",
                "url": SUPREME_COURT_TERM_URL,
                "source_tier": "official",
                "term_snapshots": supreme_court_snapshots,
            },
        ],
        "summary": {
            "raw_public_law_count": raw_law_count,
            "raw_executive_order_count": len(orders),
            "raw_federal_register_agency_document_count": len(agency_documents),
            "raw_supreme_court_opinion_count": len(opinions),
            "raw_historical_supreme_court_decision_count": len(historical_opinions),
            "raw_supreme_court_slip_opinion_count": len(slip_opinions),
            "selected_public_law_count": len(laws),
            "selected_executive_order_count": len(executive_orders),
            "classified_federal_register_agency_document_count": len(classified_agency_events),
            "selected_federal_register_agency_document_count": len(agency_events),
            "selected_federal_register_agency_documents_by_year": dict(
                sorted(Counter(event["publication_date"][:4] for event in agency_events).items())
            ),
            "selected_federal_register_agency_documents_by_type": dict(
                sorted(Counter(event["federal_register_document_type"] for event in agency_events).items())
            ),
            "selected_supreme_court_opinion_count": len(court_decisions),
            "event_count": len(sorted_events),
            "counts_by_type": dict(sorted(Counter(event["event_type"] for event in sorted_events).items())),
            "counts_by_topic": dict(
                sorted(Counter(topic for event in sorted_events for topic in event["market_topic_ids"]).items())
            ),
        },
        "events": sorted_events,
        "context_label": (
            "Official-source public laws, executive orders, significant agency rules and notices, and Supreme "
            "Court opinions selected by a disclosed market-topic taxonomy. Federal Register agency records are "
            "balanced with fixed annual type quotas. Selection indicates possible context, not a causal "
            "relationship to any trade."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=os.environ.get("CONGRESS_GOV_API_KEY"))
    parser.add_argument("--start", default="2009-01-20")
    parser.add_argument("--end", default=date.today().isoformat())
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("Set CONGRESS_GOV_API_KEY or pass --api-key.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(args.api_key, args.start, args.end), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
