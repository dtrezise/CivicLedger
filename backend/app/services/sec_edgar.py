from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
import time
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


SEC_SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
SEC_COMPANYFACTS_BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
SEC_ATOM_BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_MAX_REQUESTS_PER_SECOND = 10.0
SEC_DEFAULT_REQUESTS_PER_SECOND = 8.0
SEC_DOCUMENTATION_URL = "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data"

JsonTransport = Callable[[str, dict[str, str], float], dict]
TextTransport = Callable[[str, dict[str, str], float], str]


class ProviderUnavailableError(RuntimeError):
    """Raised when SEC data cannot be fetched and no cached response is usable."""


def normalize_cik(value: str | int) -> str:
    candidate = str(value).strip()
    digits = candidate[3:].strip() if candidate.upper().startswith("CIK") else candidate
    if not digits.isdigit() or len(digits) > 10 or int(digits) <= 0:
        raise ValueError(f"Invalid SEC CIK: {value}")
    return digits.zfill(10)


def _normalize_forms(forms: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({form.strip().upper() for form in forms if form.strip()}))


@dataclass(frozen=True)
class SecCompanyRequest:
    request_id: str
    cik: str
    start_date: str
    end_date: str
    forms: tuple[str, ...] = ()
    label: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        object.__setattr__(self, "cik", normalize_cik(self.cik))
        object.__setattr__(self, "forms", _normalize_forms(self.forms))
        start = date.fromisoformat(self.start_date)
        end = date.fromisoformat(self.end_date)
        if start > end:
            raise ValueError("start_date must be on or before end_date")

    def as_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "cik": self.cik,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "forms": list(self.forms),
            "label": self.label,
        }


@dataclass(frozen=True)
class SecFiling:
    cik: str
    company_name: str
    accession_number: str
    filing_date: str
    report_date: str | None
    accepted_at: str | None
    form: str
    file_number: str | None
    items: tuple[str, ...]
    primary_document: str | None
    primary_document_description: str | None
    is_xbrl: bool
    is_inline_xbrl: bool
    source_url: str


@dataclass(frozen=True)
class SecFilingResult:
    company: dict
    filings: tuple[SecFiling, ...]
    request_urls: tuple[str, ...]
    retrieval_status: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecCompanyFactsResult:
    payload: dict
    request_url: str
    retrieval_status: str
    warnings: tuple[str, ...] = ()


class SecFilingProvider(Protocol):
    provider_id: str
    provider_name: str
    source_tier: str
    documentation_url: str

    def filings(self, request: SecCompanyRequest) -> SecFilingResult: ...


class RequestRateLimiter:
    def __init__(
        self,
        requests_per_second: float = SEC_DEFAULT_REQUESTS_PER_SECOND,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < requests_per_second <= SEC_MAX_REQUESTS_PER_SECOND:
            raise ValueError(
                f"requests_per_second must be greater than 0 and no more than {SEC_MAX_REQUESTS_PER_SECOND:g}"
            )
        self.minimum_interval_seconds = 1.0 / requests_per_second
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last_request_at is not None:
                delay = self.minimum_interval_seconds - (now - self._last_request_at)
                if delay > 0:
                    self._sleeper(delay)
                    now = max(self._clock(), self._last_request_at + delay)
            self._last_request_at = now


class JsonResponseCache:
    def __init__(self, directory: Path | None) -> None:
        self.directory = directory

    def _path(self, request_url: str) -> Path | None:
        if self.directory is None:
            return None
        digest = hashlib.sha256(request_url.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def read(self, request_url: str) -> dict | None:
        path = self._path(request_url)
        if path is None or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def write(self, request_url: str, payload: dict) -> None:
        path = self._path(request_url)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)


def _default_json_transport(url: str, headers: dict[str, str], timeout: float) -> dict:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider response must be a JSON object")
    return payload


def _default_text_transport(url: str, headers: dict[str, str], timeout: float) -> str:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("ISO-8859-1")


def _row_value(columns: dict, name: str, index: int) -> object:
    values = columns.get(name, [])
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            cleaned
            for item in value
            if (cleaned := _optional_text(item)) is not None
        }
    )


def _source_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes"}


