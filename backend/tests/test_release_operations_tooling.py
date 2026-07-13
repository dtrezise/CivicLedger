import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "release_ops"
sys.path.insert(0, str(ROOT / "scripts"))


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_parity_checks_identity_inventory_and_all_files(monkeypatch):
    module = load_script("verify_pages_cloudflare_parity.py")
    common = {
        "release.json": {"dataset_version": "d1", "methodology_version": "m1", "commit": "abc"},
        "data/manifest.json": {"dataset_version": "d1", "methodology_version": "m1"},
        "release-checksums.json": {
            "files": [{"path": "index.html", "bytes": 16, "sha256": "0" * 64}]
        },
        "index.html": {"html": "same"},
    }
    monkeypatch.setattr(module, "fetch", lambda base, path, timeout=30: json.dumps(common[path], sort_keys=True).encode())
    report = module.validate("https://pages.example", "https://cloudflare.example", include_files=False)
    assert report["status"] == "passed"
    assert report["file_count"] == 1


def test_rollback_recommendation_requires_post_deploy_failure_and_prior_target():
    module = load_script("recommend_production_rollback.py")
    gates = json.loads((FIXTURES / "failed_gates.json").read_text())
    readiness = json.loads((FIXTURES / "rollback_readiness.json").read_text())
    report = module.recommend(gates, readiness)
    assert report["status"] == "rollback_recommended"
    assert report["rollback_target_version_id"].startswith("1111")

    gates["gates"][1]["phase"] = "pre_deploy"
    assert module.recommend(gates, readiness)["status"] == "no_action"


def test_preview_rehearsal_selects_target_without_executing_rollback(tmp_path):
    module = load_script("rehearse_preview_rollback.py")
    report = module.rehearse(
        FIXTURES / "cloudflare_versions.json",
        FIXTURES / "cloudflare_status.json",
        ROOT / "pages-site",
        ["fake-wrangler"],
        False,
    )
    assert report["rollback_target_version_id"].startswith("1111")
    assert report["rollback_executed"] is False
    assert "deploy --dry-run" in report["dry_run_command"]
    assert "rollback-rehearsal" in report["dry_run_command"]
