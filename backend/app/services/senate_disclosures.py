from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


SENATE_SOURCE_ID = "senate-public-financial-disclosure"
SENATE_PORTAL_BASE_URL = "https://efdsearch.senate.gov"
SENATE_HOME_URL = f"{SENATE_PORTAL_BASE_URL}/search/home/"
SENATE_SEARCH_URL = f"{SENATE_PORTAL_BASE_URL}/search/"
SENATE_REPORT_DATA_URL = f"{SENATE_PORTAL_BASE_URL}/search/report/data/"
SENATE_TERMS_URL = SENATE_HOME_URL
SENATE_ONLINE_START_DATE = date(2012, 1, 1)
SENATE_CONGRESS_START = 111
SENATE_CONGRESS_END = 119
SENATE_PTR_REPORT_TYPE = 11
SENATE_MEMBER_FILER_TYPES = (1, 5)
MIN_REQUEST_INTERVAL_SECONDS = 1.0
VALIDATION_BIOGUIDE_ID = "F000062"
USER_AGENT = "CivicLedger research crawler/0.2 (+https://github.com/dtrezise/CivicLedger)"
IMPORT_SCHEMA_VERSION = "senate-disclosure-import-v1"

REPORT_PATH_RE = re.compile(
    r"^/search/view/(?P<view_kind>ptr|paper)/(?P<report_uuid>[0-9a-f-]{36})/$",
    re.IGNORECASE,
)
NAME_NOISE = {"hon", "honorable", "jr", "sr", "ii", "iii", "iv", "md", "phd", "esq"}
VALUE_RANGES = {
    "$1,001 - $15,000": (1001, 15000),
    "$15,001 - $50,000": (15001, 50000),
    "$50,001 - $100,000": (50001, 100000),
    "$100,001 - $250,000": (100001, 250000),
    "$250,001 - $500,000": (250001, 500000),
    "$500,001 - $1,000,000": (500001, 1000000),
    "$1,000,001 - $5,000,000": (1000001, 5000000),
    "$5,000,001 - $25,000,000": (5000001, 25000000),
    "$25,000,001 - $50,000,000": (25000001, 50000000),
    "Over $50,000,000": (50000001, None),
}


class SenateTermsAcknowledgementRequired(RuntimeError):
    pass


class SenatePortalAccessError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        source_url: str,
        status_code: int | None = None,
        retry_after: str | None = None,
    ):
        super().__init__(message)
        self.source_url = source_url
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class PortalResponse:
    source_url: str
    final_url: str
    body: bytes
    content_type: str
    status_code: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True)
class SenateSearchAcquisition:
    rows: list[list[str]]
    response_records: list[dict]
    retrieved_at: str
    acquisition_mode: str = "live_portal"
    import_manifest_sha256: str | None = None


@dataclass(frozen=True)
class SenateReportPage:
    source_url: str
    body: bytes
    content_type: str
    status_code: int
    retrieved_at: str
    acquisition_mode: str = "live_portal"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True)
class ParsedSenateReport:
    report_title: str | None
    filer_name: str | None
    filing_date: str | None
    transactions: list[dict]
    media_urls: list[str]
    rejected_rows: list[dict]
    layout_metadata: dict


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name(value: str | None) -> str:
    ascii_value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def meaningful_name_tokens(value: str | None) -> list[str]:
    return [token for token in normalize_name(value).split() if token not in NAME_NOISE]


def parse_portal_date(value: str) -> date:
    return datetime.strptime(clean_text(value), "%m/%d/%Y").date()


def canonical_amount(value: str) -> str:
    normalized = clean_text(value).replace("$ ", "$")
    numbers = re.findall(r"\d[\d,]*", normalized)
    if len(numbers) >= 2:
        return f"${numbers[0]} - ${numbers[1]}"
    if numbers and re.search(r"over|more than|\+", normalized, re.IGNORECASE):
        return f"Over ${numbers[0]}"
    return normalized


def value_range(value: str) -> tuple[int | None, int | None, str]:
    label = canonical_amount(value)
    if label in VALUE_RANGES:
        minimum, maximum = VALUE_RANGES[label]
        return minimum, maximum, label
    numbers = [int(number.replace(",", "")) for number in re.findall(r"\d[\d,]*", label)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1], label
    if numbers and label.lower().startswith("over"):
        return numbers[0] + 1, None, label
    return None, None, label


def normalize_action(value: str) -> str:
    lowered = clean_text(value).lower()
    if "purchase" in lowered or lowered == "buy":
        return "BUY"
    if "sale" in lowered or "sold" in lowered or lowered == "sell":
        return "SELL"
    if "exchange" in lowered:
        return "EXCHANGE"
    return "OTHER"


