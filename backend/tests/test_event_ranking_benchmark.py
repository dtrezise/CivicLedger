import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_event_ranking import evaluate  # noqa: E402


def test_curated_ranking_benchmark_reports_precision_recall_after_sector_window_tuning():
    fixture = json.loads(
        (ROOT / "backend" / "tests" / "fixtures" / "event_ranking" / "benchmark_v1.json").read_text()
    )

    result = evaluate(fixture, generated_at="2025-07-01")

    assert result["metrics"] == {
        "case_count": 7,
        "positive_label_count": 3,
        "negative_label_count": 4,
        "true_positive": 3,
        "false_positive": 0,
        "false_negative": 0,
        "true_negative": 4,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }
    distant_sector = next(row for row in result["cases"] if row["id"] == "sector-thirty-nine-days-before")
    assert distant_sector["predicted_candidate"] is False
    assert result["scope_note"].startswith("This is a deterministic regression benchmark")
