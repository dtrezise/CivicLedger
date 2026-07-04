from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app import crud
from app.database import get_db
from app.main import app
from app.routes import events as events_route


@pytest.fixture()
def client():
    async def override_get_db():
        yield object()

    app.dependency_overrides[get_db] = override_get_db
    app.openapi_schema = None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.openapi_schema = None


def test_meta_status_contract(client):
    response = client.get("/meta/status")

    assert response.status_code == 200
    assert response.json() == {
        "last_ingestion_run_at": None,
        "dataset_version": "seed-v1",
        "parser_version": "1.0.0",
        "methodology_version": "1.0.0",
    }


def test_meta_methodology_contract(client):
    response = client.get("/meta/methodology")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"blocks", "key_rules"}
    assert len(payload["blocks"]) >= 1
    assert all(set(block) == {"title", "content"} for block in payload["blocks"])
    assert "Neutrality: present facts, not judgments" in payload["key_rules"]


def test_meta_sources_contract(client):
    response = client.get("/meta/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_version"] == "seed-v1"
    assert payload["methodology_version"] == "1.0.0"
    assert [source["id"] for source in payload["sources"]] == [
        "house-financial-disclosure",
        "senate-public-financial-disclosure",
    ]
    assert all(source["ingestion_status"] == "planned" for source in payload["sources"])
    assert all(source["provenance_requirements"] for source in payload["sources"])


@pytest.mark.parametrize(
    "params",
    [
        {"person_id": str(uuid4())},
        {"scope": "person"},
    ],
)
def test_events_reject_person_scoped_params_without_db(client, monkeypatch, params):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("crud.get_events should not be called for person-scoped params")

    monkeypatch.setattr(events_route.crud, "get_events", fail_if_called)

    response = client.get("/events", params=params)

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Person-scoped event filtering is not modeled yet; request global events without person_id.",
    }


def test_events_id_path_is_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/events/{id}" in paths
    assert "/events/{event_id}" not in paths


def test_search_people_response_schema_with_mocked_crud(client, monkeypatch):
    person_id = UUID("11111111-1111-1111-1111-111111111111")

    async def fake_search_people(db, q):
        assert q == "smith"
        return [
            SimpleNamespace(
                id=person_id,
                full_name="Alex Smith",
                chamber="House",
                state="CA",
                party="I",
                service_start=date(2021, 1, 3),
                service_end=None,
            )
        ]

    monkeypatch.setattr(crud, "search_people", fake_search_people)

    response = client.get("/search/people", params={"q": "smith"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "person_id": str(person_id),
            "full_name": "Alex Smith",
            "chamber": "House",
            "state": "CA",
            "party": "I",
            "service_start": "2021-01-03",
            "service_end": None,
        }
    ]


def test_scorecard_openapi_schema_includes_metrics_and_deductions(client):
    openapi = client.get("/openapi.json").json()
    scorecard_schema = openapi["components"]["schemas"]["ScorecardResponse"]
    response_schema = openapi["paths"]["/people/{person_id}/scorecard"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]

    assert response_schema == {"$ref": "#/components/schemas/ScorecardResponse"}
    assert "metrics" in scorecard_schema["properties"]
    assert "deductions" in scorecard_schema["properties"]
    assert "metrics" in scorecard_schema["required"]
    assert "deductions" in scorecard_schema["required"]
