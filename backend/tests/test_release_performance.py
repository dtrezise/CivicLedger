import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_public_performance_budgets_pass():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_performance.py"), "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    assert summary["initial_raw_bytes"] <= 4_750_000
    assert summary["initial_gzip_bytes"] <= 350_000
    assert summary["shell_gzip_bytes"] <= 36_000
    assert summary["largest_partition_bytes"] <= 5_000_000
    assert summary["deployment_bytes"] <= 325_000_000


def test_manifest_keeps_large_data_lazy_loaded():
    manifest = json.loads((ROOT / "pages-site" / "data" / "manifest.json").read_text())
    assert len(manifest["files"]) == 7
    assert len(manifest["partitions"]["timelines"]) >= 350
    assert len(manifest["partitions"]["market"]) >= 25
    assert len(manifest["partitions"]["events"]) >= 18