def parse_submission_filings(
    payload: dict,
    *,
    cik: str,
    company_name: str,
    source_url: str,
) -> list[SecFiling]:
    normalized_cik = normalize_cik(cik)
    filing_block = payload.get("filings")
    columns = filing_block.get("recent") if isinstance(filing_block, dict) else payload
    if not isinstance(columns, dict):
        return []
    accession_numbers = columns.get("accessionNumber", [])
    if not isinstance(accession_numbers, list):
        return []

    filings = []
    for index, accession_value in enumerate(accession_numbers):
        accession_number = _optional_text(accession_value)
        filing_date = _optional_text(_row_value(columns, "filingDate", index))
        form = _optional_text(_row_value(columns, "form", index))
        if not accession_number or not filing_date or not form:
            continue
        try:
            date.fromisoformat(filing_date)
        except ValueError:
            continue
        items_value = _optional_text(_row_value(columns, "items", index)) or ""
        items = tuple(sorted({item.strip() for item in items_value.split(",") if item.strip()}))
        filings.append(
            SecFiling(
                cik=normalized_cik,
                company_name=company_name,
                accession_number=accession_number,
                filing_date=filing_date,
                report_date=_optional_text(_row_value(columns, "reportDate", index)),
                accepted_at=_optional_text(_row_value(columns, "acceptanceDateTime", index)),
                form=form.upper(),
                file_number=_optional_text(_row_value(columns, "fileNumber", index)),
                items=items,
                primary_document=_optional_text(_row_value(columns, "primaryDocument", index)),
                primary_document_description=_optional_text(
                    _row_value(columns, "primaryDocDescription", index)
                ),
                is_xbrl=_source_bool(_row_value(columns, "isXBRL", index)),
                is_inline_xbrl=_source_bool(_row_value(columns, "isInlineXBRL", index)),
                source_url=source_url,
            )
        )
    return sorted(filings, key=lambda filing: (filing.filing_date, filing.accession_number))


def _xml_child_text(parent: ElementTree.Element | None, local_name: str) -> str | None:
    if parent is None:
        return None
    for child in parent.iter():
        if child.tag.rsplit("}", 1)[-1] == local_name:
            return _optional_text(child.text)
    return None


def parse_atom_filings(payload: str, *, cik: str, source_url: str) -> tuple[dict, list[SecFiling]]:
    root = ElementTree.fromstring(payload)
    normalized_cik = normalize_cik(cik)
    company_name = _xml_child_text(root, "conformed-name") or f"CIK {normalized_cik}"
    company = {
        "cik": normalized_cik,
        "name": company_name,
        "tickers": [],
        "exchanges": [],
        "sic": _xml_child_text(root, "assigned-sic"),
        "sic_description": _xml_child_text(root, "assigned-sic-desc"),
    }
    filings = []
    for entry in (node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "entry"):
        accession_number = _xml_child_text(entry, "accession-number")
        filing_date = _xml_child_text(entry, "filing-date")
        form = _xml_child_text(entry, "filing-type")
        if not accession_number or not filing_date or not form:
            continue
        try:
            date.fromisoformat(filing_date)
        except ValueError:
            continue
        items_text = _xml_child_text(entry, "items-desc") or ""
        items = tuple(sorted(set(re.findall(r"\b\d{1,2}\.\d{2}\b", items_text))))
        filings.append(
            SecFiling(
                cik=normalized_cik,
                company_name=company_name,
                accession_number=accession_number,
                filing_date=filing_date,
                report_date=None,
                accepted_at=_xml_child_text(entry, "updated"),
                form=form.upper(),
                file_number=_xml_child_text(entry, "file-number"),
                items=items,
                primary_document=None,
                primary_document_description=_xml_child_text(entry, "form-name"),
                is_xbrl=bool(_xml_child_text(entry, "xbrl_href")),
                is_inline_xbrl=False,
                source_url=source_url,
            )
        )
    return company, sorted(
        filings,
        key=lambda filing: (filing.filing_date, filing.accession_number),
    )


def sec_filing_index_url(cik: str | int, accession_number: str) -> str:
    normalized_cik = normalize_cik(cik)
    safe_accession = quote(accession_number, safe="-")
    compact_accession = quote(accession_number.replace("-", ""), safe="")
    return (
        f"{SEC_ARCHIVES_BASE_URL}/{int(normalized_cik)}/{compact_accession}/"
        f"{safe_accession}-index.html"
    )


