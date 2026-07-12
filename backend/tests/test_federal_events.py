import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import scripts.build_federal_events_dataset as federal_events_module  # noqa: E402
from scripts.build_federal_events_dataset import (  # noqa: E402
    SupremeCourtOpinionParser,
    build_dataset,
    classify,
    deduplicate_federal_register_events,
    executive_order_event,
    federal_register_agency_event,
    fetch_federal_register_agency_documents,
    law_event,
    select_balanced_federal_register_events,
    supreme_court_event,
)


def federal_register_row(**overrides):
    row = {
        "document_number": "2024-01234",
        "title": "Cybersecurity Risk Management for Financial Markets",
        "type": "Rule",
        "subtype": "Final Rule",
        "publication_date": "2024-02-01",
        "effective_on": "2024-03-04",
        "html_url": "https://www.federalregister.gov/d/2024-01234",
        "pdf_url": "https://www.govinfo.gov/content/pkg/FR-2024-02-01/pdf/2024-01234.pdf",
        "abstract": "The rule updates cyber risk controls for regulated financial institutions.",
        "action": "Final rule.",
        "agencies": [
            {
                "id": 123,
                "name": "Example Markets Commission",
                "raw_name": "EXAMPLE MARKETS COMMISSION",
                "slug": "example-markets-commission",
                "url": "https://www.federalregister.gov/agencies/example-markets-commission",
            }
        ],
        "docket_ids": ["Docket No. EMC-2024-01"],
        "regulation_id_numbers": ["1234-AB56"],
        "citation": "89 FR 1234",
        "topics": ["Cybersecurity", "Securities"],
        "significant": True,
        "_source_query_ids": ["federal-register-significant-2024-rule"],
        "_source_record_sha256": "a" * 64,
    }
    row.update(overrides)
    return row


def test_market_topic_classifier_is_specific_and_explainable():
    result = classify("Semiconductor Manufacturing and Supply Chain Investment Act")
    assert result is not None
    assert {"technology", "industry_trade"} <= set(result["market_topic_ids"])
    assert "XLK" in result["ticker_scope"]
    assert classify("Naming a Post Office for a Local Resident") is None


def test_law_and_executive_order_events_preserve_official_sources():
    law = law_event(
        {
            "congress": 117,
            "type": "HR",
            "number": "1",
            "title": "Semiconductor Manufacturing Investment Act",
            "latestAction": {"actionDate": "2022-08-09", "text": "Became Public Law No: 117-1."},
            "laws": [{"number": "117-1", "type": "Public Law"}],
        }
    )
    order = executive_order_event(
        {
            "executive_order_number": "14017",
            "title": "America's Supply Chains",
            "signing_date": "2021-02-24",
            "publication_date": "2021-03-01",
            "html_url": "https://www.federalregister.gov/example",
            "abstract": None,
        }
    )

    assert law["source_tier"] == "official"
    assert law["sources"][0].startswith("https://www.congress.gov/")
    assert order["source_tier"] == "official"
    assert order["event_type"] == "executive_order"


def test_supreme_court_table_parser_and_event_keep_docket_evidence():
    parser = SupremeCourtOpinionParser()
    parser.feed(
        """
        <table><tr><td>15</td><td>2/26/25</td><td>23-900</td>
        <td><a href='/opinions/24pdf/example.pdf' title='The Court decided a securities dispute.'>
        Example Corp. v. United States</a></td><td>EK</td><td>604 U.S. 321</td></tr></table>
        """
    )
    assert len(parser.rows) == 1
    row = parser.rows[0]
    event = supreme_court_event(
        {
            "term_year": 2024,
            "release_number": row[0]["text"],
            "decision_date": "2025-02-26",
            "docket_number": row[2]["text"],
            "case_name": row[3]["text"],
            "synopsis": row[3]["title"],
            "opinion_url": "https://www.supremecourt.gov/opinions/24pdf/example.pdf",
            "source_page_url": "https://www.supremecourt.gov/opinions/slipopinion/24",
            "citation": row[5]["text"],
        }
    )

    assert event["event_type"] == "court_decision"
    assert event["docket_number"] == "23-900"
    assert event["branch_scope"] == ["Judicial"]
    assert event["sources"][0].endswith("example.pdf")


def test_significant_agency_event_preserves_source_dates_agencies_and_identifiers():
    event = federal_register_agency_event(federal_register_row())

    assert event["event_type"] == "agency_rule"
    assert event["announcement_date"] == "2024-02-01"
    assert event["effective_date"] == "2024-03-04"
    assert event["date"] == "2024-02-01"
    assert event["agency_names"] == ["Example Markets Commission"]
    assert event["docket_ids"] == ["Docket No. EMC-2024-01"]
    assert event["regulation_id_numbers"] == ["1234-AB56"]
    assert event["source_record_sha256"] == "a" * 64
    assert event["source_query_ids"] == ["federal-register-significant-2024-rule"]
    assert {item["field"] for item in event["market_relevance_evidence"]} >= {"title", "topics"}
    assert event["market_relevance"] == "significant_document_official_text_keyword_match"


def test_agency_event_requires_source_significance_and_supportable_market_classification():
    assert federal_register_agency_event(federal_register_row(significant=False)) is None
    assert (
        federal_register_agency_event(
            federal_register_row(
                title="Public Meeting Announcement",
                abstract="The agency announces a meeting.",
                topics=["Administrative practice and procedure"],
            )
        )
        is None
    )


