from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections import Counter
from datetime import date, datetime
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


GOVINFO_PACKAGE_URL = "https://www.govinfo.gov/content/pkg/USREPORTS-{volume}.zip"
GOVINFO_PACKAGE_DETAIL_URL = "https://www.govinfo.gov/app/details/USREPORTS-{volume}"
GOVINFO_PACKAGE_METADATA_URL = "https://www.govinfo.gov/metadata/pkg/USREPORTS-{volume}/mods.xml"
GOVINFO_CASE_PDF_URL = (
    "https://www.govinfo.gov/content/pkg/USREPORTS-{volume}/pdf/{granule_id}.pdf"
)
GOVINFO_CASE_DETAIL_URL = "https://www.govinfo.gov/app/details/USREPORTS-{volume}/{granule_id}"
SUPREME_COURT_US_REPORTS_URL = "https://www.supremecourt.gov/opinions/USReports.aspx"
SUPREME_COURT_BOUND_VOLUME_URL = (
    "https://www.supremecourt.gov/opinions/boundvolumes/{volume}BV.pdf"
)
USER_AGENT = "CivicLedger U.S. Reports backfill/0.1 (+https://civic-ledger.dan-a2c.workers.dev/)"
MODS_NS = {"mods": "http://www.loc.gov/mods/v3"}
HISTORICAL_VOLUMES = tuple(range(555, 583))
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _spaced_word_pattern(value: str) -> str:
    return r"\s*".join(re.escape(character) for character in value)


HEADER_ACTIONS = "|".join(
    _spaced_word_pattern(value)
    for value in ("Argued", "Reargued", "Decided", "Submitted", "Judgment", "Decree", "Opinion")
)
DOCKET_RE = re.compile(
    rf"\bN\s*o\s*s?\.\s+(.{{1,180}}?)\.\s+(?=(?:{HEADER_ACTIONS})\b)",
    re.IGNORECASE,
)
DECISION_DATE_RE = re.compile(
    rf"\b(?:{_spaced_word_pattern('Decided')}|"
    rf"{_spaced_word_pattern('Judgment')}\s+{_spaced_word_pattern('entered')}|"
    rf"{_spaced_word_pattern('Decree')}\s+{_spaced_word_pattern('entered')})\s+"
    rf"({'|'.join(_spaced_word_pattern(month) for month in MONTH_NAMES)})"
    rf"\s+(\d{{1,2}}),\s+(\d{{4}})\b",
    re.IGNORECASE,
)


def fetch_official_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=180) as response:
        return response.read()


def _extension_value(extension: ET.Element | None, field: str) -> str | None:
    if extension is None:
        return None
    value = extension.findtext(f"mods:{field}", default="", namespaces=MODS_NS).strip()
    return value or None


def _package_term(root: ET.Element) -> int | None:
    for extension in root.findall("mods:extension", MODS_NS):
        value = _extension_value(extension, "courtTerm")
        if value and value.isdigit():
            return int(value)
    return None


def _case_name(title: str, citation: str | None) -> str:
    if not citation:
        return title
    return re.sub(rf",\s*{re.escape(citation)}(?:\s*\(\d{{4}}\))?\s*$", "", title).strip()


def parse_govinfo_mods(metadata: bytes, volume: int) -> tuple[int | None, list[dict]]:
    root = ET.fromstring(metadata)
    package_term = _package_term(root)
    cases = []
    for item in root.findall("mods:relatedItem[@type='constituent']", MODS_NS):
        extension = item.find("mods:extension", MODS_NS)
        if _extension_value(extension, "granuleClass") != "CASE":
            continue
        granule_id = _extension_value(extension, "accessId")
        citation = _extension_value(extension, "usCitation")
        title = item.findtext("mods:titleInfo/mods:title", default="", namespaces=MODS_NS).strip()
        if not granule_id or not citation or not title:
            raise ValueError(f"U.S. Reports volume {volume} contains an incomplete CASE constituent")
        term_value = _extension_value(extension, "courtTerm")
        subject_terms = sorted(
            {
                topic.text.strip()
                for topic in item.findall(".//mods:subject/mods:topic", MODS_NS)
                if topic.text and topic.text.strip()
            }
        )
        cases.append(
            {
                "volume": volume,
                "reporter_page": int(_extension_value(extension, "reportNumber") or citation.rsplit(" ", 1)[-1]),
                "granule_id": granule_id,
                "case_name": _case_name(title, citation),
                "citation": citation,
                "full_citation": _extension_value(extension, "fullCitation") or citation,
                "metadata_decision_date": _extension_value(extension, "decisionDate"),
                "term_year": int(term_value) if term_value and term_value.isdigit() else package_term,
                "subject_terms": subject_terms,
            }
        )
    return package_term, cases


def extract_pdf_header_text(pdf_content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("Install the backend pypdf dependency to build the U.S. Reports backfill") from error

    reader = PdfReader(io.BytesIO(pdf_content))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:2])