def sec_primary_document_url(
    cik: str | int,
    accession_number: str,
    primary_document: str | None,
) -> str | None:
    if not primary_document:
        return None
    normalized_cik = normalize_cik(cik)
    compact_accession = quote(accession_number.replace("-", ""), safe="")
    return (
        f"{SEC_ARCHIVES_BASE_URL}/{int(normalized_cik)}/{compact_accession}/"
        f"{quote(primary_document, safe='._-')}"
    )


def _ranges_overlap(
    start_date: str,
    end_date: str,
    filing_from: str | None,
    filing_to: str | None,
) -> bool:
    if not filing_from or not filing_to:
        return True
    return filing_from <= end_date and filing_to >= start_date


class SecEdgarSubmissionsProvider:
    """Official SEC submissions adapter, including linked historical files."""

    provider_id = "sec-edgar-submissions"
    provider_name = "SEC EDGAR Submissions"
    source_tier = "official"
    documentation_url = SEC_DOCUMENTATION_URL

    def __init__(
        self,
        *,
        user_agent: str | None,
        cache_directory: Path | None = None,
        submissions_base_url: str = SEC_SUBMISSIONS_BASE_URL,
        companyfacts_base_url: str = SEC_COMPANYFACTS_BASE_URL,
        requests_per_second: float = SEC_DEFAULT_REQUESTS_PER_SECOND,
        timeout: float = 45.0,
        refresh: bool = False,
        transport: JsonTransport | None = None,
        rate_limiter: RequestRateLimiter | None = None,
    ) -> None:
        self.user_agent = (user_agent or "").strip()
        self.cache = JsonResponseCache(cache_directory)
        self.submissions_base_url = submissions_base_url.rstrip("/")
        self.companyfacts_base_url = companyfacts_base_url.rstrip("/")
        self.timeout = timeout
        self.refresh = refresh
        self.transport = transport or _default_json_transport
        self.rate_limiter = rate_limiter or RequestRateLimiter(requests_per_second)

    def _get_json(self, request_url: str) -> tuple[dict, str, tuple[str, ...]]:
        cached = self.cache.read(request_url)
        if cached is not None and not self.refresh:
            return cached, "cache_hit", ()
        if not self.user_agent:
            if cached is not None:
                return cached, "stale_cache_fallback", (
                    "SEC identity header is missing; cached response used.",
                )
            raise ProviderUnavailableError(
                "SEC_EDGAR_USER_AGENT is required for live SEC requests"
            )

        self.rate_limiter.wait()
        try:
            payload = self.transport(
                request_url,
                {"Accept": "application/json", "User-Agent": self.user_agent},
                self.timeout,
            )
            if not isinstance(payload, dict):
                raise ValueError("provider response must be a JSON object")
        except HTTPError as exc:
            if cached is not None:
                return cached, "stale_cache_fallback", (
                    "Live SEC request failed; cached response used.",
                )
            raise ProviderUnavailableError(f"SEC EDGAR unavailable (HTTP {exc.code})") from exc
        except (
            URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            OSError,
        ) as exc:
            if cached is not None:
                return cached, "stale_cache_fallback", (
                    "Live SEC request failed; cached response used.",
                )
            raise ProviderUnavailableError(
                f"SEC EDGAR unavailable ({type(exc).__name__})"
            ) from exc

        self.cache.write(request_url, payload)
        return payload, "fetched", ()

    @staticmethod
    def _aggregate_status(statuses: list[str], partial: bool) -> str:
        if partial:
            return "partial"
        if "stale_cache_fallback" in statuses:
            return "stale_cache_fallback"
        if statuses and all(status == "cache_hit" for status in statuses):
            return "cache_hit"
        return "fetched"

    def filings(self, request: SecCompanyRequest) -> SecFilingResult:
        root_url = f"{self.submissions_base_url}/CIK{request.cik}.json"
        root, root_status, root_warnings = self._get_json(root_url)
        company_name = _optional_text(root.get("name")) or request.label or f"CIK {request.cik}"
        company = {
            "cik": request.cik,
            "name": company_name,
            "tickers": _string_values(root.get("tickers")),
            "exchanges": _string_values(root.get("exchanges")),
            "sic": _optional_text(root.get("sic")),
            "sic_description": _optional_text(root.get("sicDescription")),
        }

        filings = parse_submission_filings(
            root,
            cik=request.cik,
            company_name=company_name,
            source_url=root_url,
        )
        request_urls = [root_url]
        statuses = [root_status]
        warnings = list(root_warnings)
        partial = False
        filing_block = root.get("filings")
        historical_files = filing_block.get("files", []) if isinstance(filing_block, dict) else []
        if not isinstance(historical_files, list):
            historical_files = []
        for descriptor in sorted(
            (item for item in historical_files if isinstance(item, dict)),
            key=lambda item: str(item.get("name", "")),
        ):
            name = _optional_text(descriptor.get("name"))
            if not name or not _ranges_overlap(
                request.start_date,
                request.end_date,
                _optional_text(descriptor.get("filingFrom")),
                _optional_text(descriptor.get("filingTo")),
            ):
                continue
            historical_url = f"{self.submissions_base_url}/{quote(name, safe='._-')}"
            request_urls.append(historical_url)
            try:
                payload, status, fetch_warnings = self._get_json(historical_url)
            except ProviderUnavailableError:
                partial = True
                warnings.append(f"Historical SEC submissions file unavailable: {name}")
                continue
            statuses.append(status)
            warnings.extend(fetch_warnings)
            filings.extend(
                parse_submission_filings(
                    payload,
                    cik=request.cik,
                    company_name=company_name,
                    source_url=historical_url,
                )
            )

        allowed_forms = set(request.forms)
        filtered = {
            filing.accession_number: filing
            for filing in filings
            if request.start_date <= filing.filing_date <= request.end_date
            and (not allowed_forms or filing.form in allowed_forms)
        }
        return SecFilingResult(
            company=company,
            filings=tuple(
                sorted(filtered.values(), key=lambda filing: (filing.filing_date, filing.accession_number))
            ),
            request_urls=tuple(sorted(set(request_urls))),
            retrieval_status=self._aggregate_status(statuses, partial),
            warnings=tuple(sorted(set(warnings))),
        )

    def companyfacts(self, cik: str | int) -> SecCompanyFactsResult:
        normalized_cik = normalize_cik(cik)
        request_url = f"{self.companyfacts_base_url}/CIK{normalized_cik}.json"
        payload, status, warnings = self._get_json(request_url)
        return SecCompanyFactsResult(
            payload=payload,
            request_url=request_url,
            retrieval_status=status,
            warnings=warnings,
        )


