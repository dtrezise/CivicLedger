#!/usr/bin/env python3
"""Validate the dependency-free interaction and URL-state contract for Pages."""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "pages-site"


class CheckError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.stylesheets.append(attrs.get("href", ""))


def validate_static_contract() -> dict[str, int]:
    html = (SITE / "index.html").read_text()
    javascript = (SITE / "app.js").read_text()
    parser = AssetParser()
    parser.feed(html)

    local_assets = [value for value in parser.scripts + parser.stylesheets if value.startswith("./")]
    for asset in local_assets:
        require((SITE / asset.removeprefix("./")).is_file(), f"Missing local static asset: {asset}")
    require(any("echarts@5.6.0" in script for script in parser.scripts), "Chart dependency must be version-pinned")
    require("./data/manifest.json" in javascript, "The app must bootstrap through the public manifest")
    require("civicledger-static.json" not in javascript, "The legacy monolith must not enter the runtime path")

    referenced_ids = set(re.findall(r'\$\("([A-Za-z][A-Za-z0-9_-]*)"\)', javascript))
    require(referenced_ids <= parser.ids, f"JavaScript references missing IDs: {sorted(referenced_ids - parser.ids)}")

    control_contract = {
        "officialSearch": ("input", "focus"),
        "officialResults": ("click",),
        "eventSearch": ("input", "focus"),
        "eventResults": ("click",),
        "selectedOfficials": ("click",),
        "assetFilter": ("change",),
        "eventTierFilter": ("change",),
        "eventWindowFilter": ("change",),
        "resetViewButton": ("click",),
        "transactionRows": ("click", "keydown"),
        "eventDetail": ("click",),
    }
    for control_id, event_names in control_contract.items():
        require(control_id in parser.ids, f"Required interaction control is missing: {control_id}")
        for event_name in event_names:
            pattern = rf'\$\("{re.escape(control_id)}"\)\.addEventListener\("{event_name}"'
            require(re.search(pattern, javascript) is not None, f"{control_id} is not wired for {event_name}")
    roster_controls = {"branchFilter", "chamberFilter", "stateFilter", "districtFilter", "partyFilter", "servicePeriodFilter"}
    require(roster_controls <= parser.ids, f"Roster filters are incomplete: {sorted(roster_controls - parser.ids)}")
    require(
        all(f'"{control_id}"' in javascript for control_id in roster_controls)
        and '$(id).addEventListener("change"' in javascript,
        "Roster filters must share change-event wiring",
    )

    for function_name in ("parseUrlState", "syncUrl", "loadData", "loadSelectedTimelines", "renderWorkbench", "selectTrade", "selectEvent", "setMode"):
        require(re.search(rf"function\s+{function_name}\s*\(", javascript) is not None or re.search(rf"async function\s+{function_name}\s*\(", javascript) is not None, f"Missing interaction function: {function_name}")

    parsed_params = set(re.findall(r'params\.get\("([a-z]+)"\)', javascript))
    written_params = set(re.findall(r'params\.set\("([a-z]+)"', javascript))
    core_params = {"officials", "mode", "asset", "event", "context", "window"}
    roster_params = {"branch", "chamber", "state", "district", "party", "service", "office"}
    required_params = core_params | roster_params | {"zoom"}
    require(required_params <= parsed_params, f"URL parser is missing hooks: {sorted(required_params - parsed_params)}")
    require(core_params | {"zoom"} <= written_params, f"URL writer is missing hooks: {sorted((core_params | {'zoom'}) - written_params)}")
    require("Object.entries(state.rosterFilters)" in javascript and "params.set(key, value)" in javascript, "Roster filters must serialize into URL state")
    require('history.replaceState(null, ""' in javascript, "URL state must update without a page navigation")
    require("location.pathname" in javascript and "location.hash" in javascript, "URL synchronization must preserve route and anchor")
    require("syncUrl();" in javascript, "Workbench rendering must synchronize shareable URL state")
    require(".slice(0, 4)" in javascript, "Comparison selection needs a stable four-official ceiling")

    require('$(`transactionRows`).addEventListener' not in javascript, "Unexpected dynamic selector in keyboard contract")
    require('$(' + '"transactionRows"' + ').addEventListener("keydown"' in javascript, "Transaction rows need keyboard activation")
    require('["Enter", " "].includes(event.key)' in javascript, "Keyboard activation must support Enter and Space")
    require('event.preventDefault()' in javascript, "Space activation must prevent page scrolling")
    require('setAttribute("aria-expanded"' in javascript, "Combobox result visibility must update aria-expanded")
    require('aria-selected="${' in javascript, "Dynamic choices must expose selected state")
    require('setAttribute("aria-busy"' in javascript, "Chart loading must expose busy state")

    require('window.addEventListener("resize"' in javascript, "Charts need responsive resize handling")
    require("state.tradeChart?.resize()" in javascript, "Trade chart is not resized responsively")
    require("state.marketChart?.resize()" in javascript, "Market chart is not resized responsively")
    require('state.tradeChart.on("click"' in javascript and 'state.tradeChart.on("datazoom"' in javascript, "Chart click and zoom interactions are required")
    require("try {" in javascript and "catch (error)" in javascript, "Dataset bootstrap needs a visible failure path")
    require("fetch(path, { cache: \"no-store\" })" in javascript, "Generated data fetches must avoid stale browser caches")

    return {
        "dom_hooks": len(referenced_ids),
        "interaction_controls": len(control_contract),
        "local_assets": len(local_assets),
        "url_parameters": len(required_params),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        summary = validate_static_contract()
    except (OSError, CheckError) as exc:
        raise SystemExit(f"Static interaction contract failed: {exc}") from exc
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("Static interaction contract passed: " + ", ".join(f"{key}={value}" for key, value in summary.items()))


if __name__ == "__main__":
    main()
