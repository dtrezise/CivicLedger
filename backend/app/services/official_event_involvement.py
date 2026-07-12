from __future__ import annotations

import base64
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from http.client import IncompleteRead
import json
import re
from pathlib import Path
import tempfile
import time
from typing import Callable, Iterable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


CONGRESS_GOV_BASE_URL = "https://api.congress.gov/v3"
USER_AGENT = "CivicLedger official-event involvement/1.0 (+https://github.com/dtrezise/CivicLedger)"
CACHE_SCHEMA_VERSION = "official-event-http-cache-v1"
DATASET_SCHEMA_VERSION = "official-event-involvement-v1"
METHODOLOGY_VERSION = "official-event-involvement-methodology-v1"
ALLOWED_ROLL_CALL_HOSTS = {"clerk.house.gov", "senate.gov", "www.senate.gov"}
DIRECT_RELATIONSHIP_TYPES = {"sponsor", "cosponsor", "recorded_vote"}


AGENCY_CATALOG = {
    "department-of-agriculture": {
        "name": "Department of Agriculture",
        "url": "https://www.usda.gov/",
    },
    "department-of-commerce": {
        "name": "Department of Commerce",
        "url": "https://www.commerce.gov/",
    },
    "department-of-defense": {
        "name": "Department of Defense",
        "url": "https://www.defense.gov/",
    },
    "department-of-energy": {
        "name": "Department of Energy",
        "url": "https://www.energy.gov/",
    },
    "department-of-health-and-human-services": {
        "name": "Department of Health and Human Services",
        "url": "https://www.hhs.gov/",
    },
    "department-of-homeland-security": {
        "name": "Department of Homeland Security",
        "url": "https://www.dhs.gov/",
    },
    "department-of-the-interior": {
        "name": "Department of the Interior",
        "url": "https://www.doi.gov/",
    },
    "department-of-the-treasury": {
        "name": "Department of the Treasury",
        "url": "https://home.treasury.gov/",
    },
    "department-of-transportation": {
        "name": "Department of Transportation",
        "url": "https://www.transportation.gov/",
    },
    "environmental-protection-agency": {
        "name": "Environmental Protection Agency",
        "url": "https://www.epa.gov/",
    },
    "federal-communications-commission": {
        "name": "Federal Communications Commission",
        "url": "https://www.fcc.gov/",
    },
    "office-of-management-and-budget": {
        "name": "Office of Management and Budget",
        "url": "https://www.whitehouse.gov/omb/",
    },
    "securities-and-exchange-commission": {
        "name": "Securities and Exchange Commission",
        "url": "https://www.sec.gov/",
    },
}

JURISDICTION_AGENCY_CROSSWALK = {
    "agriculture": {"department-of-agriculture"},
    "appropriations": {"office-of-management-and-budget"},
    "armed services": {"department-of-defense"},
    "banking": {"department-of-the-treasury"},
    "budget": {"office-of-management-and-budget"},
    "commerce": {"department-of-commerce"},
    "communications": {"department-of-commerce", "federal-communications-commission"},
    "cybersecurity": {"department-of-homeland-security"},
    "defense": {"department-of-defense"},
    "energy": {"department-of-energy"},
    "environment": {"environmental-protection-agency"},
    "epa": {"environmental-protection-agency"},
    "financial markets": {"department-of-the-treasury", "securities-and-exchange-commission"},
    "food": {"department-of-agriculture", "department-of-health-and-human-services"},
    "health": {"department-of-health-and-human-services"},
    "hhs": {"department-of-health-and-human-services"},
    "infrastructure": {"department-of-transportation"},
    "interior": {"department-of-the-interior"},
    "manufacturing": {"department-of-commerce"},
    "medicaid": {"department-of-health-and-human-services"},
    "medicare": {"department-of-health-and-human-services"},
    "national security": {"department-of-defense", "department-of-homeland-security"},
    "securities": {"securities-and-exchange-commission"},
    "supply chain": {"department-of-commerce"},
    "tax": {"department-of-the-treasury"},
    "technology": {"department-of-commerce"},
    "trade": {"department-of-commerce"},
    "transportation": {"department-of-transportation"},
    "treasury": {"department-of-the-treasury"},
}


class CacheMissError(RuntimeError):
    """Raised when an offline build needs a response that is not cached."""


