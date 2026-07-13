import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from public_corpus_metrics import write_json  # noqa: E402
from report_public_corpus_growth import build_snapshot, update_history  # noqa: E402
from simulate_r2_public_partition_migration import build_simulation  # noqa: E402


def _write_artifact(path: Path, payload: str, data_root: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = payload.encode()
    path.write_bytes(encoded)
    return {
        "bytes": len(encoded),
        "path": path.relative_to(data_root).as_posix(),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _build_fixture(site: Path, large_payload: str) -> Path:
    data = site / "data"
    bootstrap = _write_artifact(data / "partitions" / "overview.json", '"bootstrap-payload"\n', data)
    small = _write_artifact(data / "partitions" / "timelines" / "small.json", '"small"\n', data)
    large = _write_artifact(data / "partitions" / "timelines" / "large.json", large_payload, data)
    (site / "index.html").write_text("fixture\n")
    manifest = {
        "dataset_version": "fixture-v1",
        "files": {"overview": bootstrap},
        "generated_at": "2026-07-05",
        "partitions": {"timelines": {"large": large, "small": small}},
    }
    manifest_path = data / "manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


def test_weekly_growth_history_is_deterministic_and_recomputes_deltas(tmp_path):
    site = tmp_path / "site"
    manifest_path = _build_fixture(site, '"large-payload"\n')
    (site / ".DS_Store").write_bytes(b"local-only metadata")
    first = build_snapshot(site, manifest_path, "2026-07-05")
    history = update_history(None, first)

    assert first["iso_week"] == "2026-W27"
    assert first["public_artifacts"]["query_partition_count"] == 2
    assert first["static_assets"]["asset_count"] == 5
    assert update_history(history, first) == history

    manifest_path = _build_fixture(site, '"large-payload-with-growth"\n')
    second = build_snapshot(site, manifest_path, "2026-07-12")
    updated = update_history(history, second)

    assert [item["iso_week"] for item in updated["snapshots"]] == ["2026-W27", "2026-W28"]
    assert updated["snapshots"][1]["delta_from_previous_week"]["query_partition_count"] == 0
    assert updated["snapshots"][1]["delta_from_previous_week"]["public_artifact_bytes"] > 0
    assert update_history(updated, second) == updated


def test_r2_simulator_selects_query_payloads_without_activating_r2(tmp_path):
    site = tmp_path / "site"
    manifest_path = _build_fixture(site, '"this-query-partition-is-large-enough"\n')
    report = build_simulation(
        site,
        manifest_path,
        candidate_bytes=20,
        priority_bytes=30,
        activation_asset_count=100,
        activation_total_bytes=100_000,
        activation_individual_bytes=10_000,
    )

    assert [item["path"] for item in report["candidate_partitions"]] == [
        "data/partitions/timelines/large.json"
    ]
    assert report["candidate_partitions"][0]["tier"] == "priority"
    assert [item["path"] for item in report["large_bootstrap_artifacts_kept_static"]] == [
        "data/partitions/overview.json"
    ]
    assert report["activation_assessment"]["triggered_gates"] == []
    assert report["safety"] == {
        "activates_r2": False,
        "cloud_api_calls": False,
        "creates_resources": False,
        "estimated_cost_usd": None,
        "mode": "offline_read_only_simulation",
    }
