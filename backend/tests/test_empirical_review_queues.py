from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_empirical_review_queues import build_disclosure_queue, build_event_queue  # noqa: E402


def test_disclosure_validation_queue_is_deterministic_and_never_claims_review():
    first = build_disclosure_queue(ROOT)
    second = build_disclosure_queue(ROOT)

    assert first == second
    assert first["status"] == "human_labeling_required"
    assert first["human_reviewed_count"] == 0
    assert first["source_lane_summary"]["judicial"]["selected"] == 0
    assert all(item["label_status"] == "unreviewed" for item in first["items"])
    assert all(item["reviewer_id"] is None for item in first["items"])


def test_event_validation_queue_is_stratified_and_unlabeled():
    queue = build_event_queue(ROOT, limit=40)

    assert queue["selected_sample_count"] == 40
    assert len(queue["sample_counts_by_stratum"]) > 1
    assert all(item["relevance_label"] is None for item in queue["items"])
    assert all("causation" not in item["review_question"].lower() for item in queue["items"])