class SecEdgarAtomProvider:
    """Official EDGAR company-feed fallback when data.sec.gov is unavailable."""

    provider_id = "sec-edgar-atom"
    provider_name = "SEC EDGAR Company Atom Feed"
    source_tier = "official"
    documentation_url = SEC_DOCUMENTATION_URL

    def __init__(
        self,
        *,
        user_agent: str | None,
        cache_directory: Path | None = None,
        base_url: str = SEC_ATOM_BASE_URL,
        requests_per_second: float = SEC_DEFAULT_REQUESTS_PER_SECOND,
        timeout: float = 45.0,
        refresh: bool = False,
        transport: TextTransport | None = None,
        rate_limiter: RequestRateLimiter | None = None,
    ) -> None:
        self.user_agent = (user_agent or "").strip()
        self.cache = JsonResponseCache(cache_directory)
        self.base_url = base_url
        self.timeout = timeout
        self.refresh = refresh
        self.transport = transport or _default_text_transport
        self.rate_limiter = rate_limiter or RequestRateLimiter(requests_per_second)

    def _request_url(self, request: SecCompanyRequest, form: str, start: int) -> str:
        parameters = {
            "action": "getcompany",
            "CIK": request.cik,
            "type": form,
            "datea": request.start_date.replace("-", ""),
            "dateb": request.end_date.replace("-", ""),
            "owner": "exclude",
            "count": "100",
            "start": str(start),
            "output": "atom",
        }
        return f"{self.base_url}?{urlencode(parameters)}"

    def _get_xml(self, request_url: str) -> tuple[str, str, tuple[str, ...]]:
        cached = self.cache.read(request_url)
        if cached is not None and isinstance(cached.get("xml"), str) and not self.refresh:
            return cached["xml"], "cache_hit", ()
        if not self.user_agent:
            raise ProviderUnavailableError("SEC_EDGAR_USER_AGENT is required for live SEC requests")
        self.rate_limiter.wait()
        try:
            payload = self.transport(
                request_url,
                {"Accept": "application/atom+xml", "User-Agent": self.user_agent},
                self.timeout,
            )
            ElementTree.fromstring(payload)
        except HTTPError as exc:
            if cached is not None and isinstance(cached.get("xml"), str):
                return cached["xml"], "stale_cache_fallback", (
                    "Live SEC Atom request failed; cached response used.",
                )
            raise ProviderUnavailableError(f"SEC EDGAR Atom unavailable (HTTP {exc.code})") from exc
        except (URLError, TimeoutError, UnicodeDecodeError, ElementTree.ParseError, OSError) as exc:
            if cached is not None and isinstance(cached.get("xml"), str):
                return cached["xml"], "stale_cache_fallback", (
                    "Live SEC Atom request failed; cached response used.",
                )
            raise ProviderUnavailableError(
                f"SEC EDGAR Atom unavailable ({type(exc).__name__})"
            ) from exc
        self.cache.write(request_url, {"xml": payload})
        return payload, "fetched", ()

    def filings(self, request: SecCompanyRequest) -> SecFilingResult:
        forms = request.forms or ("8-K", "10-K", "10-Q")
        company = None
        filings: dict[str, SecFiling] = {}
        request_urls = []
        statuses = []
        warnings = []
        for form in forms:
            start = 0
            while True:
                request_url = self._request_url(request, form, start)
                request_urls.append(request_url)
                payload, status, fetch_warnings = self._get_xml(request_url)
                statuses.append(status)
                warnings.extend(fetch_warnings)
                page_company, page_filings = parse_atom_filings(
                    payload,
                    cik=request.cik,
                    source_url=request_url,
                )
                company = company or page_company
                eligible = [
                    filing
                    for filing in page_filings
                    if request.start_date <= filing.filing_date <= request.end_date
                    and (not request.forms or filing.form in set(request.forms))
                ]
                filings.update({filing.accession_number: filing for filing in eligible})
                if len(page_filings) < 100:
                    break
                oldest = min((filing.filing_date for filing in page_filings), default=request.end_date)
                if oldest < request.start_date:
                    break
                start += 100

        if company is None:
            company = {
                "cik": request.cik,
                "name": request.label or f"CIK {request.cik}",
                "tickers": [],
                "exchanges": [],
                "sic": None,
                "sic_description": None,
            }
        return SecFilingResult(
            company=company,
            filings=tuple(
                sorted(filings.values(), key=lambda filing: (filing.filing_date, filing.accession_number))
            ),
            request_urls=tuple(request_urls),
            retrieval_status=SecEdgarSubmissionsProvider._aggregate_status(statuses, False),
            warnings=tuple(sorted(set(warnings))),
        )


