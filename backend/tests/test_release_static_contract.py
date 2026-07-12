import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_static_interaction_and_url_contract_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_static_contract.py"), "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    assert summary["interaction_controls"] >= 10
    assert summary["url_parameters"] >= 14
    assert summary["dom_hooks"] >= 35


def test_runtime_loads_only_partitioned_public_data():
    javascript = (ROOT / "pages-site" / "app.js").read_text()
    assert 'fetchJson("./data/manifest.json")' in javascript
    assert "civicledger-static.json" not in javascript
    assert 'fetch(path, { cache: "no-store" })' in javascript
