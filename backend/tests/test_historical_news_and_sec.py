import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

from app.services.historical_news import (
    GdeltDocHistoricalNewsProvider,
    HistoricalNewsArticle,
    HistoricalNewsQuery,
    HistoricalNewsResult,
    ProviderUnavailableError as NewsProviderUnavailableError,
    parse_gdelt_articles,
)
from app.services.sec_edgar import (
    ProviderUnavailableError as SecProviderUnavailableError,
    RequestRateLimiter as SecRateLimiter,
    SecCompanyRequest,
    SecEdgarSubmissionsProvider,
    SecFiling,
    SecFilingResult,
    normalize_cik,
    parse_atom_filings,
    parse_submission_filings,
    sec_filing_index_url,
)


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.build_historical_news_context import build_dataset as build_news_dataset  # noqa: E402
from scripts.build_sec_filing_events import build_dataset as build_sec_dataset  # noqa: E402


class SpyRateLimiter:
    def __init__(self) -> None:
        self.wait_count = 0

    def wait(self) -> None:
        self.wait_count += 1


def test_gdelt_parser_normalizes_and_sorts_source_rows():
    articles = parse_gdelt_articles(
        {
            "articles": [
                {
                    "title": "  Later   headline ",
                    "url": "HTTPS://Example.com/later#fragment",
                    "seendate": "20240103T130405Z",
                    "domain": "Example.COM",
                    "language": "English",
                    "sourcecountry": "United States",
                },
                {
                    "title": "Earlier headline",
                    "url": "https://news.example/earlier",
                    "seendate": "20240102T010203Z",
                },
                {"title": "Missing URL"},
            ]
        }
    )

    assert [article.title for article in articles] == ["Earlier headline", "Later headline"]
    assert articles[0].published_at == "2024-01-02T01:02:03Z"
    assert articles[1].url == "https://example.com/later"
    assert articles[1].domain == "example.com"


def test_gdelt_adapter_is_keyless_rate_limited_and_cached(tmp_path):
    calls = []
    limiter = SpyRateLimiter()

    def transport(url, headers, timeout):
        calls.append((url, headers, timeout))
        return {
            "articles": [
                {
                    "title": "A filing was reported",
                    "url": "https://publisher.example/story",
                    "seendate": "20240201T120000Z",
                    "domain": "publisher.example",
                }
            ]
        }

    provider = GdeltDocHistoricalNewsProvider(
        cache_directory=tmp_path,
        transport=transport,
        rate_limiter=limiter,
    )
    query = HistoricalNewsQuery(
        query_id="issuer-news",
        query='"Example Corp"',
        start_date="2024-02-01",
        end_date="2024-02-02",
        max_records=25,
    )

    first = provider.search(query)
    second = provider.search(query)

    assert first.retrieval_status == "fetched"
    assert second.retrieval_status == "cache_hit"
    assert len(calls) == 1
    assert limiter.wait_count == 1
    parameters = parse_qs(urlsplit(calls[0][0]).query)
    assert parameters["mode"] == ["artlist"]
    assert parameters["startdatetime"] == ["20240201000000"]
    assert parameters["enddatetime"] == ["20240202235959"]
    assert "api_key" not in parameters
    assert calls[0][1]["User-Agent"].startswith("CivicLedger")


class FakeNewsProvider:
    provider_id = "fake-news"
    provider_name = "Fake News Provider"
    source_tier = "news_aggregator"
    documentation_url = "https://provider.example/docs"

    def search(self, query):
        return HistoricalNewsResult(
            articles=(
                HistoricalNewsArticle(
                    title="Issuer event",
                    url="https://publisher.example/issuer-event",
                    published_at="2024-02-02T10:30:00Z",
                    domain="publisher.example",
                    language="English",
                    source_country="United States",
                ),
            ),
            request_url=f"https://provider.example/search?q={query.query_id}",
            retrieval_status="fetched",
        )


def test_news_dataset_is_deterministic_source_attributed_and_review_gated():
    queries = [
        HistoricalNewsQuery("second", "Example", "2024-02-01", "2024-02-03"),
        HistoricalNewsQuery("first", '"Example Corp"', "2024-02-01", "2024-02-03"),
    ]

    forward = build_news_dataset(FakeNewsProvider(), queries, artifact_date="2024-02-03")
    reverse = build_news_dataset(FakeNewsProvider(), list(reversed(queries)), artifact_date="2024-02-03")

    assert json.dumps(forward, sort_keys=True) == json.dumps(reverse, sort_keys=True)
    assert forward["summary"]["event_count"] == 1
    event = forward["events"][0]
    assert event["matched_query_ids"] == ["first", "second"]
    assert event["review_required_before_publication"] is True
    assert event["public_production_event"] is False
    assert {source["role"] for source in event["sources"]} == {
        "article",
        "discovery_provider",
    }
    assert event["source_urls"][0] == "https://publisher.example/issuer-event"


