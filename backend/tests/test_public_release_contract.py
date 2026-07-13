import hashlib
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DATA = ROOT / "pages-site" / "data"


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.script_sources = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id":
                self.ids.append(value)
            if tag == "script" and key == "src":
                self.script_sources.append(value)


def test_public_release_validator_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_public_release_dataset.py"), "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)
    assert summary["officials"] >= 2_000
    assert summary["timelines"] >= 298
    assert summary["trades"] >= 54_000
    assert summary["house_documents"] >= 7_500
    assert summary["house_transactions"] >= 53_000
    assert summary["production_trades"] == 0
    assert summary["market_symbols"] >= 25


def test_manifest_hashes_every_public_partition():
    manifest = json.loads((PUBLIC_DATA / "manifest.json").read_text())
    records = list(manifest["files"].values())
    records.extend(
        record
        for group in manifest["partitions"].values()
        for record in group.values()
    )
    assert len(records) >= 45
    for record in records:
        encoded = (PUBLIC_DATA / record["path"]).read_bytes()
        assert len(encoded) == record["bytes"]
        assert hashlib.sha256(encoded).hexdigest() == record["sha256"]


def test_static_app_dom_contract_and_keyboard_support():
    html = (ROOT / "pages-site" / "index.html").read_text()
    javascript = (ROOT / "pages-site" / "app.js").read_text()
    parser = IdCollector()
    parser.feed(html)

    assert len(parser.ids) == len(set(parser.ids))
    referenced_ids = set(re.findall(r'\$\("([A-Za-z][A-Za-z0-9_-]*)"\)', javascript))
    assert referenced_ids <= set(parser.ids)
    assert '$("transactionRows").addEventListener("keydown"' in javascript
    assert 'event.key' in javascript
    assert "aria-selected" in javascript
    assert "eventSearch" in parser.ids
    assert "eventResults" in parser.ids
    assert "eventSelect" not in parser.ids


def test_static_app_loads_manifest_instead_of_monolith():
    html = (ROOT / "pages-site" / "index.html").read_text()
    javascript = (ROOT / "pages-site" / "app.js").read_text()
    parser = IdCollector()
    parser.feed(html)

    assert "./data/manifest.json" in javascript
    assert "civicledger-static.json" not in javascript
    assert any(source.startswith("./assets/echarts-5.6.0.") for source in parser.script_sources)
    assert all(not source.startswith(("http://", "https://")) for source in parser.script_sources)
    assert "Career" in html and "Calendar" in html and "Event" in html