@dataclass(frozen=True)
class SourceSnapshot:
    url: str
    body: bytes = field(repr=False)
    response_sha256: str
    retrieved_at: str
    content_type: str | None
    status_code: int = 200
    from_cache: bool = False

    @property
    def source_id(self) -> str:
        digest = hashlib.sha256(self.url.encode("utf-8")).hexdigest()[:24]
        return f"source-snapshot:{digest}"

    def as_provenance(self, *, authority: str, source_kind: str) -> dict:
        return {
            "id": self.source_id,
            "source_class": "fetched_official_response",
            "source_kind": source_kind,
            "authority": authority,
            "source_tier": "official",
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "response_sha256": self.response_sha256,
            "content_type": self.content_type,
            "status_code": self.status_code,
        }


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_request_url(url: str, params: dict | None = None) -> str:
    parts = urlsplit(url)
    pairs = list(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in (params or {}).items():
        if isinstance(value, (list, tuple)):
            pairs.extend((key, str(item)) for item in value)
        elif value is not None:
            pairs.append((key, str(value)))
    query = urlencode(sorted(pairs), doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


class CachedRateLimitedHttpClient:
    """HTTP client with a key-safe, content-verified response cache."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        offline: bool = False,
        refresh: bool = False,
        min_interval_seconds: float = 0.25,
        timeout_seconds: float = 60.0,
        retries: int = 4,
        user_agent: str = USER_AGENT,
    ) -> None:
        if offline and refresh:
            raise ValueError("offline and refresh modes cannot be combined")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be non-negative")
        self.cache_dir = Path(cache_dir).expanduser()
        self.offline = offline
        self.refresh = refresh
        self.min_interval_seconds = min_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.user_agent = user_agent
        self._last_request_at: float | None = None
        self.cache_hits = 0
        self.network_requests = 0

    def cache_path_for(self, canonical_url: str) -> Path:
        digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        secret_params: dict | None = None,
    ) -> SourceSnapshot:
        canonical_url = canonical_request_url(url, params)
        cache_path = self.cache_path_for(canonical_url)
        if cache_path.exists() and not self.refresh:
            snapshot = self._read_cache(cache_path, canonical_url)
            self.cache_hits += 1
            return snapshot
        if self.offline:
            raise CacheMissError(f"Offline cache miss for {canonical_url}")

        request_url = canonical_request_url(canonical_url, secret_params)
        snapshot = self._request(request_url, canonical_url)
        self._write_cache(cache_path, snapshot)
        return snapshot

    def _read_cache(self, cache_path: Path, canonical_url: str) -> SourceSnapshot:
        try:
            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            if envelope.get("schema_version") != CACHE_SCHEMA_VERSION:
                raise ValueError("unsupported cache schema")
            if envelope.get("url") != canonical_url:
                raise ValueError("cache URL does not match cache key")
            body = base64.b64decode(envelope["body_base64"], validate=True)
            response_sha256 = sha256_bytes(body)
            if response_sha256 != envelope.get("response_sha256"):
                raise ValueError("cached response hash mismatch")
            return SourceSnapshot(
                url=canonical_url,
                body=body,
                response_sha256=response_sha256,
                retrieved_at=envelope["retrieved_at"],
                content_type=envelope.get("content_type"),
                status_code=int(envelope.get("status_code", 200)),
                from_cache=True,
            )
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid response cache entry: {cache_path}") from exc

    def _write_cache(self, cache_path: Path, snapshot: SourceSnapshot) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "url": snapshot.url,
            "retrieved_at": snapshot.retrieved_at,
            "status_code": snapshot.status_code,
            "content_type": snapshot.content_type,
            "response_sha256": snapshot.response_sha256,
            "body_base64": base64.b64encode(snapshot.body).decode("ascii"),
        }
        serialized = json.dumps(envelope, indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.cache_dir,
            prefix=f".{cache_path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            temp_path = Path(handle.name)
        temp_path.replace(cache_path)

    def _request(self, request_url: str, canonical_url: str) -> SourceSnapshot:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._rate_limit()
            request = Request(request_url, headers={"User-Agent": self.user_agent, "Accept": "*/*"})
            try:
                self.network_requests += 1
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read()
                    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                    return SourceSnapshot(
                        url=canonical_url,
                        body=body,
                        response_sha256=sha256_bytes(body),
                        retrieved_at=retrieved_at,
                        content_type=response.headers.get("Content-Type"),
                        status_code=int(getattr(response, "status", 200)),
                    )
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt == self.retries:
                    break
                time.sleep(self._retry_delay(exc.headers.get("Retry-After"), attempt))
            except (IncompleteRead, TimeoutError, URLError, ConnectionError) as exc:
                last_error = exc
                if attempt == self.retries:
                    break
                time.sleep(float(attempt * 2))
        raise RuntimeError(f"Official-source request failed: {canonical_url}") from last_error

    def _rate_limit(self) -> None:
        now = time.monotonic()
        if self._last_request_at is not None:
            wait_seconds = self.min_interval_seconds - (now - self._last_request_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
        self._last_request_at = time.monotonic()

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    return max((retry_at - datetime.now(retry_at.tzinfo)).total_seconds(), 0.0)
                except (TypeError, ValueError):
                    pass
        return float(attempt * 2)


class OfficialCongressGovClient:
    def __init__(
        self,
        http_client: CachedRateLimitedHttpClient,
        *,
        api_key: str | None = None,
        base_url: str = CONGRESS_GOV_BASE_URL,
        page_size: int = 250,
    ) -> None:
        self.http = http_client
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size

    def bill_detail(self, congress: int, bill_type: str, number: str) -> tuple[dict, SourceSnapshot]:
        payload, snapshot = self._get_json(
            f"/bill/{congress}/{bill_type.lower()}/{number}",
            {"format": "json"},
        )
        bill = payload.get("bill")
        if not isinstance(bill, dict):
            raise ValueError(f"Congress.gov bill detail missing bill object for {congress}/{bill_type}/{number}")
        return bill, snapshot

    def bill_cosponsors(
        self,
        congress: int,
        bill_type: str,
        number: str,
    ) -> tuple[list[dict], list[SourceSnapshot]]:
        return self._get_pages(
            f"/bill/{congress}/{bill_type.lower()}/{number}/cosponsors",
            "cosponsors",
        )

    def bill_actions(
        self,
        congress: int,
        bill_type: str,
        number: str,
    ) -> tuple[list[dict], list[SourceSnapshot]]:
        return self._get_pages(
            f"/bill/{congress}/{bill_type.lower()}/{number}/actions",
            "actions",
        )

    def _get_pages(self, path: str, collection_key: str) -> tuple[list[dict], list[SourceSnapshot]]:
        rows: list[dict] = []
        snapshots: list[SourceSnapshot] = []
        offset = 0
        for _page_number in range(1, 101):
            payload, snapshot = self._get_json(
                path,
                {"format": "json", "limit": self.page_size, "offset": offset},
            )
            batch = payload.get(collection_key, [])
            if not isinstance(batch, list):
                raise ValueError(f"Congress.gov {collection_key} payload is not a list: {snapshot.url}")
            rows.extend(row for row in batch if isinstance(row, dict))
            snapshots.append(snapshot)
            pagination = payload.get("pagination") or {}
            if not batch or not pagination.get("next"):
                return rows, snapshots
            offset += self.page_size
        raise RuntimeError(f"Congress.gov pagination exceeded 100 pages: {path}")

    def _get_json(self, path: str, params: dict) -> tuple[dict, SourceSnapshot]:
        secret_params = {"api_key": self.api_key} if self.api_key else None
        snapshot = self.http.get(f"{self.base_url}{path}", params=params, secret_params=secret_params)
        try:
            payload = json.loads(snapshot.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Congress.gov returned invalid JSON: {snapshot.url}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Congress.gov returned a non-object payload: {snapshot.url}")
        return payload, snapshot


def _text(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    child = node.find(path)
    if child is None or child.text is None:
        return None
    value = " ".join(child.text.split()).strip()
    return value or None


def _iso_house_vote_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d-%b-%Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Unexpected House vote date: {value}") from exc


def _iso_senate_vote_date(value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.replace(",", " , ").split()).replace(" , ", ", ")
    for pattern in ("%B %d, %Y, %I:%M %p", "%B %d, %Y"):
        try:
            return datetime.strptime(normalized, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unexpected Senate vote date: {value}")


def parse_house_roll_call(xml_content: bytes | str) -> dict:
    root = ET.fromstring(xml_content)
    if root.tag != "rollcall-vote":
        raise ValueError(f"Unexpected House roll-call root element: {root.tag}")
    metadata = root.find("vote-metadata")
    congress = _text(metadata, "congress")
    roll_number = _text(metadata, "rollcall-num")
    session_text = _text(metadata, "session") or ""
    session_match = re.search(r"\d+", session_text)
    if not congress or not roll_number or not session_match:
        raise ValueError("House roll-call XML is missing congress, session, or roll number")
    members = []
    for recorded_vote in root.findall("./vote-data/recorded-vote"):
        legislator = recorded_vote.find("legislator")
        vote_cast = _text(recorded_vote, "vote")
        if legislator is None or not vote_cast:
            continue
        official_name = " ".join("".join(legislator.itertext()).split()).strip()
        members.append(
            {
                "official_record_name": official_name,
                "bioguide_id": legislator.attrib.get("name-id") or None,
                "party": legislator.attrib.get("party") or None,
                "state": legislator.attrib.get("state") or None,
                "vote_cast": vote_cast,
            }
        )
    totals_node = metadata.find("./vote-totals/totals-by-vote") if metadata is not None else None
    totals = {
        "yea": _text(totals_node, "yea-total"),
        "nay": _text(totals_node, "nay-total"),
        "present": _text(totals_node, "present-total"),
        "not_voting": _text(totals_node, "not-voting-total"),
    }
    return {
        "id": f"house-{int(congress)}-{int(session_match.group())}-{int(roll_number)}",
        "chamber": "House",
        "congress": int(congress),
        "session": int(session_match.group()),
        "roll_number": int(roll_number),
        "vote_date": _iso_house_vote_date(_text(metadata, "action-date")),
        "document": {"name": _text(metadata, "legis-num")},
        "question": _text(metadata, "vote-question"),
        "vote_type": _text(metadata, "vote-type"),
        "result": _text(metadata, "vote-result"),
        "description": _text(metadata, "vote-desc"),
        "totals": {key: int(value) if value and value.isdigit() else None for key, value in totals.items()},
        "tie_breaker": None,
        "members": members,
    }


def parse_senate_roll_call(xml_content: bytes | str) -> dict:
    root = ET.fromstring(xml_content)
    if root.tag != "roll_call_vote":
        raise ValueError(f"Unexpected Senate roll-call root element: {root.tag}")
    congress = _text(root, "congress")
    session = _text(root, "session")
    roll_number = _text(root, "vote_number")
    if not congress or not session or not roll_number:
        raise ValueError("Senate roll-call XML is missing congress, session, or vote number")
    members = []
    for member in root.findall("./members/member"):
        vote_cast = _text(member, "vote_cast")
        if not vote_cast:
            continue
        members.append(
            {
                "official_record_name": _text(member, "member_full")
                or " ".join(filter(None, [_text(member, "first_name"), _text(member, "last_name")])),
                "first_name": _text(member, "first_name"),
                "last_name": _text(member, "last_name"),
                "lis_member_id": _text(member, "lis_member_id"),
                "party": _text(member, "party"),
                "state": _text(member, "state"),
                "vote_cast": vote_cast,
            }
        )
    count = root.find("count")
    totals = {
        "yea": _text(count, "yeas"),
        "nay": _text(count, "nays"),
        "present": _text(count, "present"),
        "not_voting": _text(count, "absent"),
    }
    document = root.find("document")
    tie_breaker = root.find("tie_breaker")
    return {
        "id": f"senate-{int(congress)}-{int(session)}-{int(roll_number)}",
        "chamber": "Senate",
        "congress": int(congress),
        "session": int(session),
        "roll_number": int(roll_number),
        "vote_date": _iso_senate_vote_date(_text(root, "vote_date")),
        "document": {
            "congress": _text(document, "document_congress"),
            "type": _text(document, "document_type"),
            "number": _text(document, "document_number"),
            "name": _text(document, "document_name"),
            "title": _text(document, "document_title"),
            "short_title": _text(document, "document_short_title"),
        },
        "question": _text(root, "vote_question_text") or _text(root, "question"),
        "vote_type": _text(root, "question"),
        "result": _text(root, "vote_result_text") or _text(root, "vote_result"),
        "description": _text(root, "vote_document_text") or _text(root, "vote_title"),
        "totals": {key: int(value) if value and value.isdigit() else None for key, value in totals.items()},
        "tie_breaker": {
            "by_whom": _text(tie_breaker, "by_whom"),
            "vote_cast": _text(tie_breaker, "tie_breaker_vote"),
        },
        "members": members,
    }


def parse_roll_call(xml_content: bytes | str, chamber: str) -> dict:
    if chamber.lower() == "house":
        return parse_house_roll_call(xml_content)
    if chamber.lower() == "senate":
        return parse_senate_roll_call(xml_content)
    raise ValueError(f"Unsupported roll-call chamber: {chamber}")


def _normalize_name(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()
    tokens = [
        token
        for token in normalized.split()
        if token not in {"rep", "representative", "sen", "senator", "jr", "sr", "ii", "iii", "iv"}
    ]
    return " ".join(tokens)


def _role_active(role: dict, event_date: str | None) -> bool:
    if not event_date:
        return True
    start = role.get("service_start")
    end = role.get("service_end")
    return (not start or start <= event_date) and (not end or event_date < end)


def _role_chamber(role: dict) -> str | None:
    metadata = role.get("source_metadata") or {}
    chamber = metadata.get("chamber")
    if chamber and "senate" in str(chamber).lower():
        return "Senate"
    if chamber:
        return "House"
    category = role.get("role_category")
    if category == "senator":
        return "Senate"
    if category in {"representative", "delegate", "resident_commissioner"}:
        return "House"
    return None


class PublicOfficialRoleIndex:
    def __init__(self, roles: Iterable[dict]) -> None:
        self.roles = [role for role in roles if isinstance(role, dict)]
        self.by_bioguide: dict[tuple[str, int, str], list[dict]] = defaultdict(list)
        self.by_chamber_state: dict[tuple[int, str, str], list[dict]] = defaultdict(list)
        self.presidents: list[dict] = []
        self.agencies: set[str] = set()
        self.courts: set[str] = set()
        for role in self.roles:
            metadata = role.get("source_metadata") or {}
            congress = metadata.get("congress_number")
            chamber = _role_chamber(role)
            bioguide_id = metadata.get("bioguide_id")
            state = metadata.get("state")
            if bioguide_id and congress and chamber:
                self.by_bioguide[(str(bioguide_id), int(congress), chamber)].append(role)
            if congress and chamber and state:
                self.by_chamber_state[(int(congress), chamber, str(state))].append(role)
            if role.get("role_category") == "elected_executive" and role.get("role_title") == "President":
                self.presidents.append(role)
            if role.get("agency"):
                self.agencies.add(str(role["agency"]))
            if role.get("court"):
                self.courts.add(str(role["court"]))
        self.presidents.sort(key=lambda role: (role.get("service_start") or "", role.get("external_role_id") or ""))

    def resolve_bioguide(
        self,
        bioguide_id: str | None,
        congress: int,
        chamber: str,
        event_date: str | None = None,
    ) -> dict | None:
        if not bioguide_id:
            return None
        candidates = self.by_bioguide.get((str(bioguide_id), int(congress), chamber), [])
        return self._select_role(candidates, event_date)

    def resolve_senate_member(
        self,
        *,
        first_name: str | None,
        last_name: str | None,
        state: str | None,
        congress: int,
        event_date: str | None = None,
    ) -> dict | None:
        if not first_name or not last_name or not state:
            return None
        candidates = self.by_chamber_state.get((int(congress), "Senate", state), [])
        active_candidates = [role for role in candidates if _role_active(role, event_date)] or candidates
        first = _normalize_name(first_name)
        last = _normalize_name(last_name)
        target = f"{first} {last}".strip()
        scored: list[tuple[int, dict]] = []
        for role in active_candidates:
            candidate = _normalize_name(role.get("full_name"))
            candidate_tokens = candidate.split()
            score = 0
            if candidate == target:
                score = 100
            elif candidate.endswith(last) and candidate.startswith(first):
                score = 90
            elif candidate.endswith(last) and candidate_tokens and first and candidate_tokens[0][:1] == first[:1]:
                score = 70
            elif last and candidate.endswith(last):
                score = 50
            if score:
                scored.append((score, role))
        if not scored:
            return None
        best_score = max(score for score, _role in scored)
        best = [role for score, role in scored if score == best_score]
        if len(best) != 1:
            return None
        return best[0]

    def president_on(self, event_date: str) -> dict | None:
        candidates = [role for role in self.presidents if _role_active(role, event_date)]
        if not candidates:
            return None
        return sorted(candidates, key=lambda role: (role.get("service_start") or "", role.get("external_role_id") or ""))[-1]

    @staticmethod
    def _select_role(candidates: Iterable[dict], event_date: str | None) -> dict | None:
        choices = list(candidates)
        active = [role for role in choices if _role_active(role, event_date)]
        selected = active or choices
        if not selected:
            return None
        return sorted(selected, key=lambda role: role.get("external_role_id") or "")[0]


def build_role_index(public_official_roles: dict | Iterable[dict]) -> PublicOfficialRoleIndex:
    if isinstance(public_official_roles, dict):
        roles = public_official_roles.get("roles", [])
    else:
        roles = public_official_roles
    return PublicOfficialRoleIndex(roles)


def parse_bill_reference(event: dict) -> tuple[int, str, str] | None:
    match = re.fullmatch(r"congress-law-(\d+)-([a-z]+)-(\d+)", str(event.get("id") or ""))
    if not match:
        return None
    return int(match.group(1)), match.group(2), match.group(3)


def _official_name_from_api(row: dict) -> str:
    pieces = [row.get("firstName"), row.get("middleName"), row.get("lastName"), row.get("suffixName")]
    assembled = " ".join(str(piece).strip() for piece in pieces if piece)
    return assembled or str(row.get("fullName") or "Unknown member")


def _actor_record(row: dict, role: dict | None, *, fallback_id: str | None = None) -> dict:
    metadata = role.get("source_metadata") if role else {}
    metadata = metadata or {}
    bioguide_id = row.get("bioguideId") or row.get("bioguide_id") or metadata.get("bioguide_id")
    official_name = row.get("official_record_name") or _official_name_from_api(row)
    official_actor_id = f"congress:{bioguide_id}" if bioguide_id else fallback_id
    if not official_actor_id:
        fallback_key = "|".join(
            [official_name, str(row.get("state") or ""), str(row.get("party") or "")]
        )
        official_actor_id = f"official-record:{hashlib.sha256(fallback_key.encode('utf-8')).hexdigest()[:24]}"
    return {
        "official_actor_id": official_actor_id,
        "external_person_id": role.get("external_person_id") if role else (f"congress:{bioguide_id}" if bioguide_id else None),
        "external_role_id": role.get("external_role_id") if role else None,
        "bioguide_id": bioguide_id,
        "full_name": role.get("full_name") if role else official_name,
        "official_record_name": official_name,
        "party": row.get("party") or metadata.get("party"),
        "state": row.get("state") or metadata.get("state"),
        "resolution_status": "matched_public_official_role" if role else "official_actor_unmatched_to_role_dataset",
        "role_source_url": role.get("source_url") if role else None,
    }


def _relationship_id(*parts: object) -> str:
    normalized = ":".join(str(part).strip().lower() for part in parts if part is not None)
    return re.sub(r"[^a-z0-9:._-]+", "-", normalized).strip("-")


class _SourceRegistry:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def add_snapshot(self, snapshot: SourceSnapshot, *, authority: str, source_kind: str) -> str:
        record = snapshot.as_provenance(authority=authority, source_kind=source_kind)
        prior = self.records.get(snapshot.source_id)
        if prior and prior != record:
            raise ValueError(f"Conflicting snapshots for canonical URL: {snapshot.url}")
        self.records[snapshot.source_id] = record
        return snapshot.source_id

    def add_input(self, source_id: str, record: dict) -> str:
        normalized = {
            "id": source_id,
            "source_class": "input_dataset_snapshot",
            **record,
        }
        self.records[source_id] = normalized
        return source_id


class _ActorRegistry:
    def __init__(self, role_dataset_source_id: str) -> None:
        self.role_dataset_source_id = role_dataset_source_id
        self.records: dict[str, dict] = {}

    def add(self, actor: dict) -> str:
        identity = actor.get("external_role_id") or actor.get("official_actor_id")
        if not identity:
            raise ValueError("Official actor record has no stable identity")
        actor_id = f"actor:{hashlib.sha256(str(identity).encode('utf-8')).hexdigest()[:24]}"
        official_record_name = actor.pop("official_record_name", None)
        full_name = actor.pop("full_name", None)
        party = actor.pop("party", None)
        state = actor.pop("state", None)
        record = {
            "id": actor_id,
            **actor,
            "full_names": [full_name] if full_name else [],
            "official_record_names": [official_record_name] if official_record_name else [],
            "parties": [party] if party else [],
            "states": [state] if state else [],
            "role_dataset_source_id": self.role_dataset_source_id,
        }
        existing = self.records.get(actor_id)
        if existing:
            observed_fields = {"full_names", "official_record_names", "parties", "states"}
            comparable_existing = {key: value for key, value in existing.items() if key not in observed_fields}
            comparable_record = {key: value for key, value in record.items() if key not in observed_fields}
            if comparable_existing != comparable_record:
                raise ValueError(f"Conflicting actor records for {identity}")
            for field_name in observed_fields:
                existing[field_name] = sorted({*existing[field_name], *record[field_name]})
        else:
            self.records[actor_id] = record
        return actor_id


def _source_authority(url: str) -> tuple[str, str]:
    host = (urlsplit(url).hostname or "").lower()
    if host == "api.congress.gov":
        return "Congress.gov", "congress_gov_api"
    if host == "clerk.house.gov":
        return "Office of the Clerk, U.S. House of Representatives", "house_roll_call_xml"
    if host in {"senate.gov", "www.senate.gov"}:
        return "U.S. Senate", "senate_roll_call_xml"
    return host or "Official source", "official_response"


def _input_record(payload: dict, *, path: str, content_sha256: str, byte_count: int | None = None) -> dict:
    record = {
        "path": path,
        "source_tier": "derived_official_source_dataset",
        "content_sha256": content_sha256,
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "upstream_sources": payload.get("sources", []),
    }
    if byte_count is not None:
        record["byte_count"] = byte_count
    return record


def _default_input_provenance(name: str, payload: dict) -> dict:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    default_path = {
        "federal_events": "data/context/federal_events.json",
        "public_official_roles": "data/public_officials/public_official_roles.json",
    }[name]
    return {"path": default_path, "content_sha256": sha256_bytes(body), "byte_count": len(body)}


def _agency_context_relationships(event: dict, event_source_id: str) -> list[dict]:
    agencies: dict[str, set[str]] = defaultdict(set)
    for jurisdiction in event.get("jurisdiction_scope", []):
        normalized = str(jurisdiction).strip().lower()
        for agency_id in JURISDICTION_AGENCY_CROSSWALK.get(normalized, set()):
            agencies[agency_id].add(str(jurisdiction))
    relationships = []
    for agency_id, matched_terms in sorted(agencies.items()):
        agency = AGENCY_CATALOG[agency_id]
        relationships.append(
            {
                "id": _relationship_id(event["id"], "agency-jurisdiction-context", agency_id),
                "event_id": event["id"],
                "relationship_class": "contextual_routing_only",
                "relationship_type": "agency_jurisdiction_context",
                "institution": {
                    "id": f"agency:{agency_id}",
                    "name": agency["name"],
                    "official_url": agency["url"],
                },
                "matched_jurisdiction_terms": sorted(matched_terms),
                "basis": "event_jurisdiction_scope_to_agency_crosswalk_v1",
                "source_snapshot_ids": [event_source_id],
                "official_event_source_urls": sorted(set(event.get("sources", []))),
                "scope_note": (
                    "Topic-routing context only. This does not establish formal legal jurisdiction, agency action, "
                    "staff awareness, participation, or any individual's knowledge."
                ),
            }
        )
    return relationships


def _presidential_context_relationship(
    event: dict,
    role_index: PublicOfficialRoleIndex,
    event_source_id: str,
    roles_source_id: str,
) -> dict | None:
    if event.get("event_type") not in {"executive_order", "legislation", "funding"}:
        return None
    event_date = event.get("date")
    if not event_date:
        return None
    president = role_index.president_on(event_date)
    if not president:
        return None
    context_type = (
        "presidential_executive_order_context"
        if event.get("event_type") == "executive_order"
        else "presidential_enactment_context"
    )
    return {
        "id": _relationship_id(event["id"], context_type, president.get("external_role_id")),
        "event_id": event["id"],
        "relationship_class": "temporal_officeholder_context_only",
        "relationship_type": context_type,
        "context_date": event_date,
        "actor": {
            "external_person_id": president.get("external_person_id"),
            "external_role_id": president.get("external_role_id"),
            "full_name": president.get("full_name"),
            "role_title": president.get("role_title"),
            "presidential_term": president.get("presidential_term"),
            "role_source_url": president.get("source_url"),
        },
        "basis": "president_in_office_on_event_date",
        "source_snapshot_ids": [event_source_id, roles_source_id],
        "official_event_source_urls": sorted(set(event.get("sources", []))),
        "scope_note": (
            "Temporal officeholder context only. It does not independently establish a signing act, personal "
            "participation, awareness, intent, or knowledge beyond what the cited event record expressly states."
        ),
    }


def _court_context_relationship(
    event: dict,
    role_index: PublicOfficialRoleIndex,
    event_source_id: str,
    roles_source_id: str,
) -> dict | None:
    if event.get("event_type") != "court_decision" or not event.get("court") or not event.get("docket_number"):
        return None
    court = str(event["court"])
    court_id = re.sub(r"[^a-z0-9]+", "-", court.lower()).strip("-")
    return {
        "id": _relationship_id(event["id"], "court-docket-institutional-link", court_id),
        "event_id": event["id"],
        "relationship_class": "direct_institutional_record",
        "relationship_type": "court_docket_institutional_link",
        "institution": {
            "id": f"court:{court_id}",
            "name": court,
            "catalog_resolution_status": (
                "matched_public_official_roles_court_catalog"
                if court in role_index.courts
                else "not_present_in_public_official_roles_court_catalog"
            ),
        },
        "docket_number": event["docket_number"],
        "decision_date": event.get("date"),
        "citation": event.get("citation"),
        "source_snapshot_ids": [event_source_id, roles_source_id],
        "official_event_source_urls": sorted(set(event.get("sources", []))),
        "scope_note": (
            "Institution-and-docket link only. It does not identify an individual judge's participation, vote, "
            "awareness, or knowledge."
        ),
    }


def _collect_recorded_votes(actions: Iterable[dict]) -> list[dict]:
    collected: dict[tuple[str, int, int, int], dict] = {}
    for action in actions:
        for vote in action.get("recordedVotes") or []:
            try:
                key = (
                    str(vote["chamber"]),
                    int(vote["congress"]),
                    int(vote["sessionNumber"]),
                    int(vote["rollNumber"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Malformed Congress.gov recorded vote: {vote}") from exc
            record = collected.setdefault(
                key,
                {
                    "chamber": key[0],
                    "congress": key[1],
                    "session": key[2],
                    "roll_number": key[3],
                    "url": vote.get("url"),
                    "recorded_at": vote.get("date"),
                    "action_texts": set(),
                    "action_types": set(),
                    "action_dates": set(),
                },
            )
            if vote.get("url") and record.get("url") and vote["url"] != record["url"]:
                raise ValueError(f"Conflicting URLs for recorded vote {key}")
            record["url"] = record.get("url") or vote.get("url")
            if action.get("text"):
                record["action_texts"].add(str(action["text"]))
            if action.get("type"):
                record["action_types"].add(str(action["type"]))
            if action.get("actionDate"):
                record["action_dates"].add(str(action["actionDate"]))
    result = []
    for key in sorted(collected):
        record = collected[key]
        record["action_texts"] = sorted(record["action_texts"])
        record["action_types"] = sorted(record["action_types"])
        record["action_dates"] = sorted(record["action_dates"])
        if not record.get("url"):
            raise ValueError(f"Congress.gov recorded vote has no official XML URL: {key}")
        result.append(record)
    return result


def _validate_roll_call(parsed: dict, descriptor: dict) -> None:
    expected = (
        descriptor["chamber"].lower(),
        int(descriptor["congress"]),
        int(descriptor["session"]),
        int(descriptor["roll_number"]),
    )
    actual = (
        parsed["chamber"].lower(),
        int(parsed["congress"]),
        int(parsed["session"]),
        int(parsed["roll_number"]),
    )
    if actual != expected:
        raise ValueError(f"Roll-call XML identity mismatch: expected {expected}, received {actual}")


def _legislative_relationship(
    *,
    event: dict,
    relationship_type: str,
    row: dict,
    role: dict | None,
    relationship_date: str | None,
    source_snapshot_ids: Iterable[str],
    actor_registry: _ActorRegistry,
    fallback_actor_id: str | None = None,
    roll_call_id: str | None = None,
    record_instance_id: str | None = None,
) -> dict:
    actor = _actor_record(row, role, fallback_id=fallback_actor_id)
    actor_id = actor.get("official_actor_id") or "unresolved-actor"
    actor_record_id = actor_registry.add(actor)
    relationship = {
        "id": _relationship_id(
            event["id"], relationship_type, roll_call_id, actor_id, record_instance_id
        ),
        "event_id": event["id"],
        "relationship_type": relationship_type,
        "relationship_date": relationship_date,
        "actor_id": actor_record_id,
    }
    normalized_source_ids = sorted(set(source_snapshot_ids))
    if normalized_source_ids:
        relationship["source_snapshot_ids"] = normalized_source_ids
    if relationship_type == "cosponsor":
        relationship["is_original_cosponsor"] = bool(row.get("isOriginalCosponsor"))
        relationship["sponsorship_withdrawn_date"] = row.get("sponsorshipWithdrawnDate")
    elif relationship_type == "recorded_vote":
        vote_cast = row.get("vote_cast")
        relationship.update(
            {
                "roll_call_id": roll_call_id,
                "vote_cast": vote_cast,
                "participation_status": (
                    "not_voting" if str(vote_cast).strip().lower() in {"not voting", "absent"} else "recorded_position"
                ),
            }
        )
    return relationship


def build_official_event_involvement(
    federal_events: dict,
    public_official_roles: dict,
    congress_client: OfficialCongressGovClient,
    *,
    input_provenance: dict[str, dict] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    events = [event for event in federal_events.get("events", []) if isinstance(event, dict)]
    role_index = build_role_index(public_official_roles)
    registry = _SourceRegistry()
    input_provenance = input_provenance or {}

    event_provenance = input_provenance.get("federal_events") or _default_input_provenance(
        "federal_events", federal_events
    )
    roles_provenance = input_provenance.get("public_official_roles") or _default_input_provenance(
        "public_official_roles", public_official_roles
    )
    event_source_id = registry.add_input(
        "input:federal-events",
        _input_record(federal_events, **event_provenance),
    )
    roles_source_id = registry.add_input(
        "input:public-official-roles",
        _input_record(public_official_roles, **roles_provenance),
    )
    actor_registry = _ActorRegistry(roles_source_id)

    relationships: list[dict] = []
    event_records: list[dict] = []
    bill_records: list[dict] = []
    roll_calls: dict[str, dict] = {}
    legislative_events = [event for event in events if parse_bill_reference(event)]
    legislative_position = 0

    for event in sorted(events, key=lambda row: (row.get("date") or "", row.get("id") or "")):
        event_start = len(relationships)
        relationships.extend(_agency_context_relationships(event, event_source_id))
        presidential = _presidential_context_relationship(event, role_index, event_source_id, roles_source_id)
        if presidential:
            relationships.append(presidential)
        court = _court_context_relationship(event, role_index, event_source_id, roles_source_id)
        if court:
            relationships.append(court)

        bill_reference = parse_bill_reference(event)
        bill_record = None
        if bill_reference:
            legislative_position += 1
            congress, bill_type, number = bill_reference
            if progress:
                progress(
                    f"Legislative event {legislative_position}/{len(legislative_events)}: "
                    f"{congress} {bill_type.upper()} {number}"
                )
            detail, detail_snapshot = congress_client.bill_detail(congress, bill_type, number)
            cosponsors, cosponsor_snapshots = congress_client.bill_cosponsors(congress, bill_type, number)
            actions, action_snapshots = congress_client.bill_actions(congress, bill_type, number)
            detail_source_id = registry.add_snapshot(
                detail_snapshot,
                authority="Congress.gov",
                source_kind="bill_detail_api",
            )
            cosponsor_source_ids = [
                registry.add_snapshot(snapshot, authority="Congress.gov", source_kind="bill_cosponsors_api")
                for snapshot in cosponsor_snapshots
            ]
            action_source_ids = [
                registry.add_snapshot(snapshot, authority="Congress.gov", source_kind="bill_actions_api")
                for snapshot in action_snapshots
            ]
            if (
                int(detail.get("congress", -1)) != congress
                or str(detail.get("type", "")).lower() != bill_type
                or str(detail.get("number")) != number
            ):
                raise ValueError(f"Congress.gov bill detail identity mismatch for event {event['id']}")

            chamber = "Senate" if bill_type.startswith("s") else "House"
            introduced_date = detail.get("introducedDate")
            for sponsor in detail.get("sponsors") or []:
                role = role_index.resolve_bioguide(sponsor.get("bioguideId"), congress, chamber, introduced_date)
                relationships.append(
                    _legislative_relationship(
                        event=event,
                        relationship_type="sponsor",
                        row=sponsor,
                        role=role,
                        relationship_date=introduced_date,
                        source_snapshot_ids=[detail_source_id],
                        actor_registry=actor_registry,
                    )
                )
            for cosponsor in cosponsors:
                sponsorship_date = cosponsor.get("sponsorshipDate")
                role = role_index.resolve_bioguide(
                    cosponsor.get("bioguideId"), congress, chamber, sponsorship_date or introduced_date
                )
                relationships.append(
                    _legislative_relationship(
                        event=event,
                        relationship_type="cosponsor",
                        row=cosponsor,
                        role=role,
                        relationship_date=sponsorship_date,
                        source_snapshot_ids=cosponsor_source_ids,
                        actor_registry=actor_registry,
                        record_instance_id="-".join(
                            filter(
                                None,
                                [
                                    str(sponsorship_date or "date-unknown"),
                                    str(cosponsor.get("sponsorshipWithdrawnDate") or "active"),
                                ],
                            )
                        ),
                    )
                )

            related_roll_call_ids = []
            for vote_descriptor in _collect_recorded_votes(actions):
                vote_url = str(vote_descriptor["url"])
                vote_host = (urlsplit(vote_url).hostname or "").lower()
                if vote_host not in ALLOWED_ROLL_CALL_HOSTS or urlsplit(vote_url).scheme != "https":
                    raise ValueError(f"Unapproved roll-call source URL: {vote_url}")
                vote_snapshot = congress_client.http.get(vote_url)
                authority, source_kind = _source_authority(vote_url)
                vote_source_id = registry.add_snapshot(
                    vote_snapshot,
                    authority=authority,
                    source_kind=source_kind,
                )
                parsed_vote = parse_roll_call(vote_snapshot.body, vote_descriptor["chamber"])
                _validate_roll_call(parsed_vote, vote_descriptor)
                roll_call_id = parsed_vote["id"]
                related_roll_call_ids.append(roll_call_id)
                roll_call = {
                    key: value for key, value in parsed_vote.items() if key != "members"
                }
                roll_call.update(
                    {
                        "related_event_ids": [event["id"]],
                        "congress_gov_action_texts": vote_descriptor["action_texts"],
                        "congress_gov_action_types": vote_descriptor["action_types"],
                        "congress_gov_action_dates": vote_descriptor["action_dates"],
                        "recorded_at": vote_descriptor.get("recorded_at"),
                        "official_source_url": vote_url,
                        "source_snapshot_ids": sorted({vote_source_id, *action_source_ids}),
                        "scope_note": (
                            "This roll call is linked through the bill's Congress.gov action record. Its question "
                            "and result define the scope; procedural votes are not treated as final-law positions."
                        ),
                    }
                )
                if roll_call_id in roll_calls:
                    existing = roll_calls[roll_call_id]
                    if existing["official_source_url"] != vote_url:
                        raise ValueError(f"Conflicting official source URLs for roll call {roll_call_id}")
                    existing["related_event_ids"] = sorted({*existing["related_event_ids"], event["id"]})
                    existing["source_snapshot_ids"] = sorted(
                        {*existing["source_snapshot_ids"], *roll_call["source_snapshot_ids"]}
                    )
                    existing["congress_gov_action_texts"] = sorted(
                        {*existing["congress_gov_action_texts"], *roll_call["congress_gov_action_texts"]}
                    )
                    existing["congress_gov_action_types"] = sorted(
                        {*existing["congress_gov_action_types"], *roll_call["congress_gov_action_types"]}
                    )
                    existing["congress_gov_action_dates"] = sorted(
                        {*existing["congress_gov_action_dates"], *roll_call["congress_gov_action_dates"]}
                    )
                else:
                    roll_calls[roll_call_id] = roll_call

                vote_date = parsed_vote.get("vote_date") or (vote_descriptor.get("recorded_at") or "")[:10]
                for member in parsed_vote["members"]:
                    if parsed_vote["chamber"] == "House":
                        role = role_index.resolve_bioguide(
                            member.get("bioguide_id"), congress, "House", vote_date
                        )
                        fallback_actor_id = None
                    else:
                        role = role_index.resolve_senate_member(
                            first_name=member.get("first_name"),
                            last_name=member.get("last_name"),
                            state=member.get("state"),
                            congress=congress,
                            event_date=vote_date,
                        )
                        fallback_actor_id = (
                            f"senate-lis:{member['lis_member_id']}" if member.get("lis_member_id") else None
                        )
                    relationships.append(
                        _legislative_relationship(
                            event=event,
                            relationship_type="recorded_vote",
                            row=member,
                            role=role,
                            relationship_date=vote_date,
                            source_snapshot_ids=[],
                            actor_registry=actor_registry,
                            fallback_actor_id=fallback_actor_id,
                            roll_call_id=roll_call_id,
                        )
                    )

            public_laws = [
                law.get("number")
                for law in detail.get("laws") or []
                if law.get("type") == "Public Law" and law.get("number")
            ]
            bill_record = {
                "event_id": event["id"],
                "congress": congress,
                "bill_type": str(detail.get("type") or bill_type).upper(),
                "bill_number": str(detail.get("number") or number),
                "title": detail.get("title") or event.get("label"),
                "introduced_date": introduced_date,
                "origin_chamber": detail.get("originChamber"),
                "public_law_numbers": sorted(public_laws),
                "event_law_number": event.get("law_number"),
                "event_law_number_match": event.get("law_number") in public_laws,
                "congress_url": (event.get("sources") or [None])[0],
                "source_snapshot_ids": sorted(
                    {detail_source_id, *cosponsor_source_ids, *action_source_ids}
                ),
                "roll_call_ids": sorted(set(related_roll_call_ids)),
            }
            bill_records.append(bill_record)

        event_relationships = relationships[event_start:]
        event_records.append(
            {
                "event_id": event.get("id"),
                "event_type": event.get("event_type"),
                "date": event.get("date"),
                "label": event.get("label"),
                "official_source_urls": sorted(set(event.get("sources", []))),
                "relationship_counts": dict(
                    sorted(Counter(row["relationship_type"] for row in event_relationships).items())
                ),
                "bill_record_available": bill_record is not None,
            }
        )

    relationship_ids = [relationship["id"] for relationship in relationships]
    if len(relationship_ids) != len(set(relationship_ids)):
        duplicates = [item for item, count in Counter(relationship_ids).items() if count > 1]
        raise ValueError(f"Duplicate relationship IDs: {duplicates[:5]}")

    relationships.sort(key=lambda row: (row["event_id"], row["relationship_type"], row["id"]))
    event_records.sort(key=lambda row: (row.get("date") or "", row.get("event_id") or ""))
    bill_records.sort(key=lambda row: (row["congress"], row["bill_type"], int(row["bill_number"])))
    roll_call_records = sorted(
        roll_calls.values(),
        key=lambda row: (row["congress"], row["chamber"], row["session"], row["roll_number"]),
    )
    source_records = sorted(registry.records.values(), key=lambda row: row["id"])
    actor_records = sorted(actor_registry.records.values(), key=lambda row: row["id"])
    source_dates = [
        str(record.get("retrieved_at") or record.get("generated_at") or "")[:10]
        for record in source_records
        if record.get("retrieved_at") or record.get("generated_at")
    ]
    dataset_as_of = max(source_dates) if source_dates else None
    relationship_type_counts = Counter(row["relationship_type"] for row in relationships)
    relationship_class_counts = Counter(
        "direct_official_record"
        if row["relationship_type"] in DIRECT_RELATIONSHIP_TYPES
        else row["relationship_class"]
        for row in relationships
    )
    actor_resolution_counts = Counter(
        actor_registry.records[row["actor_id"]]["resolution_status"]
        for row in relationships
        if row.get("relationship_type") in DIRECT_RELATIONSHIP_TYPES and row.get("actor_id")
    )
    vote_cast_counts = Counter(
        row["vote_cast"] for row in relationships if row.get("relationship_type") == "recorded_vote"
    )
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "generated_at": dataset_as_of,
        "scope": {
            "event_input_count": len(events),
            "event_date_start": min((event.get("date") for event in events if event.get("date")), default=None),
            "event_date_end": max((event.get("date") for event in events if event.get("date")), default=None),
            "legislative_source_endpoints": ["bill detail", "bill cosponsors", "bill actions"],
            "roll_call_sources": [
                "Office of the Clerk, U.S. House of Representatives XML",
                "U.S. Senate roll-call XML",
            ],
        },
        "methodology": {
            "direct_relationship_types": sorted(DIRECT_RELATIONSHIP_TYPES),
            "relationship_type_definitions": {
                "sponsor": {
                    "relationship_class": "direct_official_record",
                    "record_scope": "Congress.gov bill sponsor record.",
                    "evidence_path": "relationship.source_snapshot_ids -> sources",
                },
                "cosponsor": {
                    "relationship_class": "direct_official_record",
                    "record_scope": (
                        "Congress.gov bill cosponsorship period, including withdrawal and readdition history."
                    ),
                    "evidence_path": "relationship.source_snapshot_ids -> sources",
                },
                "recorded_vote": {
                    "relationship_class": "direct_official_record",
                    "record_scope": (
                        "Position recorded on the specific roll-call question; not by itself a final-law position."
                    ),
                    "evidence_path": "relationship.roll_call_id -> roll_calls.source_snapshot_ids -> sources",
                },
            },
            "context_relationship_types": [
                "presidential_executive_order_context",
                "presidential_enactment_context",
                "agency_jurisdiction_context",
                "court_docket_institutional_link",
            ],
            "offline_determinism": (
                "Canonical URLs exclude API credentials. Cached response bodies, retrieval timestamps, and hashes "
                "are reused verbatim; output ordering and generated_at are derived only from source snapshots."
            ),
            "vote_scope": (
                "Each vote preserves the specific official roll-call question. A procedural or amendment vote is "
                "not reclassified as support for or opposition to the final law."
            ),
            "context_limit": (
                "Presidential entries are temporal officeholder context; agency links are topic-routing context; "
                "court links are institution-and-docket context. None establishes individual awareness, knowledge, "
                "intent, or participation beyond an expressly cited official record."
            ),
            "agency_crosswalk": {
                jurisdiction: sorted(agency_ids)
                for jurisdiction, agency_ids in sorted(JURISDICTION_AGENCY_CROSSWALK.items())
            },
        },
        "summary": {
            "event_count": len(event_records),
            "legislative_event_count": len(bill_records),
            "bill_record_count": len(bill_records),
            "roll_call_count": len(roll_call_records),
            "relationship_count": len(relationships),
            "actor_record_count": len(actor_records),
            "relationship_counts_by_type": dict(sorted(relationship_type_counts.items())),
            "relationship_counts_by_class": dict(sorted(relationship_class_counts.items())),
            "actor_resolution_counts": dict(sorted(actor_resolution_counts.items())),
            "vote_cast_counts": dict(sorted(vote_cast_counts.items())),
            "source_snapshot_count": len(source_records),
        },
        "sources": source_records,
        "actors": actor_records,
        "events": event_records,
        "bills": bill_records,
        "roll_calls": roll_call_records,
        "relationships": relationships,
        "context_label": (
            "Direct legislative involvement is limited to official sponsor, cosponsor, and specific roll-call "
            "records. All other links are labeled institutional or temporal context and do not imply individual "
            "knowledge, intent, wrongdoing, or a relationship to any financial transaction."
        ),
    }