def test_news_dataset_records_unavailable_provider_without_raising():
    class UnavailableNewsProvider(FakeNewsProvider):
        def search(self, query):
            raise NewsProviderUnavailableError("provider offline")

    query = HistoricalNewsQuery("offline", "Example", "2024-02-01", "2024-02-03")
    dataset = build_news_dataset(
        UnavailableNewsProvider(),
        [query],
        artifact_date="2024-02-03",
    )

    assert dataset["events"] == []
    assert dataset["coverage_report"]["offline"]["status"] == "unavailable"
    assert dataset["summary"]["public_production_event_count"] == 0


def _recent_submissions_payload():
    return {
        "cik": "320193",
        "name": "APPLE INC",
        "tickers": ["AAPL"],
        "exchanges": ["Nasdaq"],
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-24-000010", "0000320193-24-000011"],
                "filingDate": ["2024-02-01", "2024-02-02"],
                "reportDate": ["2024-01-31", "2024-01-31"],
                "acceptanceDateTime": ["2024-02-01T16:30:00.000Z", "2024-02-02T16:30:00.000Z"],
                "form": ["8-K", "10-Q"],
                "fileNumber": ["001-36743", "001-36743"],
                "items": ["2.02,9.01", ""],
                "primaryDocument": ["aapl-20240201.htm", "aapl-20240202.htm"],
                "primaryDocDescription": ["Current report", "Quarterly report"],
                "isXBRL": [1, 1],
                "isInlineXBRL": [1, 1],
            },
            "files": [
                {
                    "name": "CIK0000320193-submissions-001.json",
                    "filingFrom": "2010-01-01",
                    "filingTo": "2019-12-31",
                }
            ],
        },
    }


def _historical_submissions_payload():
    return {
        "accessionNumber": ["0000320193-12-000001"],
        "filingDate": ["2012-03-01"],
        "reportDate": ["2012-02-29"],
        "acceptanceDateTime": ["2012-03-01T16:00:00.000Z"],
        "form": ["8-K"],
        "fileNumber": ["001-36743"],
        "items": ["8.01"],
        "primaryDocument": ["aapl-20120301.htm"],
        "primaryDocDescription": ["Current report"],
        "isXBRL": [0],
        "isInlineXBRL": [0],
    }


def test_sec_submissions_adapter_reads_linked_history_filters_and_caches(tmp_path):
    root_url = "https://data.sec.gov/submissions/CIK0000320193.json"
    historical_url = "https://data.sec.gov/submissions/CIK0000320193-submissions-001.json"
    responses = {
        root_url: _recent_submissions_payload(),
        historical_url: _historical_submissions_payload(),
    }
    calls = []
    limiter = SpyRateLimiter()

    def transport(url, headers, timeout):
        calls.append((url, headers, timeout))
        return responses[url]

    provider = SecEdgarSubmissionsProvider(
        user_agent="CivicLedger test test@example.com",
        cache_directory=tmp_path,
        transport=transport,
        rate_limiter=limiter,
    )
    request = SecCompanyRequest(
        request_id="apple",
        cik="320193",
        start_date="2011-01-01",
        end_date="2024-12-31",
        forms=("8-K",),
    )

    first = provider.filings(request)
    second = provider.filings(request)

    assert first.retrieval_status == "fetched"
    assert second.retrieval_status == "cache_hit"
    assert [filing.filing_date for filing in first.filings] == ["2012-03-01", "2024-02-01"]
    assert first.company["tickers"] == ["AAPL"]
    assert len(calls) == 2
    assert limiter.wait_count == 2
    assert all(call[1]["User-Agent"] == "CivicLedger test test@example.com" for call in calls)


def test_sec_parser_and_filing_url_preserve_official_evidence():
    filings = parse_submission_filings(
        _historical_submissions_payload(),
        cik="320193",
        company_name="APPLE INC",
        source_url="https://data.sec.gov/submissions/history.json",
    )

    assert len(filings) == 1
    assert filings[0].items == ("8.01",)
    assert filings[0].is_xbrl is False
    assert normalize_cik("cik320193") == "0000320193"
    assert sec_filing_index_url("320193", filings[0].accession_number) == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019312000001/"
        "0000320193-12-000001-index.html"
    )
    with pytest.raises(ValueError):
        SecRateLimiter(requests_per_second=10.1)


