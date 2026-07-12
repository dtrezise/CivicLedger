from __future__ import annotations

import json
from http.client import IncompleteRead
from pathlib import Path

import app.services.official_event_involvement as involvement
from app.services.official_event_involvement import (
    CachedRateLimitedHttpClient,
    OfficialCongressGovClient,
    SourceSnapshot,
    build_official_event_involvement,
    build_role_index,
    canonical_request_url,
    parse_house_roll_call,
    parse_senate_roll_call,
    sha256_bytes,
)


HOUSE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rollcall-vote>
  <vote-metadata>
    <congress>118</congress><session>1st</session><rollcall-num>12</rollcall-num>
    <legis-num>H R 1</legis-num><vote-question>On Passage</vote-question>
    <vote-type>RECORDED VOTE</vote-type><vote-result>Passed</vote-result>
    <action-date>1-May-2023</action-date><vote-desc>Example Act</vote-desc>
    <vote-totals><totals-by-vote><yea-total>1</yea-total><nay-total>1</nay-total>
      <present-total>0</present-total><not-voting-total>0</not-voting-total>
    </totals-by-vote></vote-totals>
  </vote-metadata>
  <vote-data>
    <recorded-vote><legislator name-id="H000001" party="D" state="MD">Hall</legislator><vote>Yea</vote></recorded-vote>
    <recorded-vote><legislator name-id="H000002" party="R" state="VA">Young</legislator><vote>Nay</vote></recorded-vote>
  </vote-data>
</rollcall-vote>"""


SENATE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<roll_call_vote>
  <congress>118</congress><session>1</session><vote_number>20</vote_number>
  <vote_date>May 2, 2023,  04:30 PM</vote_date>
  <vote_question_text>On Passage of the Bill H.R. 1</vote_question_text>
  <vote_document_text>An example bill.</vote_document_text>
  <vote_result_text>Bill Passed (1-0)</vote_result_text><question>On Passage</question>
  <document><document_congress>118</document_congress><document_type>H.R.</document_type>
    <document_number>1</document_number><document_name>H.R. 1</document_name>
    <document_title>An example bill.</document_title><document_short_title>Example Act</document_short_title>
  </document>
  <count><yeas>1</yeas><nays>0</nays><present/><absent>0</absent></count>
  <tie_breaker><by_whom/><tie_breaker_vote/></tie_breaker>
  <members><member><member_full>Smith (D-MD)</member_full><last_name>Smith</last_name>
    <first_name>Jane</first_name><party>D</party><state>MD</state><vote_cast>Yea</vote_cast>
    <lis_member_id>S999</lis_member_id></member></members>
</roll_call_vote>"""


def _role(
    bioguide_id: str,
    full_name: str,
    chamber: str,
    state: str,
    *,
    external_role_id: str | None = None,
) -> dict:
    return {
        "branch": "Legislative",
        "external_person_id": f"congress:{bioguide_id}",
        "external_role_id": external_role_id or f"congress-gov:118:{bioguide_id}:{chamber.lower()}",
        "full_name": full_name,
        "role_category": "senator" if chamber == "Senate" else "representative",
        "role_title": "U.S. Senator" if chamber == "Senate" else "U.S. Representative",
        "service_start": "2023-01-03",
        "service_end": "2025-01-03",
        "source_url": f"https://api.congress.gov/v3/member/{bioguide_id}?format=json",
        "source_metadata": {
            "bioguide_id": bioguide_id,
            "chamber": chamber,
            "congress_number": 118,
            "state": state,
            "party": "Democratic",
        },
    }


