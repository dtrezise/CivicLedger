import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "public_officials" / "public_official_roles.json"


def test_public_officials_dataset_has_expected_initial_scope():
    data = json.loads(DATASET.read_text())
    summary = data["summary"]

    assert summary["person_count"] >= 500
    assert summary["role_count"] >= 550
    assert summary["role_counts_by_branch"]["Executive"] >= 50
    assert summary["role_counts_by_branch"]["Judicial"] >= 500
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