def test_sec_atom_parser_preserves_official_filing_evidence():
    payload = """<?xml version="1.0" encoding="ISO-8859-1"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <company-info>
        <cik>0000320193</cik>
        <conformed-name>Apple Inc.</conformed-name>
        <assigned-sic>3571</assigned-sic>
        <assigned-sic-desc>Electronic Computers</assigned-sic-desc>
      </company-info>
      <entry>
        <content type="text/xml">
          <accession-number>0000320193-24-000010</accession-number>
          <file-number>001-36743</file-number>
          <filing-date>2024-02-01</filing-date>
          <filing-type>8-K</filing-type>
          <form-name>Current report</form-name>
          <items-desc>items 2.02 and 9.01</items-desc>
        </content>
        <updated>2024-02-01T16:30:00-05:00</updated>
      </entry>
    </feed>"""

    company, filings = parse_atom_filings(
        payload,
        cik="320193",
        source_url="https://www.sec.gov/cgi-bin/browse-edgar?output=atom",
    )

    assert company["name"] == "Apple Inc."
    assert company["sic"] == "3571"
    assert len(filings) == 1
    assert filings[0].form == "8-K"
    assert filings[0].items == ("2.02", "9.01")
    assert filings[0].accepted_at == "2024-02-01T16:30:00-05:00"


class FakeSecProvider:
    provider_id = "fake-sec"
    provider_name = "Fake SEC"
    source_tier = "official"
    documentation_url = "https://sec.example/docs"

    def filings(self, request):
        filing = SecFiling(
            cik=request.cik,
            company_name="EXAMPLE CORP",
            accession_number="0000001234-24-000001",
            filing_date="2024-02-01",
            report_date="2024-01-31",
            accepted_at="2024-02-01T16:00:00.000Z",
            form="8-K",
            file_number="001-00001",
            items=("2.02", "9.01"),
            primary_document="example.htm",
            primary_document_description="Current report",
            is_xbrl=True,
            is_inline_xbrl=True,
            source_url="https://data.sec.gov/submissions/CIK0000001234.json",
        )
        return SecFilingResult(
            company={
                "cik": request.cik,
                "name": "EXAMPLE CORP",
                "tickers": ["EXM"],
                "exchanges": ["NYSE"],
                "sic": "1234",
                "sic_description": "Example industry",
            },
            filings=(filing,),
            request_urls=("https://data.sec.gov/submissions/CIK0000001234.json",),
            retrieval_status="fetched",
        )


def test_sec_dataset_is_deterministic_official_and_review_gated():
    requests = [
        SecCompanyRequest("second", "1234", "2024-01-01", "2024-03-01", ("8-K",)),
        SecCompanyRequest("first", "1234", "2024-01-01", "2024-03-01", ("8-K",)),
    ]

    forward = build_sec_dataset(FakeSecProvider(), requests, artifact_date="2024-03-01")
    reverse = build_sec_dataset(FakeSecProvider(), list(reversed(requests)), artifact_date="2024-03-01")

    assert json.dumps(forward, sort_keys=True) == json.dumps(reverse, sort_keys=True)
    assert forward["summary"]["event_count"] == 1
    event = forward["events"][0]
    assert event["matched_request_ids"] == ["first", "second"]
    assert event["source_tier"] == "official"
    assert event["review_required_before_publication"] is True
    assert event["public_production_event"] is False
    assert {source["role"] for source in event["sources"]} == {
        "filing_index",
        "primary_document",
        "submissions_data",
    }


def test_sec_dataset_records_missing_identity_as_unavailable(tmp_path):
    provider = SecEdgarSubmissionsProvider(
        user_agent=None,
        cache_directory=tmp_path,
        transport=lambda *_: pytest.fail("transport must not be called without an identity header"),
    )
    request = SecCompanyRequest("missing-identity", "320193", "2024-01-01", "2024-03-01")

    dataset = build_sec_dataset(provider, [request], artifact_date="2024-03-01")

    assert dataset["events"] == []
    assert dataset["coverage_report"]["missing-identity"]["status"] == "unavailable"
    assert "SEC_EDGAR_USER_AGENT" in dataset["coverage_report"]["missing-identity"]["reason"]
    assert dataset["summary"]["public_production_event_count"] == 0
