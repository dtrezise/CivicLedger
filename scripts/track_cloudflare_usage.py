#!/usr/bin/env python3
"""Capture Workers request metrics and the current static transfer footprint."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSET_REPORT = ROOT / "docs" / "metrics" / "cloudflare_asset_baseline.json"


class UsageError(RuntimeError):
    pass


def iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def query_workers(token: str, account_id: str, script_name: str, start: datetime, end: datetime) -> list[dict]:
    query = """
query CivicLedgerWorkersUsage($accountTag: string, $datetimeStart: string, $datetimeEnd: string, $scriptName: string) {
  viewer {
    accounts(filter: {accountTag: $accountTag}) {
      workersInvocationsAdaptive(
        limit: 10000
        filter: {
          scriptName: $scriptName
          datetime_geq: $datetimeStart
          datetime_leq: $datetimeEnd
        }
      ) {
        dimensions { datetime scriptName status }
        sum { errors requests subrequests }
      }
    }
  }
}
"""
    payload = json.dumps(
        {
            "query": query,
            "variables": {
                "accountTag": account_id,
                "datetimeStart": iso(start),
                "datetimeEnd": iso(end),
                "scriptName": script_name,
            },
        }
    ).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "CivicLedger-Cloudflare-Usage/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UsageError(f"Cloudflare GraphQL request failed: {exc}") from exc
    if result.get("errors"):
        messages = "; ".join(error.get("message", "Unknown GraphQL error") for error in result["errors"])
        raise UsageError(messages)
    accounts = result.get("data", {}).get("viewer", {}).get("accounts", [])
    if not accounts:
        raise UsageError("Cloudflare returned no matching account analytics scope")
    return accounts[0].get("workersInvocationsAdaptive", [])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default=os.getenv("CLOUDFLARE_ACCOUNT_ID"))
    parser.add_argument("--api-token", default=os.getenv("CLOUDFLARE_ANALYTICS_TOKEN"))
    parser.add_argument("--script-name", default="civic-ledger")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--asset-report", type=Path, default=DEFAULT_ASSET_REPORT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    if not args.account_id or not args.api_token:
        raise SystemExit("Cloudflare usage tracking requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_ANALYTICS_TOKEN.")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    try:
        rows = query_workers(args.api_token, args.account_id, args.script_name, start, end)
        asset_payload = json.loads(args.asset_report.read_text())
    except (OSError, json.JSONDecodeError, UsageError) as exc:
        raise SystemExit(f"Cloudflare usage tracking failed: {exc}") from exc
    sums = {"errors": 0, "requests": 0, "subrequests": 0}
    for row in rows:
        for key in sums:
            sums[key] += int(row.get("sum", {}).get(key, 0) or 0)
    current_assets = asset_payload.get("current", asset_payload)
    report = {
        "bandwidth": {
            "measured_bytes": None,
            "status": "awaiting_custom_zone",
            "reason": (
                "Cloudflare exposes exact visitor data-transfer bytes through zone analytics. "
                "The current workers.dev-only deployment has no zone scope."
            ),
        },
        "generated_at": iso(end),
        "period": {"days": args.days, "end": iso(end), "start": iso(start)},
        "requests": sums,
        "schema_version": "civicledger-cloudflare-usage-v1",
        "script_name": args.script_name,
        "static_assets": {
            "asset_count": current_assets.get("asset_count"),
            "full_corpus_transfer_bytes": current_assets.get("total_asset_bytes"),
            "largest_asset_bytes": current_assets.get("largest_asset_bytes"),
            "request_billing": "free_and_unlimited_static_assets",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        print("### Cloudflare usage window")
        print("")
        print("| Measure | Value |")
        print("| --- | ---: |")
        print(f"| Worker requests | {sums['requests']:,} |")
        print(f"| Worker errors | {sums['errors']:,} |")
        print(f"| Worker subrequests | {sums['subrequests']:,} |")
        print(f"| Static corpus bytes | {int(current_assets.get('total_asset_bytes', 0)):,} |")
        print("| Exact transfer bytes | Awaiting custom zone |")
    else:
        print(f"Cloudflare usage report written for {args.days} days and {sums['requests']:,} requests")


if __name__ == "__main__":
    main()
