#!/usr/bin/env python3
"""Write a privacy-safe refresh health record for the public static site."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "pages-site" / "refresh-status.json"
ALLOWED_STATUSES = {"success", "failure", "cancelled", "skipped", "unknown"}


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_status(
    status: str,
    *,
    run_id: str | None = None,
    run_url: str | None = None,
    commit: str | None = None,
    generated_at: str | None = None,
) -> dict:
    normalized = status.strip().lower()
    if normalized not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported refresh status: {status}")

    healthy = normalized == "success"
    if healthy:
        headline = "Daily source refresh completed"
        message = "The explorer is serving the latest dataset that passed the automated release gates."
    elif normalized == "unknown":
        headline = "Refresh health not yet recorded"
        message = "Use each record's source and evidence status before relying on the dataset."
    else:
        headline = "Latest daily refresh did not complete"
        message = (
            "The explorer is serving the last validated dataset. Do not treat it as current until "
            "the next successful refresh."
        )

    return {
        "schema_version": "civicledger-refresh-status-v1",
        "status": normalized,
        "healthy": healthy,
        "headline": headline,
        "message": message,
        "generated_at": generated_at or iso_utc_now(),
        "run_id": run_id or None,
        "run_url": run_url or None,
        "commit": commit or None,
        "interpretation_boundary": (
            "Refresh health describes pipeline execution, not completeness, correctness, misconduct, "
            "or the absence of reportable transactions."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", required=True, choices=sorted(ALLOWED_STATUSES))
    parser.add_argument("--run-id")
    parser.add_argument("--run-url")
    parser.add_argument("--commit")
    parser.add_argument("--generated-at")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payload = build_status(
        args.status,
        run_id=args.run_id,
        run_url=args.run_url,
        commit=args.commit,
        generated_at=args.generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {args.output} with refresh status {payload['status']}")


if __name__ == "__main__":
    main()
