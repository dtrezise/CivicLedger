from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Lock
import time
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_MAX_RECORDS = 250
GDELT_DEFAULT_REQUEST_INTERVAL_SECONDS = 1.0
USER_AGENT = "CivicLedger historical news context (+https://github.com/dtrezise/CivicLedger)"

JsonTransport = Callable[[str, dict[str, str], float], dict]


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider cannot supply a response and no cache is usable."""


@dataclass(frozen=True)
class HistoricalNewsQuery:
    query_id: str
    query: str
    start_date: str
    end_date: str
    label: str | None = None
    max_records: int = GDELT_MAX_RECORDS

    def __post_init__(self) -> None:
        if not self.query_id.strip():
            raise ValueError("query_id is required")
        if not self.query.strip():
            raise ValueError("query is required")
        start = date.fromisoformat(self.start_date)
        end = date.fromisoformat(self.end_date)
        if start > end:
            raise ValueError("start_date must be on or before end_date")
        if not 1 <= self.max_records <= GDELT_MAX_RECORDS:
            raise ValueError(f"max_records must be between 1 and {GDELT_MAX_RECORDS}")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalNewsArticle:
    title: str
    url: str
    published_at: str | None
    domain: str | None
    language: str | None
    source_country: str | None
    image_url: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalNewsResult:
    articles: tuple[HistoricalNewsArticle, ...]
    request_url: str
    retrieval_status: str
    warnings: tuple[str, ...] = ()


class HistoricalNewsProvider(Protocol):
    provider_id: str
    provider_name: str
    source_tier: str
    documentation_url: str

    def search(self, query: HistoricalNewsQuery) -> HistoricalNewsResult: ...


class RequestRateLimiter:
    """A small thread-safe minimum-interval limiter with injectable time hooks."""

    def __init__(
        self,
        minimum_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds cannot be negative")
        self.minimum_interval_seconds = minimum_interval_seconds
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
    """Content cache keyed by canonical request URL."""

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
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(encoded)
        temporary.replace(path)


def _default_json_transport(url: str, headers: dict[str, str], timeout: float) -> dict:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider response must be a JSON object")
    return payload


def _canonical_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")
    )


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def parse_gdelt_datetime(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            parsed = datetime.strptime(candidate, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_gdelt_articles(payload: dict) -> list[HistoricalNewsArticle]:
    articles = []
    rows = payload.get("articles", [])
    if not isinstance(rows, list):
        return articles
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _canonical_url(row.get("url"))
        if not url:
            continue
        title = _clean_text(row.get("title")) or "Untitled source article"
        domain = _clean_text(row.get("domain")) or urlsplit(url).netloc
        articles.append(
            HistoricalNewsArticle(
                title=title,
                url=url,
                published_at=parse_gdelt_datetime(row.get("seendate")),
                domain=domain.lower() if domain else None,
                language=_clean_text(row.get("language")),
                source_country=_clean_text(row.get("sourcecountry")),
                image_url=_canonical_url(row.get("socialimage")) or None,
            )
        )
    return sorted(
        articles,
        key=lambda article: (
            article.published_at or "",
            article.url,
            article.title,
        ),
    )


class GdeltDocHistoricalNewsProvider:
    """Keyless adapter for the GDELT DOC 2.0 ArticleList JSON contract."""

    provider_id = "gdelt-doc-2"
    provider_name = "GDELT DOC 2.0"
    source_tier = "news_aggregator"
    documentation_url = "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"

    def __init__(
        self,
        *,
        base_url: str = GDELT_DOC_API_URL,
        cache_directory: Path | None = None,
        minimum_interval_seconds: float = GDELT_DEFAULT_REQUEST_INTERVAL_SECONDS,
        timeout: float = 45.0,
        refresh: bool = False,
        transport: JsonTransport | None = None,
        rate_limiter: RequestRateLimiter | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("?")
        self.cache = JsonResponseCache(cache_directory)
        self.timeout = timeout
        self.refresh = refresh
        self.transport = transport or _default_json_transport
        self.rate_limiter = rate_limiter or RequestRateLimiter(minimum_interval_seconds)

    def request_url(self, query: HistoricalNewsQuery) -> str:
        parameters = {
            "query": query.query,
            "mode": "artlist",
            "maxrecords": str(query.max_records),
            "format": "json",
            "sort": "dateasc",
            "startdatetime": f"{query.start_date.replace('-', '')}000000",
            "enddatetime": f"{query.end_date.replace('-', '')}235959",
        }
        return f"{self.base_url}?{urlencode(parameters)}"

    def _fetch(self, request_url: str) -> tuple[dict, str, tuple[str, ...]]:
        cached = self.cache.read(request_url)
        if cached is not None and not self.refresh:
            return cached, "cache_hit", ()

        self.rate_limiter.wait()
        try:
            payload = self.transport(
                request_url,
                {"Accept": "application/json", "User-Agent": USER_AGENT},
                self.timeout,
            )
            if not isinstance(payload, dict):
                raise ValueError("provider response must be a JSON object")
        except HTTPError as exc:
            if cached is not None:
                return cached, "stale_cache_fallback", ("Live GDELT request failed; cached response used.",)
            raise ProviderUnavailableError(f"GDELT unavailable (HTTP {exc.code})") from exc
        except (
            URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            OSError,
        ) as exc:
            if cached is not None:
                return cached, "stale_cache_fallback", ("Live GDELT request failed; cached response used.",)
            raise ProviderUnavailableError(f"GDELT unavailable ({type(exc).__name__})") from exc

        self.cache.write(request_url, payload)
        return payload, "fetched", ()

    def search(self, query: HistoricalNewsQuery) -> HistoricalNewsResult:
        request_url = self.request_url(query)
        payload, retrieval_status, warnings = self._fetch(request_url)
        return HistoricalNewsResult(
            articles=tuple(parse_gdelt_articles(payload)),
            request_url=request_url,
            retrieval_status=retrieval_status,
            warnings=warnings,
        )


GdeltHistoricalNewsAdapter = GdeltDocHistoricalNewsProvider
