#!/usr/bin/env python3
"""Build source-backed market-relevant federal law and executive-order events."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.congress_sources import CongressGovClient  # noqa: E402


OUTPUT = ROOT / "data" / "context" / "federal_events.json"
FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/documents.json"
SUPREME_COURT_TERM_URL = "https://www.supremecourt.gov/opinions/slipopinion/{term}"
USER_AGENT = "CivicLedger federal event research/0.1 (+https://github.com/dtrezise/CivicLedger)"
CONGRESSES = list(range(111, 120))

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
    classification = classify(f"{row['case_name']} {row.get('synopsis') or ''}")
    if not classification:
        return None
    stable_docket = re.sub(r"[^a-z0-9]+", "-", row["docket_number"].lower()).strip("-")
    return {
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
    opinions, supreme_court_snapshots = fetch_supreme_court_opinions(start_date, end_date)
    court_decisions = [event for row in opinions if (event := supreme_court_event(row))]
    events = {event["id"]: event for event in [*laws, *executive_orders, *court_decisions]}
    sorted_events = sorted(events.values(), key=lambda event: (event["date"], event["id"]))
    return {
        "schema_version": "federal-market-events-v1",
        "generated_at": date.today().isoformat(),
        "scope": {
            "start_date": start_date,
            "end_date": end_date,
            "congresses": CONGRESSES,
            "selection_method": "Market-relevant title and official-summary keyword taxonomy v1",
            "structured_supreme_court_term_range": (
                [2017, supreme_court_snapshots[-1]["term_year"]] if supreme_court_snapshots else []
            ),
            "supreme_court_pre_2017_status": "official_bound_volume_backfill_pending",
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
                "id": "supreme-court-slip-opinions",
                "url": SUPREME_COURT_TERM_URL,
                "source_tier": "official",
                "term_snapshots": supreme_court_snapshots,
            },
        ],
        "summary": {
            "raw_public_law_count": raw_law_count,
            "raw_executive_order_count": len(orders),
            "raw_supreme_court_opinion_count": len(opinions),
            "selected_public_law_count": len(laws),
            "selected_executive_order_count": len(executive_orders),
            "selected_supreme_court_opinion_count": len(court_decisions),
            "event_count": len(sorted_events),
            "counts_by_type": dict(sorted(Counter(event["event_type"] for event in sorted_events).items())),
            "counts_by_topic": dict(
                sorted(Counter(topic for event in sorted_events for topic in event["market_topic_ids"]).items())
            ),
        },
        "events": sorted_events,
        "context_label": (
            "Official-source public laws, executive orders, and Supreme Court opinions selected by a disclosed "
            "market-topic title and official-summary taxonomy. "
            "Selection indicates possible context, not a relationship to any trade."
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