def parse_case_header(text: str) -> tuple[str | None, str | None]:
    normalized = " ".join(
        text.replace("\u00ad", "").replace("\u2010", "-").replace("\u2011", "-")
        .replace("\u2012", "-").replace("\u2013", "-").replace("\u2014", "-")
        .split()
    )
    normalized = re.sub(
        r"(?<!\d)(?:\d\s+){1,}\d(?!\d)",
        lambda match: re.sub(r"\s+", "", match.group(0)),
        normalized,
    )
    docket_match = DOCKET_RE.search(normalized)
    docket_number = None
    if docket_match:
        docket_number = docket_match.group(1).strip()
        for word in ("and", "Orig"):
            docket_number = re.sub(
                _spaced_word_pattern(word),
                word,
                docket_number,
                flags=re.IGNORECASE,
            )
        docket_number = re.sub(r"\s*([-/,])\s*", r"\1", docket_number)
        docket_number = re.sub(r"\s+", " ", docket_number).strip()
    date_match = DECISION_DATE_RE.search(normalized)
    decision_date = None
    if date_match:
        month = re.sub(r"\s+", "", date_match.group(1)).title()
        decision_date = datetime.strptime(
            f"{month} {date_match.group(2)}, {date_match.group(3)}",
            "%B %d, %Y",
        ).date().isoformat()
    return docket_number, decision_date


def build_volume_records(
    volume: int,
    package_content: bytes,
    *,
    pdf_text_extractor=extract_pdf_header_text,
) -> tuple[dict, list[dict]]:
    package_sha256 = hashlib.sha256(package_content).hexdigest()
    with zipfile.ZipFile(io.BytesIO(package_content)) as archive:
        metadata_path = f"USREPORTS-{volume}/mods.xml"
        metadata = archive.read(metadata_path)
        metadata_sha256 = hashlib.sha256(metadata).hexdigest()
        package_term, cases = parse_govinfo_mods(metadata, volume)
        records = []
        for case in cases:
            pdf_path = f"USREPORTS-{volume}/pdf/{case['granule_id']}.pdf"
            pdf_content = archive.read(pdf_path)
            docket_number, pdf_decision_date = parse_case_header(pdf_text_extractor(pdf_content))
            metadata_date = case.pop("metadata_decision_date")
            decision_date = pdf_decision_date or metadata_date
            if not decision_date:
                raise ValueError(f"No official decision date for {case['granule_id']}")
            if pdf_decision_date and metadata_date:
                date_status = (
                    "pdf_header_matches_mods"
                    if pdf_decision_date == metadata_date
                    else "pdf_header_overrides_mods"
                )
            elif pdf_decision_date:
                date_status = "pdf_header_only"
            else:
                date_status = "mods_only"
            records.append(
                {
                    **case,
                    "decision_date": decision_date,
                    "docket_number": docket_number,
                    "docket_number_status": (
                        "official_bound_pdf_header" if docket_number else "not_found_in_bound_pdf_header"
                    ),
                    "decision_date_provenance": {
                        "status": date_status,
                        "bound_pdf_header_date": pdf_decision_date,
                        "govinfo_mods_date": metadata_date,
                    },
                    "source_url": GOVINFO_CASE_PDF_URL.format(
                        volume=volume,
                        granule_id=case["granule_id"],
                    ),
                    "source_detail_url": GOVINFO_CASE_DETAIL_URL.format(
                        volume=volume,
                        granule_id=case["granule_id"],
                    ),
                    "source_metadata_url": GOVINFO_PACKAGE_METADATA_URL.format(volume=volume),
                    "source_package_url": GOVINFO_PACKAGE_URL.format(volume=volume),
                    "supreme_court_bound_volume_url": SUPREME_COURT_BOUND_VOLUME_URL.format(
                        volume=volume
                    ),
                    "source_pdf_sha256": hashlib.sha256(pdf_content).hexdigest(),
                    "source_pdf_byte_count": len(pdf_content),
                    "provenance": {
                        "publisher": "Supreme Court of the United States",
                        "distributor": "U.S. Government Publishing Office",
                        "collection": "United States Reports",
                        "source_tier": "official",
                        "metadata_extraction": "GovInfo package MODS",
                        "docket_extraction": "U.S. Reports case PDF header",
                        "package_sha256": package_sha256,
                        "metadata_sha256": metadata_sha256,
                    },
                }
            )
    snapshot = {
        "volume": volume,
        "term_year": package_term,
        "url": GOVINFO_PACKAGE_URL.format(volume=volume),
        "detail_url": GOVINFO_PACKAGE_DETAIL_URL.format(volume=volume),
        "metadata_url": GOVINFO_PACKAGE_METADATA_URL.format(volume=volume),
        "supreme_court_bound_volume_url": SUPREME_COURT_BOUND_VOLUME_URL.format(volume=volume),
        "package_sha256": package_sha256,
        "package_byte_count": len(package_content),
        "metadata_sha256": metadata_sha256,
        "case_count": len(records),
    }
    return snapshot, records


