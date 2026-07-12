#!/usr/bin/env python3
"""Evaluate trade-event candidate ranking against a curated regression benchmark."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_pages_dataset import trade_context_candidates  # noqa: E402


DEFAULT_FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "event_ranking" / "benchmark_v1.json"
DEFAULT_OUTPUT = ROOT / "data" / "quality" / "event_ranking_benchmark.json"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate(payload: dict, generated_at: str | None = None) -> dict:
    relationships = []
    events = {}
    labels = {}
    for case in payload.get("cases", []):
        case_id = case["id"]
        labels[case_id] = bool(case["expected_relevant"])
        relationships.append(
            {
                "id": case_id,
                "date": case["date"],
                "relationship_tier": case["relationship_tier"],
                "relationship_tier_rank": case["relationship_tier_rank"],
                "relationship_reasons": list(case.get("relationship_reasons", [])),
                "display_default": False,
            }
        )
        events[case_id] = {
            "id": case_id,
            "source_tier": case.get("source_tier"),
            "editor_status": case.get("editor_status"),
        }

    trade_context_candidates(relationships, payload.get("trades", []), events)
    predictions = {row["id"]: bool(row.get("trade_context_candidate")) for row in relationships}
    tp = sum(predictions[key] and labels[key] for key in labels)
    fp = sum(predictions[key] and not labels[key] for key in labels)
    fn = sum(not predictions[key] and labels[key] for key in labels)
    tn = sum(not predictions[key] and not labels[key] for key in labels)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = _ratio(2 * precision * recall, precision + recall)
    ranked = sorted(
        (
            {
                "id": row["id"],
                "expected_relevant": labels[row["id"]],
                "predicted_candidate": predictions[row["id"]],
                "candidate_rank": row.get("candidate_rank"),
                "candidate_score": row.get("candidate_score"),
            }
            for row in relationships
        ),
        key=lambda row: (row["candidate_rank"] is None, row["candidate_rank"] or 10**9, row["id"]),
    )
    return {
        "schema_version": "trade-event-ranking-benchmark-v1",
        "generated_at": generated_at or date.today().isoformat(),
        "benchmark_id": payload.get("benchmark_id"),
        "label_policy": payload.get("label_policy"),
        "methodology_version": "trade-window-v3",
        "scope_note": (
            "This is a deterministic regression benchmark for ranking behavior. It does not measure "
            "real-world causation, intent, knowledge, misconduct, or investigative accuracy."
        ),
        "metrics": {
            "case_count": len(labels),
            "positive_label_count": sum(labels.values()),
            "negative_label_count": len(labels) - sum(labels.values()),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
        "cases": ranked,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-precision", type=float, default=0.7)
    parser.add_argument("--minimum-recall", type=float, default=0.9)
    args = parser.parse_args()

    result = evaluate(json.loads(args.fixture.read_text()))
    metrics = result["metrics"]
    if metrics["precision"] < args.minimum_precision or metrics["recall"] < args.minimum_recall:
        raise SystemExit(
            "Ranking benchmark failed: "
            f"precision={metrics['precision']}, recall={metrics['recall']}"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        f"Wrote {args.output}: precision={metrics['precision']}, "
        f"recall={metrics['recall']}, f1={metrics['f1']}"
    )


if __name__ == "__main__":
    main()