def _inputs() -> tuple[dict, dict]:
    events = {
        "schema_version": "federal-market-events-v1",
        "generated_at": "2024-01-01",
        "sources": [{"id": "federal-events-source", "url": "https://example.gov/events"}],
        "events": [
            {
                "id": "congress-law-118-hr-1",
                "date": "2023-05-03",
                "event_type": "legislation",
                "label": "Example Act",
                "law_number": "118-1",
                "jurisdiction_scope": ["health"],
                "sources": ["https://www.congress.gov/bill/118th-congress/house-bill/1"],
            },
            {
                "id": "federal-register-eo-14000",
                "date": "2023-06-01",
                "event_type": "executive_order",
                "label": "Executive Order 14000: Example",
                "jurisdiction_scope": ["commerce"],
                "sources": ["https://www.federalregister.gov/example-order"],
            },
            {
                "id": "scotus-2022-1-22-1",
                "date": "2023-06-15",
                "event_type": "court_decision",
                "label": "Example Corp. v. United States",
                "court": "Supreme Court of the United States",
                "docket_number": "22-1",
                "citation": "600 U.S. 1",
                "jurisdiction_scope": ["securities"],
                "sources": ["https://www.supremecourt.gov/opinions/example.pdf"],
            },
        ],
    }
    roles = {
        "generated_at": "2024-01-02",
        "sources": [{"id": "roles-source", "url": "https://api.congress.gov/"}],
        "roles": [
            _role("H000001", "Helen Hall", "House", "MD"),
            _role("H000002", "Yara Young", "House", "VA"),
            _role("S000001", "Jane Q. Smith", "Senate", "MD"),
            {
                "branch": "Executive",
                "external_person_id": "exec:example-president",
                "external_role_id": "president:2021",
                "full_name": "Example President",
                "role_category": "elected_executive",
                "role_title": "President",
                "presidential_term": "example-46",
                "service_start": "2021-01-20",
                "service_end": "2025-01-20",
                "source_url": "https://www.whitehouse.gov/",
            },
            {
                "branch": "Judicial",
                "external_person_id": "fjc:example-justice",
                "external_role_id": "fjc:example-role",
                "full_name": "Example Justice",
                "role_category": "supreme_court",
                "role_title": "Associate Justice",
                "court": "Supreme Court of the United States",
                "service_start": "2020-01-01",
                "service_end": None,
                "source_url": "https://www.fjc.gov/example.csv",
            },
        ],
    }
    return events, roles


