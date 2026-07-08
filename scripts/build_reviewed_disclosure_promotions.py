#!/usr/bin/env python3
"""Build reviewed promotion artifact from parser fixtures without inventing production trades."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.parsers import get_parser


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "parsers" / "oge_278t.csv"
OUTPUT = ROOT / "data" / "disclosures" / "reviewed_disclosure_promotions.json"


def build_dataset() -> dict:
    content = FIXTURE.read_bytes()
    parser = get_parser("oge-individual-disclosures")
    preview = parser.preview(content, filename=FIXTURE.name, content_type="text/csv")
    promotions = []
    for index, transaction in enumerate(preview.transactions, start=1):
        row = transaction.to_dict()
        promotions.append(
            {
                "promotion_id": f"fixture-oge-reviewed-{index:03d}",
                "source_id": "oge-individual-disclosures",
                "fixture_path": str(FIXTURE.relative_to(ROOT)),
                "filer_name": preview.filer_name,
                "report_type": preview.report_type,
                "filing_date": preview.filing_date,
                "asset_display_name": row["asset"],
                "ticker": row["ticker"],
                "action": row["transaction_type"],
                "trade_date": row["transaction_date"],
                "value_range_label": row["amount"],
                "parser_confidence": row["confidence"],
                "field_confidence": row["field_confidence"],
                "review_status": "reviewed_fixture_promotion",
                "record_status": "reviewed_fixture_not_public_production",
                "confidence_label": "Reviewed fixture promotion; not a public production official trade",
                "public_production_trade": False,
                "review_required_before_public_trade": True,
            }
        )
    return {
        "generated_at": date.today().isoformat(),
        "schema_version": "reviewed-disclosure-promotions-v1",
        "context_label": (
            "Promotion workflow proof using parser fixtures. These rows verify review mechanics "
            "and are not public production official trade records."
        ),
        "summary": {
            "reviewed_fixture_promotion_count": len(promotions),
            "public_production_trade_count": 0,
            "review_required_before_public_trade": True,
        },
        "promotions": promotions,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_dataset(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
