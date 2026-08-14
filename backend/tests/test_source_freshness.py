import json
from datetime import date
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.check_source_freshness import ArtifactPolicy, evaluate_artifacts  # noqa: E402


def write_artifact(root: Path, relative_path: str, generated_at: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"generated_at": generated_at}) + "\n")


def test_freshness_policies_separate_blocking_advisory_and_reference_artifacts(tmp_path):
    write_artifact(tmp_path, "strict.json", "2026-07-01")
    write_artifact(tmp_path, "advisory.json", "2026-07-01")
    write_artifact(tmp_path, "reference.json", "2020-01-01")
    policies = (
        ArtifactPolicy("strict.json", max_age_days=14, stale_is_error=True),
        ArtifactPolicy("advisory.json", max_age_days=14, stale_is_error=False),
        ArtifactPolicy("reference.json", max_age_days=None),
    )

    failures, warnings = evaluate_artifacts(tmp_path, date(2026, 8, 14), policies)

    assert failures == ["strict.json is stale: 44 days old"]
    assert warnings == ["advisory.json is stale: 44 days old"]


def test_freshness_policy_rejects_missing_and_invalid_artifacts(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json\n")
    policies = (
        ArtifactPolicy("missing.json"),
        ArtifactPolicy("invalid.json"),
    )

    failures, warnings = evaluate_artifacts(tmp_path, date(2026, 8, 14), policies)

    assert failures == [
        "Missing required generated file: missing.json",
        "Unreadable generated file: invalid.json (JSONDecodeError)",
    ]
    assert warnings == []