class FakeHttpClient:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses

    def get(self, url: str, *, params: dict | None = None, secret_params: dict | None = None) -> SourceSnapshot:
        canonical_url = canonical_request_url(url, params)
        assert "api_key" not in canonical_url
        body = self.responses[canonical_url]
        return SourceSnapshot(
            url=canonical_url,
            body=body,
            response_sha256=sha256_bytes(body),
            retrieved_at="2024-01-03T12:00:00Z",
            content_type="application/xml" if canonical_url.endswith(".xml") else "application/json",
        )


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _fake_congress_client() -> OfficialCongressGovClient:
    base = "https://api.congress.gov/v3/bill/118/hr/1"
    house_url = "https://clerk.house.gov/evs/2023/roll012.xml"
    senate_url = "https://www.senate.gov/legislative/LIS/roll_call_votes/vote1181/vote_118_1_00020.xml"
    responses = {
        canonical_request_url(base, {"format": "json"}): _json_bytes(
            {
                "bill": {
                    "congress": 118,
                    "type": "HR",
                    "number": "1",
                    "title": "Example Act",
                    "introducedDate": "2023-01-10",
                    "originChamber": "House",
                    "laws": [{"type": "Public Law", "number": "118-1"}],
                    "sponsors": [
                        {
                            "bioguideId": "H000001",
                            "firstName": "Helen",
                            "lastName": "Hall",
                            "party": "D",
                            "state": "MD",
                        }
                    ],
                }
            }
        ),
        canonical_request_url(base + "/cosponsors", {"format": "json", "limit": 250, "offset": 0}): _json_bytes(
            {
                "cosponsors": [
                    {
                        "bioguideId": "H000002",
                        "firstName": "Yara",
                        "lastName": "Young",
                        "party": "R",
                        "state": "VA",
                        "sponsorshipDate": "2023-01-11",
                        "sponsorshipWithdrawnDate": "2023-01-12",
                        "isOriginalCosponsor": True,
                    },
                    {
                        "bioguideId": "H000002",
                        "firstName": "Yara",
                        "lastName": "Young",
                        "party": "R",
                        "state": "VA",
                        "sponsorshipDate": "2023-02-01",
                        "isOriginalCosponsor": False,
                    }
                ],
                "pagination": {"next": None},
            }
        ),
        canonical_request_url(base + "/actions", {"format": "json", "limit": 250, "offset": 0}): _json_bytes(
            {
                "actions": [
                    {
                        "actionDate": "2023-05-01",
                        "type": "Floor",
                        "text": "Passed House by recorded vote.",
                        "recordedVotes": [
                            {
                                "chamber": "House",
                                "congress": 118,
                                "sessionNumber": 1,
                                "rollNumber": 12,
                                "date": "2023-05-01T16:00:00Z",
                                "url": house_url,
                            }
                        ],
                    },
                    {
                        "actionDate": "2023-05-01",
                        "type": "NotUsed",
                        "text": "Duplicate source-system description.",
                        "recordedVotes": [
                            {
                                "chamber": "House",
                                "congress": 118,
                                "sessionNumber": 1,
                                "rollNumber": 12,
                                "date": "2023-05-01T16:00:00Z",
                                "url": house_url,
                            }
                        ],
                    },
                    {
                        "actionDate": "2023-05-02",
                        "type": "Floor",
                        "text": "Passed Senate by yea-nay vote.",
                        "recordedVotes": [
                            {
                                "chamber": "Senate",
                                "congress": 118,
                                "sessionNumber": 1,
                                "rollNumber": 20,
                                "date": "2023-05-02T20:30:00Z",
                                "url": senate_url,
                            }
                        ],
                    },
                ],
                "pagination": {"next": None},
            }
        ),
        house_url: HOUSE_XML,
        senate_url: SENATE_XML,
    }
    return OfficialCongressGovClient(FakeHttpClient(responses), api_key="not-persisted")


def test_roll_call_parsers_preserve_member_ids_questions_and_totals():
    house = parse_house_roll_call(HOUSE_XML)
    senate = parse_senate_roll_call(SENATE_XML)

    assert house["id"] == "house-118-1-12"
    assert house["members"][0]["bioguide_id"] == "H000001"
    assert house["members"][1]["vote_cast"] == "Nay"
    assert house["totals"] == {"yea": 1, "nay": 1, "present": 0, "not_voting": 0}
    assert senate["id"] == "senate-118-1-20"
    assert senate["vote_date"] == "2023-05-02"
    assert senate["members"][0]["lis_member_id"] == "S999"
    assert senate["document"]["name"] == "H.R. 1"


def test_role_index_resolves_house_ids_and_senate_names_without_guessing_across_states():
    _events, roles = _inputs()
    index = build_role_index(roles)

    assert index.resolve_bioguide("H000001", 118, "House", "2023-05-01")["full_name"] == "Helen Hall"
    senate = index.resolve_senate_member(
        first_name="Jane",
        last_name="Smith",
        state="MD",
        congress=118,
        event_date="2023-05-02",
    )
    assert senate["external_person_id"] == "congress:S000001"
    assert (
        index.resolve_senate_member(
            first_name="Jane",
            last_name="Smith",
            state="VA",
            congress=118,
            event_date="2023-05-02",
        )
        is None
    )


