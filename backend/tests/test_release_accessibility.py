import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_check(name: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_release_accessibility_and_responsive_contract_passes():
    summary = run_check("check_release_accessibility.py")
    assert summary["landmarks"] == 4
    assert summary["controls"] >= 10
    assert summary["html_ids"] >= 40
    assert summary["headings"] >= 8


def test_public_charts_have_text_and_aria_alternatives():
    html = (ROOT / "pages-site" / "index.html").read_text()
    assert re.search(r'<div[^>]+id="tradeChart"[^>]+role="img"[^>]+aria-label=', html)
    assert re.search(r'<div[^>]+id="marketChart"[^>]+role="img"[^>]+aria-label=', html)
    assert 'id="chartAlternative" aria-live="polite"' in html
    assert '<th scope="col">' in html