def build_supreme_court_historical_decisions(
    start_date: str = "2009-01-01",
    end_date: str = "2016-12-31",
    *,
    as_of: date | None = None,
    volumes: tuple[int, ...] = HISTORICAL_VOLUMES,
    binary_fetcher=fetch_official_bytes,
    pdf_text_extractor=extract_pdf_header_text,
) -> dict:
    if date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise ValueError("start_date cannot be after end_date")
    snapshots = []
    records = []
    for volume in volumes:
        package = binary_fetcher(GOVINFO_PACKAGE_URL.format(volume=volume))
        snapshot, volume_records = build_volume_records(
            volume,
            package,
            pdf_text_extractor=pdf_text_extractor,
        )
        included = [
            record for record in volume_records if start_date <= record["decision_date"] <= end_date
        ]
        snapshot["included_case_count"] = len(included)
        snapshots.append(snapshot)
        records.extend(included)

    records.sort(key=lambda row: (row["decision_date"], row["volume"], row["reporter_page"]))
    citation_counts = Counter(row["citation"] for row in records)
    duplicate_citations = sorted(citation for citation, count in citation_counts.items() if count > 1)
    if duplicate_citations:
        raise ValueError(f"Duplicate U.S. Reports citations: {duplicate_citations}")
    missing_dockets = [row["granule_id"] for row in records if not row["docket_number"]]
    date_conflicts = [
        row["granule_id"]
        for row in records
        if row["decision_date_provenance"]["status"] == "pdf_header_overrides_mods"
    ]
    return {
        "schema_version": "supreme-court-us-reports-decisions-v1",
        "generated_at": (as_of or date.today()).isoformat(),
        "scope": {
            "start_date": start_date,
            "end_date": end_date,
            "volume_range": [min(volumes), max(volumes)] if volumes else [],
            "record_scope": "CASE constituents in official U.S. Reports packages, filtered by decision date.",
            "exclusion": "Front matter, back matter, and dates outside the requested calendar range.",
        },
        "sources": [
            {
                "id": "supreme-court-us-reports",
                "url": SUPREME_COURT_US_REPORTS_URL,
                "publisher": "Supreme Court of the United States",
                "source_tier": "official",
            },
            {
                "id": "govinfo-us-reports-packages",
                "url": GOVINFO_PACKAGE_DETAIL_URL,
                "publisher": "U.S. Government Publishing Office",
                "source_tier": "official",
                "volume_snapshots": snapshots,
            },
        ],
        "coverage": {
            "status": "official_us_reports_calendar_2009_2016_backfilled",
            "declared_gaps": [
                {
                    "field": "docket_number",
                    "status": "not_found_in_parseable_bound_pdf_header",
                    "record_count": len(missing_dockets),
                    "granule_ids": missing_dockets,
                },
                {
                    "field": "decision_date",
                    "status": "bound_pdf_header_overrode_govinfo_mods",
                    "record_count": len(date_conflicts),
                    "granule_ids": date_conflicts,
                },
            ],
        },
        "summary": {
            "volume_count": len(snapshots),
            "decision_count": len(records),
            "decisions_by_calendar_year": dict(
                sorted(Counter(row["decision_date"][:4] for row in records).items())
            ),
            "decisions_by_term_year": dict(
                sorted(Counter(str(row["term_year"]) for row in records).items())
            ),
            "docket_number_present_count": len(records) - len(missing_dockets),
            "docket_number_missing_count": len(missing_dockets),
            "decision_date_pdf_mods_conflict_count": len(date_conflicts),
        },
        "decisions": records,
    }


def historical_decisions_for_range(path, start_date: str, end_date: str) -> tuple[list[dict], dict]:
    import json

    path_parts = path.parts
    path_label = (
        "/".join(path_parts[path_parts.index("data") :])
        if "data" in path_parts
        else path.name
    )
    if not path.exists():
        return [], {"status": "artifact_missing", "path": path_label}
    dataset = json.loads(path.read_text())
    decisions = [
        {
            "term_year": row["term_year"],
            "release_number": f"{row['volume']}-{row['reporter_page']}",
            "decision_date": row["decision_date"],
            "docket_number": row["docket_number"],
            "case_name": row["case_name"],
            "subject_terms": row.get("subject_terms") or [],
            "opinion_url": row["source_url"],
            "source_page_url": row["source_detail_url"],
            "citation": row["citation"],
            "historical_provenance": row["provenance"],
        }
        for row in dataset.get("decisions", [])
        if start_date <= row.get("decision_date", "") <= end_date
    ]
    return decisions, {
        "status": dataset.get("coverage", {}).get("status"),
        "path": path_label,
        "schema_version": dataset.get("schema_version"),
        "generated_at": dataset.get("generated_at"),
        "decision_count": len(decisions),
        "source_artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