def test_cache_omits_credentials_and_supports_verified_offline_rebuild(monkeypatch, tmp_path: Path):
    requested_urls = []

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        assert timeout == 60.0
        return Response()

    monkeypatch.setattr(involvement, "urlopen", fake_urlopen)
    live = CachedRateLimitedHttpClient(tmp_path, min_interval_seconds=0)
    first = live.get(
        "https://api.example.gov/data",
        params={"z": 2, "a": 1},
        secret_params={"api_key": "top-secret"},
    )

    assert "api_key=top-secret" in requested_urls[0]
    assert first.url == "https://api.example.gov/data?a=1&z=2"
    cache_text = next(tmp_path.glob("*.json")).read_text()
    assert "top-secret" not in cache_text
    assert "api_key" not in cache_text

    offline = CachedRateLimitedHttpClient(tmp_path, offline=True)
    second = offline.get("https://api.example.gov/data", params={"a": 1, "z": 2})
    assert second.body == first.body
    assert second.response_sha256 == first.response_sha256
    assert second.retrieved_at == first.retrieved_at
    assert second.from_cache is True


def test_http_client_retries_incomplete_response_bodies(monkeypatch, tmp_path: Path):
    attempts = 0

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise IncompleteRead(b'{"partial"', 10)
            return b'{"complete": true}'

    monkeypatch.setattr(involvement, "urlopen", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(involvement.time, "sleep", lambda _seconds: None)
    client = CachedRateLimitedHttpClient(tmp_path, min_interval_seconds=0, retries=2)

    snapshot = client.get("https://api.example.gov/retry")

    assert snapshot.body == b'{"complete": true}'
    assert attempts == 2
    assert client.network_requests == 2


def test_dataset_separates_direct_records_from_context_and_is_deterministic():
    events, roles = _inputs()
    first = build_official_event_involvement(events, roles, _fake_congress_client())
    second = build_official_event_involvement(events, roles, _fake_congress_client())

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["generated_at"] == "2024-01-03"
    assert first["summary"]["roll_call_count"] == 2
    assert first["summary"]["relationship_counts_by_type"]["sponsor"] == 1
    assert first["summary"]["relationship_counts_by_type"]["cosponsor"] == 2
    assert first["summary"]["relationship_counts_by_type"]["recorded_vote"] == 3
    cosponsorships = [row for row in first["relationships"] if row["relationship_type"] == "cosponsor"]
    assert len({row["id"] for row in cosponsorships}) == 2
    assert {row["sponsorship_withdrawn_date"] for row in cosponsorships} == {"2023-01-12", None}

    house_roll = next(row for row in first["roll_calls"] if row["id"] == "house-118-1-12")
    assert len(house_roll["congress_gov_action_texts"]) == 2
    assert "procedural votes" in house_roll["scope_note"]

    direct_types = set(first["methodology"]["direct_relationship_types"])
    direct = [row for row in first["relationships"] if row["relationship_type"] in direct_types]
    context = [row for row in first["relationships"] if row["relationship_type"] not in direct_types]
    assert {row["relationship_type"] for row in direct} == {"sponsor", "cosponsor", "recorded_vote"}
    assert all(row["actor_id"].startswith("actor:") for row in direct)
    assert first["methodology"]["relationship_type_definitions"]["recorded_vote"][
        "evidence_path"
    ].startswith("relationship.roll_call_id")
    assert first["summary"]["actor_record_count"] == len(first["actors"])
    assert all(row.get("scope_note") for row in context)
    assert all("actor" not in row for row in context if row["relationship_type"] != "presidential_enactment_context" and row["relationship_type"] != "presidential_executive_order_context")

    presidential = [row for row in context if row["relationship_type"].startswith("presidential_")]
    assert presidential
    assert all(row["relationship_class"] == "temporal_officeholder_context_only" for row in presidential)
    assert all("does not independently establish" in row["scope_note"] for row in presidential)

    court = next(row for row in context if row["relationship_type"] == "court_docket_institutional_link")
    assert court["institution"]["name"] == "Supreme Court of the United States"
    assert "individual judge" in court["scope_note"]
    assert "actor" not in court

    fetched_sources = [row for row in first["sources"] if row["source_class"] == "fetched_official_response"]
    assert fetched_sources
    assert all(row["response_sha256"] and row["url"] for row in fetched_sources)
    assert all("api_key" not in row["url"] for row in fetched_sources)
