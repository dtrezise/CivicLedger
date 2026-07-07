import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "public_officials" / "public_official_roles.json"
FRED_CONTEXT = ROOT / "data" / "context" / "fred_market_context.json"


def test_public_officials_dataset_has_expected_initial_scope():
    data = json.loads(DATASET.read_text())
    summary = data["summary"]

    assert summary["person_count"] >= 1400
    assert summary["role_count"] >= 3300
    assert summary["role_counts_by_branch"]["Executive"] >= 50
    assert summary["role_counts_by_branch"]["Judicial"] >= 500
    assert summary["role_counts_by_branch"]["Legislative"] >= 2700
    assert summary["role_counts_by_category"]["representative"] >= 2100
    assert summary["role_counts_by_category"]["senator"] >= 550
    assert set(summary["role_counts_by_term"]) == {"trump-45", "biden-46", "trump-47"}


def test_public_officials_dataset_roles_are_source_backed():
    data = json.loads(DATASET.read_text())

    assert data["sources"]
    for role in data["roles"]:
        assert role["external_role_id"]
        assert role["external_person_id"]
        assert role["full_name"]
        assert role["source_url"].startswith("https://")
        assert role["source_tier"] in {"official", "official_archive"}


def test_congressional_dataset_has_115th_to_119th_counts():
    data = json.loads((ROOT / "data" / "public_officials" / "congressional_service_terms.json").read_text())
    summary = data["summary"]

    assert data["scope"]["congress_numbers"] == [115, 116, 117, 118, 119]
    assert summary["person_count"] >= 900
    assert summary["role_count"] >= 2700
    assert set(summary["role_counts_by_congress"]) == {"115", "116", "117", "118", "119"}
    assert all(count >= 540 for count in summary["role_counts_by_congress"].values())
    assert summary["role_counts_by_chamber"]["House"] >= 2200
    assert summary["role_counts_by_chamber"]["Senate"] >= 550


def test_fred_context_dataset_has_trade_relevant_macro_scope():
    data = json.loads(FRED_CONTEXT.read_text())

    assert data["summary"]["series_count"] == 6
    assert data["summary"]["observation_count"] >= 1000
    assert data["summary"]["release_event_count"] >= 20
    assert {"FEDFUNDS", "CPIAUCSL", "DGS10", "DGS2", "UNRATE", "USREC"} <= set(data["series"])
    assert data["summary"]["active_context_source"] == "FRED"
    assert set(data["summary"]["deferred_sources"]) == {"FEC", "USAspending"}
    assert data["context_label"].startswith("Context only")
