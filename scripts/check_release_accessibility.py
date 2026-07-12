#!/usr/bin/env python3
"""Check static Pages accessibility and responsive-layout invariants."""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "pages-site" / "index.html"
CSS_PATH = ROOT / "pages-site" / "styles.css"
FORM_CONTROLS = {"input", "select", "textarea"}
LANDMARKS = {"header", "main", "nav", "footer"}
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class CheckError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


class StaticPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.elements: list[tuple[str, dict[str, str]]] = []
        self.controls: list[tuple[str, dict[str, str], bool]] = []
        self.label_targets: set[str] = set()
        self.headings: list[int] = []
        self.button_stack: list[list[str]] = []
        self.button_names: list[str] = []
        self.landmarks: list[tuple[str, dict[str, str]]] = []
        self._open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        self.elements.append((tag, attrs))
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag in LANDMARKS:
            self.landmarks.append((tag, attrs))
        if tag == "label" and attrs.get("for"):
            self.label_targets.add(attrs["for"])
        if tag in FORM_CONTROLS:
            self.controls.append((tag, attrs, "label" in self._open_tags))
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        if tag == "button":
            self.button_stack.append([])
        if tag not in VOID_ELEMENTS:
            self._open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self.button_stack:
            self.button_names.append(" ".join(self.button_stack.pop()).strip())
        for index in range(len(self._open_tags) - 1, -1, -1):
            if self._open_tags[index] == tag:
                del self._open_tags[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.button_stack and data.strip():
            self.button_stack[-1].append(data.strip())


def validate_accessibility() -> dict[str, int]:
    html = HTML_PATH.read_text()
    css = CSS_PATH.read_text()
    parser = StaticPageParser()
    parser.feed(html)

    require('<html lang="en">' in html, "The document must declare its language")
    require(re.search(r"<title>\s*\S.+?</title>", html, re.DOTALL) is not None, "A non-empty page title is required")
    require('name="viewport"' in html, "A viewport meta tag is required")
    require('name="description"' in html, "A page description is required")
    require(len(parser.ids) == len(set(parser.ids)), "HTML IDs must be unique")

    landmark_counts = {tag: sum(1 for found, _attrs in parser.landmarks if found == tag) for tag in LANDMARKS}
    require(landmark_counts == {"header": 1, "main": 1, "nav": 1, "footer": 1}, "Page landmarks must be unique and complete")
    nav = next(attrs for tag, attrs in parser.landmarks if tag == "nav")
    require(bool(nav.get("aria-label")), "Primary navigation needs an accessible name")

    require(parser.headings and parser.headings[0] == 1, "The first heading must be h1")
    require(parser.headings.count(1) == 1, "The page must have exactly one h1")
    for previous, current in zip(parser.headings, parser.headings[1:]):
        require(current <= previous + 1, f"Heading level skips from h{previous} to h{current}")

    id_set = set(parser.ids)
    for tag, attrs, wrapped_by_label in parser.controls:
        if attrs.get("type") == "hidden":
            continue
        control_id = attrs.get("id", "")
        require(
            wrapped_by_label or control_id in parser.label_targets or bool(attrs.get("aria-label")),
            f"Unlabelled {tag}: {control_id or '<no id>'}",
        )
    for tag, attrs in parser.elements:
        for attribute in ("aria-controls", "aria-describedby", "aria-labelledby"):
            for referenced_id in attrs.get(attribute, "").split():
                require(referenced_id in id_set, f"{tag} {attribute} references missing ID {referenced_id}")
        if attrs.get("role") == "img":
            require(bool(attrs.get("aria-label") or attrs.get("aria-labelledby")), "Chart image role needs an accessible name")
        if attrs.get("aria-live"):
            require(attrs["aria-live"] in {"polite", "assertive", "off"}, f"Invalid aria-live value on {tag}")

    button_elements = [attrs for tag, attrs in parser.elements if tag == "button"]
    require(len(button_elements) == len(parser.button_names), "Button parsing did not reconcile")
    for attrs, text_name in zip(button_elements, parser.button_names):
        require(bool(text_name or attrs.get("aria-label") or attrs.get("aria-labelledby")), "Every button needs an accessible name")

    require('class="chart-alternative"' in html, "The visual chart needs a textual alternative region")
    require('<th ' in html and '<tbody id="transactionRows">' in html, "The transaction table needs header cells and a body")
    require(':focus-visible' in css, "Keyboard focus styling is required")
    require('@media (prefers-reduced-motion: reduce)' in css, "Reduced-motion support is required")

    # Responsive invariants prevent the dense workbench from forcing page-level horizontal scrolling.
    require("box-sizing: border-box" in css, "Global border-box sizing is required")
    require(re.search(r"body\s*\{[^}]*min-width:\s*320px", css, re.DOTALL) is not None, "Body needs a 320px minimum viewport contract")
    require(re.search(r"body\s*\{[^}]*overflow-x:\s*(?:clip|hidden)", css, re.DOTALL) is not None, "Body must contain horizontal overflow")
    require("@media (max-width: 1120px)" in css, "Tablet layout breakpoint is missing")
    mobile = re.search(r"@media \(max-width: 760px\)\s*\{(?P<body>.*)\n\}", css, re.DOTALL)
    require(mobile is not None, "Mobile layout breakpoint is missing")
    mobile_css = mobile.group("body")
    for selector in (".section-intro", ".selection-row", ".toolbar", ".detail-layout"):
        require(selector in mobile_css, f"Mobile layout does not adapt {selector}")
    require(mobile_css.count("grid-template-columns: 1fr") >= 4, "Mobile controls must collapse to one-column layouts")
    require(re.search(r"\.table-scroll\s*\{[^}]*overflow:\s*(?:auto|scroll)", css, re.DOTALL) is not None, "Wide tables need a contained scroll region")

    return {
        "controls": len(parser.controls),
        "headings": len(parser.headings),
        "html_ids": len(parser.ids),
        "landmarks": len(parser.landmarks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        summary = validate_accessibility()
    except (OSError, CheckError) as exc:
        raise SystemExit(f"Release accessibility validation failed: {exc}") from exc
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("Release accessibility validation passed: " + ", ".join(f"{key}={value}" for key, value in summary.items()))


if __name__ == "__main__":
    main()
