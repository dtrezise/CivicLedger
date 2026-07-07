#!/usr/bin/env python3
"""Build a source-status index for presidential OGE disclosure ingestion."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "disclosures" / "presidential_oge_disclosure_status.json"

OGE_DISCLOSURE_COLLECTION = (
    "https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm="
)
OGE_DISCLOSURE_FAQ = "https://www.oge.gov/web/oge.nsf/publicresources_disclosure-faq"
OGE_FINANCIAL_DISCLOSURE = "https://www.oge.gov/web/oge.nsf/ethicsofficials_financial-disc"


PRESIDENTIAL_DISCLOSURE_STATUS = [
    {
        "official_id": "exec:barack-obama",
        "full_name": "Barack Obama",
        "presidential_term": "obama-44",
        "term_label": "Obama 44",
        "service_start": "2009-01-20",
        "service_end": "2017-01-20",
        "source_status": "historical_request_or_archive_required",
        "reviewed_trade_count": 0,
        "expected_forms": ["OGE Form 278e", "OGE Form 278-T"],
        "availability_note": (
            "Historical presidential public financial disclosure records may require "
            "official archive review or OGE Form 201/agency request workflows."
        ),
    },
    {
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-45",
        "term_label": "Trump 45",
        "service_start": "2017-01-20",
        "service_end": "2021-01-20",
        "source_status": "oge_collection_search_required",
        "reviewed_trade_count": 0,
        "expected_forms": ["OGE Form 278e", "OGE Form 278-T"],
        "availability_note": (
            "OGE individual disclosures should be searched and archived before "
            "any normalized presidential trade rows are promoted."
        ),
    },
    {
        "official_id": "exec:joseph-r-biden",
        "full_name": "Joseph R. Biden",
        "presidential_term": "biden-46",
        "term_label": "Biden 46",
        "service_start": "2021-01-20",
        "service_end": "2025-01-20",
        "source_status": "oge_collection_search_required",
        "reviewed_trade_count": 0,
        "expected_forms": ["OGE Form 278e", "OGE Form 278-T"],
        "availability_note": (
            "OGE individual disclosures should be searched and archived before "
            "any normalized presidential trade rows are promoted."
        ),
    },
    {
        "official_id": "exec:donald-j-trump",
        "full_name": "Donald J. Trump",
        "presidential_term": "trump-47",
        "term_label": "Trump 47",
        "service_start": "2025-01-20",
        "service_end": None,
        "source_status": "live_tracking_required",
        "reviewed_trade_count": 0,
        "expected_forms": ["OGE Form 278e", "OGE Form 278-T"],
        "availability_note": (
            "Current-term disclosures require scheduled OGE collection review "
            "and reviewer promotion before becoming production trade rows."
        ),
    },
]


def build_dataset() -> dict:
    status_counts = Counter(row["source_status"] for row in PRESIDENTIAL_DISCLOSURE_STATUS)
    return {
        "generated_at": date.today().isoformat(),
        "schema_version": "presidential-oge-disclosure-status-v1",
        "context_label": (
            "Presidential OGE disclosure status records identify source readiness only. "
            "They are not trade records and do not imply any transaction activity."
        ),
        "source": {
            "id": "oge-individual-disclosures",
            "name": "OGE Officials' Individual Disclosures",
            "collection_url": OGE_DISCLOSURE_COLLECTION,
            "faq_url": OGE_DISCLOSURE_FAQ,
            "financial_disclosure_url": OGE_FINANCIAL_DISCLOSURE,
            "source_tier": "official",
        },
        "ingestion_policy": {
            "raw_document_required": True,
            "review_required_before_public_trade": True,
            "parser_source_id": "oge-individual-disclosures",
            "preserve_use_restrictions": True,
            "supported_forms": ["OGE Form 278e", "OGE Form 278-T"],
        },
        "summary": {
            "official_status_count": len(PRESIDENTIAL_DISCLOSURE_STATUS),
            "reviewed_trade_count": sum(row["reviewed_trade_count"] for row in PRESIDENTIAL_DISCLOSURE_STATUS),
            "source_status_counts": dict(sorted(status_counts.items())),
        },
        "officials": PRESIDENTIAL_DISCLOSURE_STATUS,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