class SecEdgarOfficialProvider:
    """Prefer submissions JSON, then fall back to the official EDGAR Atom feed."""

    provider_id = "sec-edgar-official"
    provider_name = "SEC EDGAR"
    source_tier = "official"
    documentation_url = SEC_DOCUMENTATION_URL

    def __init__(
        self,
        *,
        user_agent: str | None,
        cache_directory: Path | None = None,
        refresh: bool = False,
    ) -> None:
        self.submissions = SecEdgarSubmissionsProvider(
            user_agent=user_agent,
            cache_directory=cache_directory,
            refresh=refresh,
        )
        self.atom = SecEdgarAtomProvider(
            user_agent=user_agent,
            cache_directory=cache_directory,
            refresh=refresh,
        )

    def filings(self, request: SecCompanyRequest) -> SecFilingResult:
        try:
            return self.submissions.filings(request)
        except ProviderUnavailableError as submissions_error:
            atom_result = self.atom.filings(request)
            return SecFilingResult(
                company=atom_result.company,
                filings=atom_result.filings,
                request_urls=atom_result.request_urls,
                retrieval_status=atom_result.retrieval_status,
                warnings=tuple(
                    sorted(
                        set(
                            atom_result.warnings
                            + (f"Submissions JSON unavailable; official Atom fallback used: {submissions_error}",)
                        )
                    )
                ),
            )


SecEdgarAdapter = SecEdgarSubmissionsProvider
