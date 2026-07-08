#!/usr/bin/env python3
"""Build scheduled stale-source alerts for current officials and live source lanes."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "disclosures" / "disclosure_ingestion_queue.json"
RAW_ARCHIVE = ROOT / "data" / "disclosures" / "raw_document_archive_index.json"
COMPLETENESS = ROOT / "data" / "disclosures" / "disclosure_completeness_dashboard.json"
PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
OUTPUT = ROOT / "data" / "disclosures" / "source_staleness_alerts.json"


def read_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text())


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def alert(alert_id: str, severity: str, source_id: str | None, message: str, count: int = 0) -> dict:
    return {
        "alert_id": alert_id,
        "severity": severity,
        "source_id": source_id,
        "message": message,
        "affected_count": count,
        "status": "open" if severity in {"warning", "high"} else "monitoring",
    }


def build_dataset() -> dict:
    today = date.today()
    queue = read_json(QUEUE, {"entries": [], "summary": {}})
    raw_archive = read_json(RAW_ARCHIVE, {"documents": [], "summary": {}})
    completeness = read_json(COMPLETENESS, {"rows": [], "summary": {}})
    officials = read_json(PUBLIC_OFFICIALS, {"generated_at": None, "summary": {}})
    alerts = []

    current_entries = [
        row
        for row in queue.get("entries", [])
        if row.get("priority") in {"high_current_official", "high_current_term"}
    ]
    current_by_source = Counter(row.get("source_id") for row in current_entries)
    archived_by_source = Counter(
        row.get("source_id") for row in raw_archive.get("documents", []) if row.get("archive_status") == "archived"
    )
    for source_id, count in sorted(current_by_source.items()):
        if archived_by_source[source_id] == 0:
            alerts.append(
                alert(
                    f"{source_id}:current-raw-documents-missing",
                    "warning",
                    source_id,
                    "Current official/current-term queue has no archived raw disclosure documents yet.",
                    count,
                )
            )
        else:
            alerts.append(
                alert(
                    f"{source_id}:current-raw-documents-started",
                    "info",
                    source_id,
                    "Current source lane has at least one archived raw disclosure document.",
                    archived_by_source[source_id],
                )
            )

    reviewed_count = completeness.get("summary", {}).get("reviewed_public_trade_count", 0)
    if reviewed_count == 0:
        alerts.append(
            alert(
                "public-production-trades:none",
                "warning",
                None,
                "No reviewed public production trade rows exist yet; keep public UI labeled as demo/source-status.",
                0,
            )
        )

    generated = parse_date(officials.get("generated_at"))
    if generated:
        age_days = (today - generated).days
        severity = "warning" if age_days > 14 else "info"
        alerts.append(
            alert(
                "public-official-roster:freshness",
                severity,
                None,
                f"Public official roster generated {age_days} day(s) ago.",
                officials.get("summary", {}).get("person_count", 0),
            )
        )

    return {
        "generated_at": today.isoformat(),
        "schema_version": "source-staleness-alerts-v1",
        "context_label": (
            "Scheduled stale-source alerts for current officials and live source lanes. "
            "Warnings identify work queues; they are not allegations or trade findings."
        ),
        "summary": {
            "alert_count": len(alerts),
            "open_warning_count": sum(1 for row in alerts if row["severity"] == "warning"),
            "high_alert_count": sum(1 for row in alerts if row["severity"] == "high"),
            "current_queue_item_count": len(current_entries),
            "reviewed_public_trade_count": reviewed_count,
        },
        "alerts": alerts,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
