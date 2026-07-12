#!/usr/bin/env python3
"""Build a review-gated Senate eFD PTR index with official roster matching."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.senate_disclosures import (  # noqa: E402
    MIN_REQUEST_INTERVAL_SECONDS,
    SENATE_ONLINE_START_DATE,
    SenateDisclosurePortalClient,
    SenatePortalAccessError,
    SenateTermsAcknowledgementRequired,
    VALIDATION_BIOGUIDE_ID,
    build_senate_ptr_index,
    combine_search_acquisitions,
    load_search_import_manifest,
    meaningful_name_tokens,
    search_import_manifest,
    senate_roles,
)


PUBLIC_OFFICIALS = ROOT / "data" / "public_officials" / "public_official_roles.json"
OUTPUT = ROOT / "data" / "disclosures" / "senate_disclosure_index.json"


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an ISO date (YYYY-MM-DD)") from exc


def selected_senators(public_officials: dict, bioguide_ids: set[str]) -> list[dict]:
    selected = {}
    for role in senate_roles(public_officials):
        bioguide_id = role.get("source_metadata", {}).get("bioguide_id")
        if bioguide_id not in bioguide_ids:
            continue
        congress = int(role["source_metadata"]["congress_number"])
        previous = selected.get(bioguide_id)
        if previous is None or congress > previous[0]:
            selected[bioguide_id] = (congress, role)
    missing = sorted(bioguide_ids - set(selected))
    if missing:
        raise ValueError(f"No 111th-119th Congress Senate role found for: {', '.join(missing)}")
    return [selected[bioguide_id][1] for bioguide_id in sorted(selected)]


def portal_name_query(role: dict) -> tuple[str, str]:
    tokens = meaningful_name_tokens(role.get("full_name"))
    if len(tokens) < 2:
        raise ValueError(f"Cannot derive a portal name query from {role.get('full_name')!r}")
    return tokens[0], tokens[-1]


def imported_query_dates(acquisition) -> tuple[date, date]:
    def request_date(value: str) -> date:
        text = value.split()[0]
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        raise ValueError(f"unrecognized request date: {value}")

    bounds = set()
    for record in acquisition.response_records:
        request = record.get("request", {})
        start_value = request.get("submitted_start_date")
        end_value = request.get("submitted_end_date")
        if not start_value or not end_value:
            raise ValueError(
                "Imported Senate search responses must record submitted_start_date and submitted_end_date"
            )
        try:
            start_date = request_date(start_value)
            end_date = request_date(end_value)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("Imported Senate search request dates are not in a recognized format") from exc
        bounds.add((start_date, end_date))
    if len(bounds) != 1:
        raise ValueError("Imported Senate search responses do not share one query date range")
    return next(iter(bounds))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "If live access is unavailable, use --import-manifest with a hash-backed "
            "senate-disclosure-import-v1 capture. --export-manifest writes that format after a live run."
        ),
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--bioguide-id",
        action="append",
        help=f"Senator Bioguide ID to query; repeat as needed (default: {VALIDATION_BIOGUIDE_ID}).",
    )
    scope.add_argument(
        "--all-senators",
        action="store_true",
        help="Query all Senator and former-Senator PTR rows, then match across Congresses 111-119.",
    )
    parser.add_argument("--start-date", type=iso_date, default=SENATE_ONLINE_START_DATE)
    parser.add_argument("--end-date", type=iso_date, default=date.today())
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument(
        "--request-interval",
        type=float,
        default=MIN_REQUEST_INTERVAL_SECONDS,
        help=f"Seconds between portal requests; cannot be below {MIN_REQUEST_INTERVAL_SECONDS:.1f}.",
    )
    parser.add_argument(
        "--acknowledge-senate-terms",
        action="store_true",
        help="Confirm review and acceptance of the official portal's prohibited-use acknowledgement.",
    )
    parser.add_argument(
        "--import-manifest",
        type=Path,
        help="Use captured official search responses instead of live portal access.",
    )
    parser.add_argument(
        "--export-manifest",
        type=Path,
        help="Write exact live response bodies and hashes in the reproducible import format.",
    )
    args = parser.parse_args()
    if args.start_date < SENATE_ONLINE_START_DATE:
        parser.error(f"--start-date cannot be before {SENATE_ONLINE_START_DATE}")
    if args.start_date > args.end_date:
        parser.error("--start-date cannot be after --end-date")
    if not 1 <= args.page_size <= 100:
        parser.error("--page-size must be between 1 and 100")
    if args.request_interval < MIN_REQUEST_INTERVAL_SECONDS:
        parser.error(
            f"--request-interval cannot be below {MIN_REQUEST_INTERVAL_SECONDS:.1f} seconds"
        )
    if args.import_manifest and args.export_manifest:
        parser.error("--export-manifest is only available for live acquisition")

    public_officials = json.loads(PUBLIC_OFFICIALS.read_text())
    selected_bioguide_ids = None if args.all_senators else set(
        args.bioguide_id or [VALIDATION_BIOGUIDE_ID]
    )
    coverage_mode = "all_111th_119th_senators" if args.all_senators else "selected_senator_validation"

    try:
        query_start_date = args.start_date
        query_end_date = args.end_date
        if args.import_manifest:
            acquisition = load_search_import_manifest(args.import_manifest.read_bytes())
            query_start_date, query_end_date = imported_query_dates(acquisition)
        else:
            client = SenateDisclosurePortalClient(
                terms_acknowledged=args.acknowledge_senate_terms,
                request_interval_seconds=args.request_interval,
            )
            if args.all_senators:
                acquisition = client.search_ptr_reports(
                    start_date=args.start_date,
                    end_date=args.end_date,
                    page_size=args.page_size,
                )
            else:
                acquisitions = []
                for role in selected_senators(public_officials, selected_bioguide_ids or set()):
                    first_name, last_name = portal_name_query(role)
                    acquisitions.append(
                        client.search_ptr_reports(
                            first_name=first_name,
                            last_name=last_name,
                            start_date=args.start_date,
                            end_date=args.end_date,
                            page_size=args.page_size,
                        )
                    )
                acquisition = combine_search_acquisitions(acquisitions)

        dataset = build_senate_ptr_index(
            public_officials,
            acquisition,
            start_date=query_start_date,
            end_date=query_end_date,
            coverage_mode=coverage_mode,
            selected_bioguide_ids=selected_bioguide_ids,
            request_interval_seconds=(
                None if acquisition.acquisition_mode == "import_manifest" else args.request_interval
            ),
        )
    except (OSError, ValueError, SenatePortalAccessError, SenateTermsAcknowledgementRequired) as exc:
        raise SystemExit(
            f"Senate disclosure index acquisition failed: {type(exc).__name__}: {exc}\n"
            "No synthetic rows were written. Use --import-manifest with a hash-backed "
            "senate-disclosure-import-v1 capture if acknowledged browser access is required."
        ) from exc

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT}")
    if args.export_manifest:
        args.export_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.export_manifest.write_text(
            json.dumps(search_import_manifest(acquisition), indent=2, sort_keys=True) + "\n"
        )
        print(f"Wrote {args.export_manifest}")


if __name__ == "__main__":
    main()
