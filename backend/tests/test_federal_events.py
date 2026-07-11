import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.build_federal_events_dataset import (  # noqa: E402
    SupremeCourtOpinionParser,
    classify,
    executive_order_event,
    law_event,
    supreme_court_event,
)


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