def test_source_aware_deduplication_is_order_independent_and_keeps_distinct_documents():
    first = federal_register_agency_event(federal_register_row())
    repeated = federal_register_agency_event(
        federal_register_row(
            _source_query_ids=["federal-register-significant-2024-notice"],
            _source_record_sha256="b" * 64,
        )
    )
    distinct = federal_register_agency_event(
        federal_register_row(
            document_number="2024-05678",
            _source_record_sha256="c" * 64,
        )
    )

    forward = deduplicate_federal_register_events([first, repeated, distinct])
    reverse = deduplicate_federal_register_events([distinct, repeated, first])

    assert json.dumps(forward, sort_keys=True) == json.dumps(reverse, sort_keys=True)
    assert len(forward) == 2
    merged = next(event for event in forward if event["source_record_id"] == "federal-register:2024-01234")
    assert merged["source_query_ids"] == [
        "federal-register-significant-2024-notice",
        "federal-register-significant-2024-rule",
    ]
    assert merged["source_record_hashes"] == ["a" * 64, "b" * 64]


def test_balanced_selection_applies_the_same_quota_to_each_year_and_type():
    events = []
    for year in (2009, 2024):
        events.append(
            federal_register_agency_event(
                federal_register_row(
                    document_number=f"{year}-10001",
                    publication_date=f"{year}-02-01",
                    effective_on=f"{year}-03-01",
                    _source_record_sha256=str(year) * 16,
                )
            )
        )
        events.append(
            federal_register_agency_event(
                federal_register_row(
                    document_number=f"{year}-10002",
                    title="Administrative Procedure Update",
                    publication_date=f"{year}-04-01",
                    effective_on=f"{year}-05-01",
                    abstract="The update affects financial markets and securities reporting.",
                    topics=[],
                    _source_record_sha256=(str(year) + "b") * 13,
                )
            )
        )
        events.append(
            federal_register_agency_event(
                federal_register_row(
                    document_number=f"{year}-20001",
                    type="Notice",
                    publication_date=f"{year}-06-01",
                    effective_on=None,
                    _source_record_sha256=(str(year) + "c") * 13,
                )
            )
        )

    selected = select_balanced_federal_register_events(events, limits={"Rule": 1, "Notice": 1})

    assert len(selected) == 4
    assert {event["selection_bucket"] for event in selected} == {
        "2009:notice",
        "2009:rule",
        "2024:notice",
        "2024:rule",
    }
    selected_rules = [event for event in selected if event["event_type"] == "agency_rule"]
    assert all("10001" in event["id"] for event in selected_rules)
    assert all(event["selection_bucket_limit"] == 1 for event in selected)


def test_federal_register_fetch_records_queries_and_hashes_without_live_network(monkeypatch):
    requested_urls = []

    class FakeResponse:
        def __init__(self, content):
            self.content = content

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return self.content

    def fake_urlopen(request, timeout):
        assert timeout == 90
        requested_urls.append(request.full_url)
        query = parse_qs(urlparse(request.full_url).query)
        api_type = query["conditions[type][]"][0]
        row = federal_register_row(
            document_number=f"2009-{api_type}",
            type={"NOTICE": "Notice", "RULE": "Rule"}[api_type],
            publication_date="2009-02-01",
            effective_on=None,
        )
        row = {key: value for key, value in row.items() if not key.startswith("_")}
        content = json.dumps(
            {"count": 1, "results": [row], "next_page_url": None},
            sort_keys=True,
        ).encode()
        return FakeResponse(content)

    monkeypatch.setattr(federal_events_module, "urlopen", fake_urlopen)
    rows, snapshots = fetch_federal_register_agency_documents("2009-01-20", "2009-12-31")

    assert len(requested_urls) == 2
    assert len(rows) == 2
    assert len(snapshots) == 2
    assert {snapshot["document_type"] for snapshot in snapshots} == {"Notice", "Rule"}
    assert all(snapshot["query_conditions"]["significant"] is True for snapshot in snapshots)
    assert all(snapshot["fetched_result_count"] == 1 for snapshot in snapshots)
    assert all(len(snapshot["response_set_sha256"]) == 64 for snapshot in snapshots)
    assert all(len(row["_source_record_sha256"]) == 64 for row in rows)


def test_dataset_integrates_agency_events_and_query_selection_counts_without_network(monkeypatch):
    query_id = "federal-register-significant-2024-rule"
    row = federal_register_row()
    snapshot = {
        "id": query_id,
        "year": 2024,
        "document_type": "Rule",
        "query_conditions": {"significant": True},
        "reported_result_count": 1,
        "fetched_result_count": 1,
        "truncated": False,
        "page_snapshots": [{"response_sha256": "d" * 64}],
        "response_set_sha256": "e" * 64,
    }

    class FakeCongressClient:
        def __init__(self, api_key):
            assert api_key == "test-key"

        def laws_by_congress(self, congress):
            return []

    monkeypatch.setattr(federal_events_module, "CongressGovClient", FakeCongressClient)
    monkeypatch.setattr(
        federal_events_module,
        "fetch_executive_orders",
        lambda start, end: ([], "f" * 64),
    )
    monkeypatch.setattr(
        federal_events_module,
        "fetch_federal_register_agency_documents",
        lambda start, end: ([row], [snapshot]),
    )
    monkeypatch.setattr(
        federal_events_module,
        "fetch_supreme_court_opinions",
        lambda start, end: ([], []),
    )

    dataset = build_dataset("test-key", "2024-01-01", "2024-12-31")

    assert dataset["schema_version"] == "federal-market-events-v2"
    assert dataset["summary"]["selected_federal_register_agency_document_count"] == 1
    assert dataset["summary"]["counts_by_type"] == {"agency_rule": 1}
    source = next(
        source
        for source in dataset["sources"]
        if source["id"] == "federal-register-significant-agency-documents"
    )
    assert source["query_snapshots"][0]["classified_result_count"] == 1
    assert source["query_snapshots"][0]["selected_result_count"] == 1
    assert "not a causal relationship" in dataset["context_label"]