def senate_transaction_signature(row: dict) -> str:
    identity = "|".join(
        clean_text(str(row.get(key) or "")).casefold()
        for key in (
            "official_id",
            "trade_date",
            "action",
            "owner",
            "asset_display_name",
            "ticker",
            "value_range_label",
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def senate_document_family_key(document: dict) -> str:
    title = normalize_name(document.get("portal_report_title") or document.get("report_type"))
    title = re.sub(r"\b(amended|amendment|corrected|correction)\b", "", title).strip()
    identity = document.get("official_id") or normalize_name(document.get("filer_name"))
    value = "|".join([str(identity), title, str(document.get("filing_date") or "")])
    return f"senate-family-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def senate_ocr_priority_record(document: dict, *, as_of: date) -> dict | None:
    """Build a metadata-only OCR work item for an official Senate paper filing."""
    if document.get("parser_status") != "paper_images_review_required":
        return None

    source_url = str(document.get("source_url") or "")
    parsed_url = urlparse(source_url)
    official_url = (
        parsed_url.scheme == "https"
        and parsed_url.netloc == "efdsearch.senate.gov"
        and bool(REPORT_PATH_RE.fullmatch(parsed_url.path))
    )
    source_hash = str(document.get("source_page_sha256") or "").lower()
    hash_verified = bool(re.fullmatch(r"[0-9a-f]{64}", source_hash))
    identity_verified = (
        document.get("match_status") == "matched"
        and bool(document.get("official_id"))
        and int(document.get("match_score") or 0) >= 8
        and document.get("page_identity_consistent") is not False
    )
    media_urls = sorted(set(document.get("source_media_urls") or []))
    media_manifested = bool(media_urls) and all(
        urlparse(url).scheme == "https"
        and urlparse(url).netloc == "efd-media-public.senate.gov"
        for url in media_urls
    )
    filing_date = date.fromisoformat(document["filing_date"])
    age_days = max(0, (as_of - filing_date).days)
    recency_points = 15 if age_days <= 365 else 10 if age_days <= 1095 else 5
    checks = {
        "official_source_url": official_url,
        "source_page_sha256_present": hash_verified,
        "filer_identity_deterministically_matched": identity_verified,
        "official_media_manifest_present": media_manifested,
    }
    evidence_score = (
        (25 if official_url else 0)
        + (20 if hash_verified else 0)
        + (20 if identity_verified else 0)
        + (20 if media_manifested else 0)
        + recency_points
    )
    eligible = all(checks.values())
    return {
        "document_id": document["document_id"],
        "source_id": document.get("source_id"),
        "chamber": "Senate",
        "official_id": document.get("official_id"),
        "official_name": document.get("official_name"),
        "filing_date": document["filing_date"],
        "source_url": source_url,
        "source_page_sha256": source_hash or None,
        "source_media_urls": media_urls,
        "source_page_count": len(media_urls),
        "source_byte_count": int(document.get("source_page_byte_count") or 0),
        "priority_score": evidence_score,
        "priority_tier": "highest_confidence" if eligible and evidence_score >= 90 else "evidence_gap",
        "eligibility_checks": checks,
        "eligible_for_ocr_batch": eligible,
        "processing_status": "metadata_prioritized_ocr_not_run",
        "ocr_content_present": False,
        "transaction_rows_created": 0,
    }


def reconcile_senate_amendments(documents: list[dict]) -> list[dict]:
    """Describe possible amendment chains while retaining every official filing."""
    grouped: dict[str, list[dict]] = {}
    for source in documents:
        document = dict(source)
        document["document_family_id"] = senate_document_family_key(document)
        grouped.setdefault(document["document_family_id"], []).append(document)

    output = []
    for family in grouped.values():
        ordered = sorted(family, key=lambda row: (row["filing_date"], row["document_id"]))
        originals = [document for document in ordered if not document.get("is_amendment")]
        for document in ordered:
            if document.get("is_amendment"):
                predecessor = originals[0] if len(originals) == 1 else None
                document["amendment_status"] = (
                    "candidate_predecessor_identified"
                    if predecessor
                    else "ambiguous_predecessor_candidates"
                    if len(originals) > 1
                    else "predecessor_not_identified"
                )
                document["candidate_supersedes_document_id"] = (
                    predecessor["document_id"] if predecessor else None
                )
                document["amendment_linkage_confidence"] = (
                    "candidate_exact_official_metadata" if predecessor else "none"
                )
                document["amendment_reconciliation_evidence"] = [
                    {
                        "evidence_type": "official_title_marker",
                        "field": "portal_report_title",
                        "value": document.get("portal_report_title"),
                        "source_document_id": document["document_id"],
                    },
                    {
                        "evidence_type": "exact_family_metadata",
                        "fields": ["official_id_or_filer_name", "report_title_without_marker", "filing_date"],
                        "candidate_document_ids": [row["document_id"] for row in originals],
                    },
                ]
            else:
                document["amendment_status"] = "original_or_standalone_filing"
                document["candidate_supersedes_document_id"] = None
                document["amendment_linkage_confidence"] = "not_applicable"
                document["amendment_reconciliation_evidence"] = []
            document["amendment_reconciliation_action"] = "annotate_only"
            document["source_record_preserved"] = True
            output.append(document)
    return sorted(output, key=lambda row: (row["filing_date"], row["senate_report_uuid"]))


def asset_class(asset_name: str, asset_type: str, ticker: str | None) -> str:
    value = f"{asset_type} {asset_name}".upper()
    if any(token in value for token in ["CRYPTO", "BITCOIN", "ETHEREUM"]):
        return "crypto"
    if "EXCHANGE TRADED FUND" in value or " ETF" in value:
        return "etf"
    if "MUTUAL FUND" in value:
        return "mutual_fund"
    if "OPTION" in value:
        return "option"
    if any(token in value for token in ["BOND", "NOTE", "TREASURY", "NON-STOCK"]):
        return "fixed_income"
    if "REAL ESTATE" in value:
        return "real_estate"
    if "STOCK" in value or ticker:
        return "equity"
    return "unknown"


class _CsrfParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        values = dict(attrs)
        if values.get("name") == "csrfmiddlewaretoken" and values.get("value"):
            self.token = values["value"]


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href: str | None = None
        self._inside_anchor = False
        self._parts: list[str] = []

    @property
    def text(self) -> str:
        return clean_text(" ".join(self._parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and self.href is None:
            self.href = dict(attrs).get("href")
            self._inside_anchor = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._inside_anchor = False

    def handle_data(self, data: str) -> None:
        if self._inside_anchor:
            self._parts.append(data)


class _SenateReportHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.headings: list[str] = []
        self.filer_headings: list[str] = []
        self.filed_blocks: list[str] = []
        self.tables: list[list[list[str]]] = []
        self.media_urls: list[str] = []
        self._capture_tag: str | None = None
        self._capture_target: list[str] | None = None
        self._capture_parts: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_tag: str | None = None
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "h1":
            self._start_capture(tag, self.headings)
        elif tag == "h2" and "filedReport" in classes:
            self._start_capture(tag, self.filer_headings)
        elif tag == "p" and "muted" in classes:
            self._start_capture(tag, self.filed_blocks)
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell_tag = tag
            self._cell_parts = []
        elif tag == "br":
            if self._cell_tag:
                self._cell_parts.append(" ")
            if self._capture_tag:
                self._capture_parts.append(" ")

        if tag == "img" and "filingImage" in classes and values.get("src"):
            self.media_urls.append(values["src"])

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell_tag == tag and self._row is not None:
            self._row.append(clean_text(" ".join(self._cell_parts)))
            self._cell_tag = None
            self._cell_parts = []
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None

        if tag == self._capture_tag and self._capture_target is not None:
            value = clean_text(" ".join(self._capture_parts))
            if value:
                self._capture_target.append(value)
            self._capture_tag = None
            self._capture_target = None
            self._capture_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_tag:
            self._cell_parts.append(data)
        if self._capture_tag:
            self._capture_parts.append(data)

    def _start_capture(self, tag: str, target: list[str]) -> None:
        self._capture_tag = tag
        self._capture_target = target
        self._capture_parts = []


def _csrf_token(content: bytes) -> str:
    parser = _CsrfParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    if not parser.token:
        raise SenatePortalAccessError(
            "The Senate portal response did not contain the expected CSRF token; the portal contract may have changed.",
            source_url=SENATE_HOME_URL,
        )
    return parser.token


def _response_error_detail(body: bytes) -> str:
    text = clean_text(body.decode("utf-8", errors="replace"))
    return text[:240] or "empty response body"


class SenateDisclosurePortalClient:
    def __init__(
        self,
        *,
        terms_acknowledged: bool,
        request_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> None:
        if request_interval_seconds < MIN_REQUEST_INTERVAL_SECONDS:
            raise ValueError(
                f"Senate portal request interval cannot be below {MIN_REQUEST_INTERVAL_SECONDS:.1f} seconds"
            )
        self.terms_acknowledged = terms_acknowledged
        self.request_interval_seconds = request_interval_seconds
        self._sleep = sleep
        self._clock = clock
        self._last_request_finished_at: float | None = None
        self._cookie_jar = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookie_jar))
        self._session_ready = False
        self._search_page: bytes | None = None

    def ensure_access(self) -> None:
        if self._session_ready:
            return
        if not self.terms_acknowledged:
            raise SenateTermsAcknowledgementRequired(
                "Live Senate disclosure access requires --acknowledge-senate-terms after reviewing "
                f"{SENATE_TERMS_URL}. The flag is intentionally not implied or enabled by default."
            )
        landing = self._request(SENATE_HOME_URL)
        token = _csrf_token(landing.body)
        accepted = self._request(
            SENATE_HOME_URL,
            data={"prohibition_agreement": "1", "csrfmiddlewaretoken": token},
            referer=SENATE_HOME_URL,
        )
        if "/search/" not in accepted.final_url or b"Find Reports" not in accepted.body:
            raise SenatePortalAccessError(
                "The Senate portal did not grant a report-search session after the required acknowledgement. "
                f"Final URL: {accepted.final_url}; response: {_response_error_detail(accepted.body)}",
                source_url=SENATE_HOME_URL,
                status_code=accepted.status_code,
            )
        self._session_ready = True
        self._search_page = accepted.body

    def search_ptr_reports(
        self,
        *,
        first_name: str = "",
        last_name: str = "",
        start_date: date = SENATE_ONLINE_START_DATE,
        end_date: date | None = None,
        page_size: int = 100,
    ) -> SenateSearchAcquisition:
        self.ensure_access()
        end_date = end_date or date.today()
        if start_date < SENATE_ONLINE_START_DATE:
            raise ValueError(f"Senate eFD online searches cannot start before {SENATE_ONLINE_START_DATE}")
        if start_date > end_date:
            raise ValueError("Senate disclosure search start date cannot be after end date")
        if not 1 <= page_size <= 100:
            raise ValueError("Senate portal page size must be between 1 and 100")

        search_page = self._search_page or b""
        search_form: list[tuple[str, str]] = [
            ("first_name", first_name),
            ("last_name", last_name),
            *(('filer_type', str(value)) for value in SENATE_MEMBER_FILER_TYPES),
            ("report_type", str(SENATE_PTR_REPORT_TYPE)),
            ("submitted_start_date", start_date.strftime("%m/%d/%Y")),
            ("submitted_end_date", end_date.strftime("%m/%d/%Y")),
            ("csrfmiddlewaretoken", _csrf_token(search_page)),
        ]
        result_page = self._request(SENATE_SEARCH_URL, data=search_form, referer=SENATE_SEARCH_URL)
        if b'id="filedReports"' not in result_page.body:
            raise SenatePortalAccessError(
                "The Senate portal search response did not contain the expected results table. "
                f"Response: {_response_error_detail(result_page.body)}",
                source_url=SENATE_SEARCH_URL,
                status_code=result_page.status_code,
            )
        self._search_page = result_page.body

        timestamp_start = f"{start_date.strftime('%m/%d/%Y')} 00:00:00"
        timestamp_end = f"{end_date.strftime('%m/%d/%Y')} 23:59:59"
        rows: list[list[str]] = []
        response_records: list[dict] = []
        start = 0
        total: int | None = None
        draw = 1
        while total is None or start < total:
            payload = self._datatable_payload(
                first_name=first_name,
                last_name=last_name,
                start_date=timestamp_start,
                end_date=timestamp_end,
                start=start,
                length=page_size,
                draw=draw,
            )
            response = self._request(
                SENATE_REPORT_DATA_URL,
                data=payload,
                referer=SENATE_SEARCH_URL,
                extra_headers={
                    "X-CSRFToken": self._csrf_cookie(),
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
            )
            response_json = _parse_report_data_response(response.body, response.source_url)
            page_rows = response_json["data"]
            total = int(response_json.get("recordsFiltered", response_json.get("recordsTotal", 0)))
            rows.extend(page_rows)
            response_records.append(
                {
                    "kind": "report_index_page",
                    "source_url": response.source_url,
                    "request": {
                        "first_name": first_name,
                        "last_name": last_name,
                        "filer_types": list(SENATE_MEMBER_FILER_TYPES),
                        "report_types": [SENATE_PTR_REPORT_TYPE],
                        "submitted_start_date": timestamp_start,
                        "submitted_end_date": timestamp_end,
                        "start": start,
                        "length": page_size,
                    },
                    "response_sha256": response.sha256,
                    "byte_count": len(response.body),
                    "row_count": len(page_rows),
                    "records_total": int(response_json.get("recordsTotal", total)),
                    "records_filtered": total,
                    "response_body": response.body.decode("utf-8"),
                }
            )
            if not page_rows:
                if start < total:
                    raise SenatePortalAccessError(
                        f"The Senate portal returned an empty page at offset {start} before the declared total {total}.",
                        source_url=SENATE_REPORT_DATA_URL,
                        status_code=response.status_code,
                    )
                break
            start += len(page_rows)
            draw += 1

        return SenateSearchAcquisition(
            rows=rows,
            response_records=response_records,
            retrieved_at=utc_now(),
        )

    def fetch_report_page(self, source_url: str) -> SenateReportPage:
        self.ensure_access()
        validate_report_url(source_url)
        response = self._request(source_url, referer=SENATE_SEARCH_URL)
        report_markers = (b"View Report", b"Print Periodic Transaction Report")
        if "html" not in response.content_type.lower() or not any(
            marker in response.body for marker in report_markers
        ):
            raise SenatePortalAccessError(
                "The Senate portal report URL did not return the expected report HTML. "
                f"Content-Type: {response.content_type or 'unknown'}; response: {_response_error_detail(response.body)}",
                source_url=source_url,
                status_code=response.status_code,
            )
        return SenateReportPage(
            source_url=source_url,
            body=response.body,
            content_type=response.content_type,
            status_code=response.status_code,
            retrieved_at=utc_now(),
        )

    def _request(
        self,
        source_url: str,
        *,
        data: dict | list[tuple[str, str]] | None = None,
        referer: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PortalResponse:
        if self._last_request_finished_at is not None:
            elapsed = self._clock() - self._last_request_finished_at
            wait = self.request_interval_seconds - elapsed
            if wait > 0:
                self._sleep(wait)
        encoded = urlencode(data, doseq=True).encode() if data is not None else None
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        }
        if referer:
            headers["Referer"] = referer
        if extra_headers:
            headers.update(extra_headers)
        request = Request(source_url, data=encoded, headers=headers)
        try:
            with self._opener.open(request, timeout=60) as response:
                body = response.read()
                result = PortalResponse(
                    source_url=source_url,
                    final_url=response.geturl(),
                    body=body,
                    content_type=response.headers.get("Content-Type", ""),
                    status_code=response.status,
                )
        except HTTPError as exc:
            body = exc.read()
            retry_after = exc.headers.get("Retry-After")
            detail = _response_error_detail(body)
            suffix = f" Retry-After: {retry_after}." if retry_after else ""
            raise SenatePortalAccessError(
                f"Senate portal request failed with HTTP {exc.code} for {source_url}.{suffix} Response: {detail}",
                source_url=source_url,
                status_code=exc.code,
                retry_after=retry_after,
            ) from exc
        except URLError as exc:
            raise SenatePortalAccessError(
                f"Senate portal request failed for {source_url}: {exc.reason}",
                source_url=source_url,
            ) from exc
        finally:
            self._last_request_finished_at = self._clock()
        return result

    def _csrf_cookie(self) -> str:
        for cookie in self._cookie_jar:
            if cookie.name == "csrftoken":
                return cookie.value
        raise SenatePortalAccessError(
            "The acknowledged Senate portal session did not provide the expected CSRF cookie.",
            source_url=SENATE_SEARCH_URL,
        )

    @staticmethod
    def _datatable_payload(
        *,
        first_name: str,
        last_name: str,
        start_date: str,
        end_date: str,
        start: int,
        length: int,
        draw: int,
    ) -> dict[str, str]:
        payload = {
            "draw": str(draw),
            "start": str(start),
            "length": str(length),
            "search[value]": "",
            "search[regex]": "false",
            "order[0][column]": "1",
            "order[0][dir]": "asc",
            "report_types": json.dumps([SENATE_PTR_REPORT_TYPE]),
            "filer_types": json.dumps(list(SENATE_MEMBER_FILER_TYPES)),
            "submitted_start_date": start_date,
            "submitted_end_date": end_date,
            "candidate_state": "",
            "senator_state": "",
            "office_id": "",
            "first_name": first_name,
            "last_name": last_name,
        }
        for index in range(5):
            payload.update(
                {
                    f"columns[{index}][data]": str(index),
                    f"columns[{index}][name]": "",
                    f"columns[{index}][searchable]": "true",
                    f"columns[{index}][orderable]": "true",
                    f"columns[{index}][search][value]": "",
                    f"columns[{index}][search][regex]": "false",
                }
            )
        return payload


def _parse_report_data_response(body: bytes, source_url: str) -> dict:
    try:
        response = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SenatePortalAccessError(
            "The Senate portal report-data endpoint did not return JSON; the acknowledgement session may have "
            f"expired or automation may be blocked. Response: {_response_error_detail(body)}",
            source_url=source_url,
        ) from exc
    if response.get("result") != "ok" or not isinstance(response.get("data"), list):
        raise SenatePortalAccessError(
            f"The Senate portal report-data response was not successful: {clean_text(str(response))[:240]}",
            source_url=source_url,
        )
    if not all(isinstance(row, list) and len(row) >= 5 for row in response["data"]):
        raise SenatePortalAccessError(
            "The Senate portal report-data rows do not match the expected five-column format.",
            source_url=source_url,
        )
    return response


def combine_search_acquisitions(acquisitions: list[SenateSearchAcquisition]) -> SenateSearchAcquisition:
    if not acquisitions:
        return SenateSearchAcquisition(rows=[], response_records=[], retrieved_at=utc_now())
    modes = {item.acquisition_mode for item in acquisitions}
    if len(modes) != 1:
        raise ValueError("Cannot combine live and imported Senate search acquisitions")
    hashes = {item.import_manifest_sha256 for item in acquisitions if item.import_manifest_sha256}
    return SenateSearchAcquisition(
        rows=[row for item in acquisitions for row in item.rows],
        response_records=[record for item in acquisitions for record in item.response_records],
        retrieved_at=max(item.retrieved_at for item in acquisitions),
        acquisition_mode=next(iter(modes)),
        import_manifest_sha256=next(iter(hashes)) if len(hashes) == 1 else None,
    )


def validate_report_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.netloc != "efdsearch.senate.gov":
        raise ValueError(f"Senate report URL is not on the official eFD search host: {source_url}")
    if not REPORT_PATH_RE.fullmatch(parsed.path):
        raise ValueError(f"Senate report URL does not match an official PTR or paper-report path: {source_url}")


def parse_report_index_row(row: list[str]) -> dict:
    if len(row) < 5:
        raise ValueError("Senate portal report row has fewer than five columns")
    first_name, last_name, filer_description, link_html, filing_date_raw = row[:5]
    anchor = _AnchorParser()
    anchor.feed(link_html)
    if not anchor.href or not anchor.text:
        raise ValueError("Senate portal report row does not contain a report link")
    source_url = urljoin(SENATE_PORTAL_BASE_URL, anchor.href)
    validate_report_url(source_url)
    path_match = REPORT_PATH_RE.fullmatch(urlparse(source_url).path)
    if path_match is None:
        raise ValueError(f"Unexpected Senate report path: {source_url}")
    filing_date = parse_portal_date(filing_date_raw)
    report_uuid = path_match.group("report_uuid").lower()
    view_kind = path_match.group("view_kind").lower()
    return {
        "document_id": f"senate-ptr-{report_uuid}",
        "senate_report_uuid": report_uuid,
        "source_id": SENATE_SOURCE_ID,
        "source_index_url": SENATE_REPORT_DATA_URL,
        "source_url": source_url,
        "source_tier": "official",
        "report_type": "periodic_transaction_report",
        "portal_report_title": anchor.text,
        "portal_filer_description": clean_text(filer_description),
        "filing_year": filing_date.year,
        "filing_date": filing_date.isoformat(),
        "filer_first_name": clean_text(first_name),
        "filer_last_name": clean_text(last_name),
        "filer_name": clean_text(f"{first_name} {last_name}"),
        "report_format": "electronic_html" if view_kind == "ptr" else "paper_images",
        "is_amendment": "amendment" in anchor.text.lower(),
        "record_status": "official_senate_index",
        "review_required_before_public_trade": True,
        "public_production_trade": False,
    }


def senate_roles(public_officials: dict) -> list[dict]:
    return [
        role
        for role in public_officials.get("roles", [])
        if role.get("branch") == "Legislative"
        and role.get("source_metadata", {}).get("chamber") == "Senate"
        and SENATE_CONGRESS_START
        <= int(role.get("source_metadata", {}).get("congress_number", 0))
        <= SENATE_CONGRESS_END
    ]


def senate_roster_coverage(roles: list[dict]) -> dict:
    roles_by_congress = Counter()
    officials_by_congress: dict[int, set[str]] = {}
    for role in roles:
        congress = int(role["source_metadata"]["congress_number"])
        roles_by_congress[congress] += 1
        officials_by_congress.setdefault(congress, set()).add(role["external_person_id"])
    officials = {role["external_person_id"] for role in roles}
    return {
        "congresses": list(range(SENATE_CONGRESS_START, SENATE_CONGRESS_END + 1)),
        "senate_role_count": len(roles),
        "senator_official_count": len(officials),
        "role_counts_by_congress": {
            str(congress): roles_by_congress[congress]
            for congress in range(SENATE_CONGRESS_START, SENATE_CONGRESS_END + 1)
        },
        "official_counts_by_congress": {
            str(congress): len(officials_by_congress.get(congress, set()))
            for congress in range(SENATE_CONGRESS_START, SENATE_CONGRESS_END + 1)
        },
    }


def match_senator(report: dict, roles: list[dict]) -> dict:
    filing_date = date.fromisoformat(report["filing_date"])
    first_tokens = meaningful_name_tokens(report.get("filer_first_name"))
    last_tokens = meaningful_name_tokens(report.get("filer_last_name"))
    candidates: dict[str, dict] = {}
    roles_by_official: dict[str, list[dict]] = {}
    for role in roles:
        roles_by_official.setdefault(role["external_person_id"], []).append(role)

    for official_id, official_roles in roles_by_official.items():
        full_name = official_roles[0].get("full_name", "")
        role_tokens = meaningful_name_tokens(full_name)
        score = 0
        reasons = []
        if last_tokens and all(token in role_tokens for token in last_tokens):
            score += 4
            reasons.append("surname")
        if first_tokens and first_tokens[0] in role_tokens:
            score += 3
            reasons.append("first_name")
        if score < 7:
            continue

        relevant_role = official_roles[0]
        active_role = None
        for role in official_roles:
            role_start = date.fromisoformat(role["service_start"])
            service_end = role.get("service_end")
            role_end = date.fromisoformat(service_end) if service_end else date.max
            grace_end = role_end + timedelta(days=180) if service_end and role_end < date.max else role_end
            if role_start <= filing_date <= grace_end:
                active_role = role
                break
        if active_role:
            score += 2
            reasons.append("senate_service_period")
            relevant_role = active_role

        candidates[official_id] = {
            "score": score,
            "reasons": reasons,
            "role": relevant_role,
            "congress_numbers": sorted(
                {int(role["source_metadata"]["congress_number"]) for role in official_roles}
            ),
        }

    ranked = sorted(candidates.items(), key=lambda item: (-item[1]["score"], item[0]))
    candidate_summary = [
        {
            "official_id": official_id,
            "official_name": candidate["role"].get("full_name"),
            "score": candidate["score"],
            "reasons": candidate["reasons"],
            "congress_numbers": candidate["congress_numbers"],
        }
        for official_id, candidate in ranked[:5]
    ]
    if not ranked:
        return {
            "match_status": "unmatched",
            "match_score": 0,
            "identity_resolution": "manual_review_required",
            "identity_candidates": [],
        }
    if len(ranked) > 1 and ranked[0][1]["score"] == ranked[1][1]["score"]:
        return {
            "match_status": "ambiguous",
            "match_score": ranked[0][1]["score"],
            "identity_resolution": "ambiguous_manual_review_required",
            "identity_candidates": candidate_summary,
        }

    official_id, match = ranked[0]
    role = match["role"]
    metadata = role.get("source_metadata", {})
    return {
        "match_status": "matched",
        "match_score": match["score"],
        "match_reasons": match["reasons"],
        "identity_resolution": "deterministic_match",
        "identity_candidates": candidate_summary,
        "official_id": official_id,
        "official_name": role["full_name"],
        "bioguide_id": metadata.get("bioguide_id"),
        "state": metadata.get("state"),
        "congress_numbers": match["congress_numbers"],
    }


def response_provenance(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "response_body"}


def build_senate_ptr_index(
    public_officials: dict,
    acquisition: SenateSearchAcquisition,
    *,
    start_date: date,
    end_date: date,
    coverage_mode: str,
    selected_bioguide_ids: set[str] | None = None,
    request_interval_seconds: float | None = None,
) -> dict:
    roles = senate_roles(public_officials)
    roster_coverage = senate_roster_coverage(roles)
    documents_by_id: dict[str, dict] = {}
    duplicate_source_row_count = 0
    selected_scope_excluded_row_count = 0
    for row in acquisition.rows:
        document = parse_report_index_row(row)
        match = match_senator(document, roles)
        document.update(match)
        if (
            selected_bioguide_ids
            and match.get("match_status") == "matched"
            and match.get("bioguide_id") not in selected_bioguide_ids
        ):
            selected_scope_excluded_row_count += 1
            continue
        previous = documents_by_id.get(document["document_id"])
        if previous:
            comparable_keys = ["source_url", "filing_date", "filer_name", "portal_report_title"]
            if any(previous[key] != document[key] for key in comparable_keys):
                raise ValueError(f"Conflicting Senate portal rows share {document['document_id']}")
            duplicate_source_row_count += 1
            continue
        documents_by_id[document["document_id"]] = document

    documents = reconcile_senate_amendments(list(documents_by_id.values()))
    match_counts = Counter(document["match_status"] for document in documents)
    format_counts = Counter(document["report_format"] for document in documents)
    validation_documents = [
        document for document in documents if document.get("bioguide_id") == VALIDATION_BIOGUIDE_ID
    ]
    acquisition_block = {
        "mode": acquisition.acquisition_mode,
        "retrieved_at": acquisition.retrieved_at,
        "terms_acknowledged": True,
        "terms_url": SENATE_TERMS_URL,
        "source_request_count": len(acquisition.response_records),
        "source_requests": [response_provenance(record) for record in acquisition.response_records],
    }
    if request_interval_seconds is not None:
        acquisition_block["minimum_request_interval_seconds"] = request_interval_seconds
    if acquisition.import_manifest_sha256:
        acquisition_block["import_manifest_sha256"] = acquisition.import_manifest_sha256

    return {
        "schema_version": "senate-disclosure-index-v1",
        "generated_at": date.today().isoformat(),
        "source": {
            "id": SENATE_SOURCE_ID,
            "name": "Secretary of the U.S. Senate, Office of Public Records",
            "url": SENATE_SEARCH_URL,
            "source_tier": "official",
            "access_requires_terms_acknowledgement": True,
            "terms_url": SENATE_TERMS_URL,
            "online_availability_note": (
                "The official portal covers reports filed from 2012 onward and applies retention limits; "
                "roster coverage does not imply that every historical report remains online."
            ),
        },
        "scope": {
            "coverage_mode": coverage_mode,
            "query_start_date": start_date.isoformat(),
            "query_end_date": end_date.isoformat(),
            "roster_congress_start": SENATE_CONGRESS_START,
            "roster_congress_end": SENATE_CONGRESS_END,
            "selected_bioguide_ids": sorted(selected_bioguide_ids or []),
            "document_scope": "Senator and former-Senator periodic transaction reports",
        },
        "roster_coverage": roster_coverage,
        "acquisition": acquisition_block,
        "summary": {
            "source_index_row_count": len(acquisition.rows),
            "document_count": len(documents),
            "matched_document_count": match_counts["matched"],
            "ambiguous_document_count": match_counts["ambiguous"],
            "unmatched_document_count": match_counts["unmatched"],
            "report_format_counts": dict(sorted(format_counts.items())),
            "amendment_document_count": sum(document["is_amendment"] for document in documents),
            "duplicate_source_row_count": duplicate_source_row_count,
            "selected_scope_excluded_row_count": selected_scope_excluded_row_count,
            "review_required_before_public_trade": True,
            "public_production_trade_count": 0,
        },
        "validation": {
            "bioguide_id": VALIDATION_BIOGUIDE_ID,
            "official_id": f"congress:{VALIDATION_BIOGUIDE_ID}",
            "official_name": "Dianne Feinstein",
            "document_count": len(validation_documents),
            "matched_document_count": sum(
                document.get("match_status") == "matched" for document in validation_documents
            ),
            "status": "reports_acquired" if validation_documents else "no_reports_in_selected_scope",
        },
        "documents": documents,
    }


def parse_senate_report_html(content: bytes, *, source_url: str) -> ParsedSenateReport:
    validate_report_url(source_url)
    parser = _SenateReportHTMLParser()
    parser.feed(content.decode("utf-8", errors="replace"))

    report_title = parser.headings[0] if parser.headings else None
    filer_name = parser.filer_headings[0] if parser.filer_headings else None
    filing_date = None
    date_sources = [*(parser.headings or []), *(parser.filed_blocks or [])]
    for value in date_sources:
        match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", value)
        if match:
            filing_date = parse_portal_date(match.group(1)).isoformat()
            break

    transactions: list[dict] = []
    rejected_rows: list[dict] = []
    matched_table_headers: list[str] = []
    header_aliases = {
        "transaction date": {"transaction date", "date", "date of transaction"},
        "owner": {"owner", "ownership"},
        "ticker": {"ticker", "symbol"},
        "asset name": {"asset name", "asset", "security", "description"},
        "asset type": {"asset type", "type of asset"},
        "type": {"type", "transaction type", "action"},
        "amount": {"amount", "value", "amount of transaction"},
        "comment": {"comment", "comments", "notes"},
        "#": {"#", "row", "item"},
    }
    required_headers = {"transaction date", "owner", "asset name", "type", "amount"}
    for table in parser.tables:
        if not table:
            continue
        raw_header = [clean_text(value) for value in table[0]]
        canonical_header = []
        for value in raw_header:
            lowered = value.lower()
            canonical_header.append(
                next((name for name, aliases in header_aliases.items() if lowered in aliases), lowered)
            )
        if not required_headers <= set(canonical_header):
            continue
        matched_table_headers = raw_header
        positions = {name: index for index, name in enumerate(canonical_header)}
        for fallback_row_number, row in enumerate(table[1:], start=1):
            values = {
                name: clean_text(row[index]) if index < len(row) else ""
                for name, index in positions.items()
            }
            row_number_raw = values.get("#") or str(fallback_row_number)
            try:
                row_number = int(row_number_raw)
            except ValueError:
                row_number = fallback_row_number
            missing = [
                name for name in ["transaction date", "asset name", "type", "amount"] if not values.get(name)
            ]
            if missing:
                rejected_rows.append(
                    {"row_number": row_number, "reason": f"missing required field(s): {', '.join(missing)}"}
                )
                continue
            try:
                transaction_date = parse_portal_date(values["transaction date"]).isoformat()
            except ValueError:
                rejected_rows.append(
                    {"row_number": row_number, "reason": "invalid transaction date"}
                )
                continue
            ticker = values.get("ticker")
            comment = values.get("comment")
            transactions.append(
                {
                    "row_number": row_number,
                    "transaction_date": transaction_date,
                    "owner": values.get("owner") or None,
                    "ticker": None if ticker in {None, "", "--"} else ticker,
                    "asset_name": values["asset name"],
                    "asset_type": values.get("asset type", ""),
                    "transaction_type_raw": values["type"],
                    "action": normalize_action(values["type"]),
                    "amount": values["amount"],
                    "comment": None if comment in {None, "", "--"} else comment,
                }
            )
        break

    media_urls = []
    for media_url in parser.media_urls:
        absolute_url = urljoin(SENATE_PORTAL_BASE_URL, media_url)
        parsed = urlparse(absolute_url)
        if parsed.scheme != "https" or parsed.netloc not in {
            "efdsearch.senate.gov",
            "efd-media-public.senate.gov",
        }:
            raise ValueError(f"Paper report referenced a non-Senate media URL: {absolute_url}")
        if absolute_url not in media_urls:
            media_urls.append(absolute_url)

    return ParsedSenateReport(
        report_title=report_title,
        filer_name=filer_name,
        filing_date=filing_date,
        transactions=transactions,
        media_urls=media_urls,
        rejected_rows=rejected_rows,
        layout_metadata={
            "table_headers": matched_table_headers,
            "table_layout_detected": bool(matched_table_headers),
            "paper_media_reference_count": len(media_urls),
        },
    )


def build_senate_ptr_transactions(
    documents: list[dict],
    pages: dict[str, SenateReportPage],
    *,
    acquisition_mode: str,
    request_interval_seconds: float | None = None,
    import_manifest_sha256: str | None = None,
) -> dict:
    document_rows = []
    transaction_rows = []
    withheld_rows = 0
    for document in documents:
        page = pages.get(document["source_url"])
        if page is None:
            raise ValueError(f"No acquired report page was supplied for {document['source_url']}")
        parsed = parse_senate_report_html(page.body, source_url=document["source_url"])
        quality_flags = []
        if parsed.filing_date and parsed.filing_date != document["filing_date"]:
            quality_flags.append("portal_page_filing_date_mismatch")
        warnings = []
        if parsed.rejected_rows:
            warnings.append(
                f"{len(parsed.rejected_rows)} structured row(s) were withheld because required fields were invalid."
            )
        expected_name_tokens = meaningful_name_tokens(document.get("filer_name"))
        parsed_name_tokens = meaningful_name_tokens(parsed.filer_name)
        page_identity_consistent = bool(
            expected_name_tokens
            and parsed_name_tokens
            and expected_name_tokens[0] in parsed_name_tokens
            and expected_name_tokens[-1] in parsed_name_tokens
        )
        if parsed.transactions and not page_identity_consistent:
            quality_flags.append("portal_page_filer_identity_mismatch")

        if parsed.transactions:
            parser_status = "parser_preview"
            extraction_method = "official_senate_structured_html_v1"
        elif parsed.media_urls:
            parser_status = "paper_images_review_required"
            extraction_method = "official_senate_paper_image_manifest_v1"
            warnings.append(
                "Paper-image filing: no transaction rows were generated; OCR and human review are required."
            )
        else:
            parser_status = "unrecognized_report_format"
            extraction_method = "official_senate_html_unrecognized_v1"
            warnings.append(
                "No structured transactions or official paper-image references were detected; human review is required."
            )

        identity_resolved = (
            document.get("match_status") == "matched"
            and bool(document.get("official_id"))
            and bool(document.get("official_name"))
            and page_identity_consistent
        )
        if parsed.transactions and not identity_resolved:
            parser_status = "identity_review_required"
            warnings.append(
                "Structured rows were detected but withheld because the filer identity is unresolved or ambiguous."
            )
            withheld_rows += len(parsed.transactions)

        normalized_count = 0
        for row in parsed.transactions if identity_resolved else []:
            minimum, maximum, amount_label = value_range(row["amount"])
            if minimum is None:
                withheld_rows += 1
                warnings.append(
                    f"Structured row {row['row_number']} was withheld because its amount range was not recognized."
                )
                continue
            trade_date = date.fromisoformat(row["transaction_date"])
            reported_date = date.fromisoformat(document["filing_date"])
            disclosure_lag = (reported_date - trade_date).days
            if disclosure_lag < 0:
                withheld_rows += 1
                warnings.append(
                    f"Structured row {row['row_number']} was withheld because its trade date follows the filing date."
                )
                continue
            row_asset_class = asset_class(row["asset_name"], row["asset_type"], row["ticker"])
            row_flags = []
            if disclosure_lag > 45:
                row_flags.append("reported_after_45_days")
            if disclosure_lag > 365:
                row_flags.append("amendment_or_date_review_required")
            if row_asset_class == "unknown":
                row_flags.append("asset_class_unresolved")
            if row["action"] == "OTHER":
                row_flags.append("transaction_action_unresolved")
            row_identity = "|".join(
                [
                    row["transaction_date"],
                    row["action"],
                    row.get("owner") or "",
                    row["asset_name"],
                    row["amount"],
                ]
            )
            row_digest = hashlib.sha256(row_identity.encode("utf-8")).hexdigest()[:10]
            transaction = {
                    "id": (
                        f"{document['document_id']}-row-{row['row_number']:04d}-{row_digest}"
                    ),
                    "document_id": document["document_id"],
                    "official_id": document["official_id"],
                    "full_name": document["official_name"],
                    "branch": "Legislative",
                    "chamber": "Senate",
                    "trade_date": row["transaction_date"],
                    "reported_date": document["filing_date"],
                    "action": row["action"],
                    "action_raw": row["transaction_type_raw"],
                    "owner": row["owner"],
                    "raw_asset_text": row["asset_name"],
                    "asset_display_name": row["asset_name"],
                    "portal_asset_type": row["asset_type"],
                    "ticker": row["ticker"],
                    "asset_class": row_asset_class,
                    "value_range_label": amount_label,
                    "value_range_min": minimum,
                    "value_range_max": maximum,
                    "comment": row["comment"],
                    "disclosure_lag_days": disclosure_lag,
                    "parsing_confidence": 0.99,
                    "field_confidence": {
                        "transaction_date": 1.0,
                        "owner": 1.0 if row["owner"] else 0.5,
                        "ticker": 1.0 if row["ticker"] else 0.5,
                        "asset": 1.0,
                        "asset_type": 1.0 if row["asset_type"] else 0.5,
                        "transaction_type": 1.0,
                        "amount": 1.0,
                        "source_row": row["row_number"],
                    },
                    "source_url": document["source_url"],
                    "source_row": row["row_number"],
                    "source_file_hash": page.sha256,
                    "source_tier": "official",
                    "record_status": "official_senate_structured_parser_preview_not_promoted",
                    "confidence_label": "Official Senate structured PTR parser preview; review required",
                    "review_required_before_public_trade": True,
                    "public_production_trade": False,
                    "data_quality_flags": row_flags,
                }
            transaction["transaction_signature_sha256"] = senate_transaction_signature(transaction)
            transaction_rows.append(transaction)
            normalized_count += 1

        document_rows.append(
            {
                **document,
                "source_page_sha256": page.sha256,
                "source_page_byte_count": len(page.body),
                "source_page_content_type": page.content_type,
                "source_page_retrieved_at": page.retrieved_at,
                "source_media_urls": parsed.media_urls,
                "source_media_page_count": len(parsed.media_urls),
                "parsed_report_title": parsed.report_title,
                "parsed_filer_name": parsed.filer_name,
                "parsed_filing_date": parsed.filing_date,
                "page_identity_consistent": page_identity_consistent,
                "parser_status": parser_status,
                "parser_version": "senate-efd-html-v1",
                "extraction_method": extraction_method,
                "parser_transaction_count": normalized_count,
                "parser_rejected_transaction_count": len(parsed.rejected_rows),
                "parser_warnings": warnings,
                "source_layout_metadata": parsed.layout_metadata,
                "data_quality_flags": quality_flags,
                "record_status": "official_senate_parser_preview_not_promoted",
                "review_required_before_public_trade": True,
                "public_production_trade": False,
            }
        )

    duplicate_groups: dict[str, list[dict]] = {}
    for row in transaction_rows:
        signature = row["transaction_signature_sha256"]
        duplicate_groups.setdefault(signature, []).append(row)
    duplicate_candidate_count = 0
    duplicate_group_count = 0
    for signature, rows in duplicate_groups.items():
        if len(rows) < 2:
            continue
        duplicate_group_count += 1
        duplicate_candidate_count += len(rows)
        group_id = f"senate-duplicate-{hashlib.sha256(signature.encode()).hexdigest()[:16]}"
        for row in rows:
            row["duplicate_candidate"] = True
            row["duplicate_candidate_group_id"] = group_id
            row["data_quality_flags"].append("possible_duplicate")

    status_counts = Counter(document["parser_status"] for document in document_rows)
    action_counts = Counter(row["action"] for row in transaction_rows)
    asset_counts = Counter(row["asset_class"] for row in transaction_rows)
    years = Counter(str(document["filing_year"]) for document in document_rows)
    validation_documents = [
        document for document in document_rows if document.get("bioguide_id") == VALIDATION_BIOGUIDE_ID
    ]
    acquisition = {
        "mode": acquisition_mode,
        "terms_acknowledged": True,
        "terms_url": SENATE_TERMS_URL,
        "report_page_count": len(pages),
        "report_pages": [
            {
                "source_url": page.source_url,
                "response_sha256": page.sha256,
                "byte_count": len(page.body),
                "content_type": page.content_type,
                "retrieved_at": page.retrieved_at,
            }
            for page in sorted(pages.values(), key=lambda item: item.source_url)
        ],
    }
    if request_interval_seconds is not None:
        acquisition["minimum_request_interval_seconds"] = request_interval_seconds
    if import_manifest_sha256:
        acquisition["import_manifest_sha256"] = import_manifest_sha256

    return {
        "schema_version": "senate-ptr-transactions-v1",
        "generated_at": date.today().isoformat(),
        "source": {
            "id": SENATE_SOURCE_ID,
            "name": "Secretary of the U.S. Senate, Office of Public Records",
            "url": SENATE_SEARCH_URL,
            "source_tier": "official",
            "access_requires_terms_acknowledgement": True,
            "terms_url": SENATE_TERMS_URL,
        },
        "scope": {
            "processed_document_count": len(document_rows),
            "document_scope": "Matched Senator and former-Senator periodic transaction reports",
        },
        "acquisition": acquisition,
        "summary": {
            "processed_document_count": len(document_rows),
            "document_status_counts": dict(sorted(status_counts.items())),
            "paper_image_review_document_count": status_counts["paper_images_review_required"],
            "paper_image_page_count": sum(
                document["source_media_page_count"] for document in document_rows
            ),
            "parser_preview_transaction_count": len(transaction_rows),
            "processed_official_count": len(
                {document["official_id"] for document in document_rows if document.get("official_id")}
            ),
            "transaction_official_count": len({row["official_id"] for row in transaction_rows}),
            "action_counts": dict(sorted(action_counts.items())),
            "asset_class_counts": dict(sorted(asset_counts.items())),
            "document_counts_by_year": dict(sorted(years.items())),
            "withheld_invalid_structured_row_count": withheld_rows
            + sum(document["parser_rejected_transaction_count"] for document in document_rows),
            "duplicate_candidate_group_count": duplicate_group_count,
            "duplicate_candidate_transaction_count": duplicate_candidate_count,
            "review_required_document_count": len(document_rows),
            "review_required_transaction_count": len(transaction_rows),
            "public_production_trade_count": 0,
        },
        "validation": {
            "bioguide_id": VALIDATION_BIOGUIDE_ID,
            "official_name": "Dianne Feinstein",
            "processed_document_count": len(validation_documents),
            "paper_image_review_document_count": sum(
                document["parser_status"] == "paper_images_review_required"
                for document in validation_documents
            ),
            "parser_preview_transaction_count": sum(
                document["parser_transaction_count"] for document in validation_documents
            ),
        },
        "documents": sorted(
            document_rows, key=lambda row: (row["filing_date"], row["senate_report_uuid"])
        ),
        "transactions": sorted(transaction_rows, key=lambda row: (row["trade_date"], row["id"])),
        "context_label": (
            "Official Senate eFD parser previews. Every structured row remains review-gated and is not a "
            "reviewed public-production trade. Paper-image reports remain unparsed pending OCR and human review."
        ),
    }


def _load_import_manifest(content: bytes) -> tuple[dict, str]:
    manifest_sha256 = hashlib.sha256(content).hexdigest()
    try:
        manifest = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Senate import manifest is not valid UTF-8 JSON: {exc}") from exc
    if manifest.get("schema_version") != IMPORT_SCHEMA_VERSION:
        raise ValueError(f"Senate import manifest must use schema_version {IMPORT_SCHEMA_VERSION}")
    if manifest.get("source_id") != SENATE_SOURCE_ID:
        raise ValueError(f"Senate import manifest source_id must be {SENATE_SOURCE_ID}")
    if manifest.get("portal_terms_acknowledged") is not True:
        raise ValueError("Senate import manifest must record portal_terms_acknowledged=true")
    if not manifest.get("retrieved_at"):
        raise ValueError("Senate import manifest must include retrieved_at")
    return manifest, manifest_sha256


def load_search_import_manifest(content: bytes) -> SenateSearchAcquisition:
    manifest, manifest_sha256 = _load_import_manifest(content)
    records = manifest.get("search_responses")
    if not isinstance(records, list) or not records:
        raise ValueError("Senate import manifest must contain at least one search_responses entry")
    rows = []
    response_records = []
    for index, record in enumerate(records, start=1):
        body_text = record.get("response_body")
        expected_sha256 = record.get("response_sha256")
        if not isinstance(body_text, str) or not expected_sha256:
            raise ValueError(f"search_responses entry {index} requires response_body and response_sha256")
        body = body_text.encode("utf-8")
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"search_responses entry {index} SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        response = _parse_report_data_response(body, record.get("source_url") or SENATE_REPORT_DATA_URL)
        page_rows = response["data"]
        rows.extend(page_rows)
        response_records.append(
            {
                "kind": "report_index_page",
                "source_url": record.get("source_url") or SENATE_REPORT_DATA_URL,
                "request": record.get("request", {}),
                "response_sha256": actual_sha256,
                "byte_count": len(body),
                "row_count": len(page_rows),
                "records_total": int(response.get("recordsTotal", len(page_rows))),
                "records_filtered": int(response.get("recordsFiltered", len(page_rows))),
                "response_body": body_text,
            }
        )
    return SenateSearchAcquisition(
        rows=rows,
        response_records=response_records,
        retrieved_at=manifest["retrieved_at"],
        acquisition_mode="import_manifest",
        import_manifest_sha256=manifest_sha256,
    )


def load_report_page_import_manifest(content: bytes) -> tuple[dict[str, SenateReportPage], str]:
    manifest, manifest_sha256 = _load_import_manifest(content)
    records = manifest.get("report_pages")
    if not isinstance(records, list) or not records:
        raise ValueError("Senate import manifest must contain at least one report_pages entry")
    pages = {}
    for index, record in enumerate(records, start=1):
        source_url = record.get("source_url")
        body_text = record.get("response_body")
        expected_sha256 = record.get("response_sha256")
        if not source_url or not isinstance(body_text, str) or not expected_sha256:
            raise ValueError(
                f"report_pages entry {index} requires source_url, response_body, and response_sha256"
            )
        validate_report_url(source_url)
        body = body_text.encode("utf-8")
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"report_pages entry {index} SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        if source_url in pages:
            raise ValueError(f"Duplicate report_pages source_url: {source_url}")
        pages[source_url] = SenateReportPage(
            source_url=source_url,
            body=body,
            content_type=record.get("content_type", "text/html; charset=utf-8"),
            status_code=int(record.get("status_code", 200)),
            retrieved_at=record.get("retrieved_at") or manifest["retrieved_at"],
            acquisition_mode="import_manifest",
        )
    return pages, manifest_sha256


def search_import_manifest(acquisition: SenateSearchAcquisition) -> dict:
    return {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "source_id": SENATE_SOURCE_ID,
        "source_url": SENATE_SEARCH_URL,
        "portal_terms_acknowledged": True,
        "terms_url": SENATE_TERMS_URL,
        "retrieved_at": acquisition.retrieved_at,
        "search_responses": [
            {
                "source_url": record["source_url"],
                "request": record.get("request", {}),
                "response_sha256": record["response_sha256"],
                "response_body": record["response_body"],
            }
            for record in acquisition.response_records
        ],
        "report_pages": [],
    }


def report_page_import_manifest(pages: dict[str, SenateReportPage]) -> dict:
    retrieved_at = max((page.retrieved_at for page in pages.values()), default=utc_now())
    return {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "source_id": SENATE_SOURCE_ID,
        "source_url": SENATE_SEARCH_URL,
        "portal_terms_acknowledged": True,
        "terms_url": SENATE_TERMS_URL,
        "retrieved_at": retrieved_at,
        "search_responses": [],
        "report_pages": [
            {
                "source_url": page.source_url,
                "retrieved_at": page.retrieved_at,
                "status_code": page.status_code,
                "content_type": page.content_type,
                "response_sha256": page.sha256,
                "response_body": page.body.decode("utf-8"),
            }
            for page in sorted(pages.values(), key=lambda item: item.source_url)
        ],
    }
