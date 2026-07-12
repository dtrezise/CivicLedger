import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DATA = ROOT / "pages-site" / "data"


def test_generated_release_json_is_canonical():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_determinism.py"), "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    assert summary["canonical_partitions"] >= 390
    assert len(summary["aggregate_sha256"]) == 64


def test_manifest_digest_is_stable_across_repeated_reads():
    path = PUBLIC_DATA / "manifest.json"
    first = hashlib.sha256(path.read_bytes()).hexdigest()
    second = hashlib.sha256(path.read_bytes()).hexdigest()
    assert first == second
    manifest = json.loads(path.read_text())
    assert list(manifest) == sorted(manifest)
