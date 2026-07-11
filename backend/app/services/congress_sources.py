from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from http.client import IncompleteRead
import json
import time
from typing import Iterable
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from app.config import settings


CONGRESS_GOV_BASE_URL = "https://api.congress.gov/v3"
HOUSE_CURRENT_MEMBERS_XML_URL = "https://clerk.house.gov/xml/lists/memberdata.xml"
SENATE_CURRENT_MEMBERS_XML_URL = "https://www.senate.gov/general/contact_information/senators_cfm.xml"
USER_AGENT = "CivicLedger data refresh"

STATE_ABBREVIATIONS = {
    "Alabama": "AL",
    "Alaska": "AK",
    "American Samoa": "AS",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Guam": "GU",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Northern Mariana Islands": "MP",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Puerto Rico": "PR",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "U.S. Virgin Islands": "VI",
    "Virgin Islands": "VI",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}

PARTY_NAMES = {
    "D": "Democratic",
    "Democrat": "Democratic",
    "Democratic": "Democratic",
    "I": "Independent",
    "Independent": "Independent",
    "R": "Republican",
    "Republican": "Republican",
}


@dataclass(frozen=True)
class CurrentCongressionalMember:
    bioguide_id: str
    full_name: str
    chamber: str
    state: str
    party: str
    district: str | None = None
    sworn_date: str | None = None
    source_url: str | None = None
    source_metadata: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _request_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def _text(element: ET.Element | None, path: str) -> str | None:
    if element is None:
        return None
    child = element.find(path)
    if child is None or child.text is None:
        return None
    value = " ".join(child.text.split()).strip()
    return value or None


def _party_name(value: str | None) -> str | None:
    if not value:
        return None
    return PARTY_NAMES.get(value.strip(), value.strip())


def state_code(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 2 and value.isupper():
        return value
    return STATE_ABBREVIATIONS.get(value, value)


def display_name_from_congress_gov(value: str) -> str:
    value = " ".join(value.split()).strip()
    if "," not in value:
        return value
    last, rest = [piece.strip() for piece in value.split(",", 1)]
    return f"{rest} {last}".strip()


def chamber_label(value: str | None) -> str:
    if not value:
        return "House"
    if "senate" in value.lower():
        return "Senate"
    return "House"


def role_category_for_chamber(chamber: str, state: str | None = None, district: str | None = None) -> str:
    if chamber == "Senate":
        return "senator"
    if state in {"AS", "DC", "GU", "MP", "PR", "VI"}:
        return "resident_commissioner" if state == "PR" else "delegate"
    if district in {None, "", "At Large"} and state in {"AS", "DC", "GU", "MP", "PR", "VI"}:
        return "delegate"
    return "representative"


def role_title_for_category(category: str) -> str:
    return {
        "senator": "U.S. Senator",
        "representative": "U.S. Representative",
        "delegate": "Delegate to the U.S. House of Representatives",
        "resident_commissioner": "Resident Commissioner",
    }.get(category, "Member of Congress")


def parse_house_current_members_xml(xml_text: str) -> list[CurrentCongressionalMember]:
    root = ET.fromstring(xml_text)
    publish_date = root.attrib.get("publish-date")
    congress_number = _text(root, "title-info/congress-num")
    members = []
    for member in root.findall("./members/member"):
        info = member.find("member-info")
        bioguide_id = _text(info, "bioguideID")
        full_name = _text(info, "official-name") or _text(info, "namelist")
        state_node = info.find("state") if info is not None else None
        state = state_node.attrib.get("postal-code") if state_node is not None else None
        if not bioguide_id or not full_name or not state:
            continue
        district = _text(info, "district")
        party = _party_name(_text(info, "party")) or "Unknown"
        sworn = info.find("sworn-date") if info is not None else None
        members.append(
            CurrentCongressionalMember(
                bioguide_id=bioguide_id,
                full_name=full_name,
                chamber="House",
                state=state,
                district=district,
                party=party,
                sworn_date=sworn.attrib.get("date") if sworn is not None else None,
                source_url=HOUSE_CURRENT_MEMBERS_XML_URL,
                source_metadata={
                    "congress_number": int(congress_number) if congress_number else None,
                    "publish_date": publish_date,
                    "state_district": _text(member, "statedistrict"),
                    "prior_congress": _text(info, "prior-congress"),
                },
            )
        )
    return members


def parse_senate_current_members_xml(xml_text: str) -> list[CurrentCongressionalMember]:
    root = ET.fromstring(xml_text)
    members = []
    for member in root.findall("./member"):
        bioguide_id = _text(member, "bioguide_id")
        first_name = _text(member, "first_name")
        last_name = _text(member, "last_name")
        state = _text(member, "state")
        if not bioguide_id or not first_name or not last_name or not state:
            continue
        members.append(
            CurrentCongressionalMember(
                bioguide_id=bioguide_id,
                full_name=f"{first_name} {last_name}",
                chamber="Senate",
                state=state,
                district=None,
                party=_party_name(_text(member, "party")) or "Unknown",
                sworn_date=None,
                source_url=SENATE_CURRENT_MEMBERS_XML_URL,
                source_metadata={
                    "member_full": _text(member, "member_full"),
                    "class": _text(member, "class"),
                    "website": _text(member, "website"),
                },
            )
        )
    return members


def fetch_house_current_members() -> list[CurrentCongressionalMember]:
    return parse_house_current_members_xml(_request_text(HOUSE_CURRENT_MEMBERS_XML_URL))


def fetch_senate_current_members() -> list[CurrentCongressionalMember]:
    return parse_senate_current_members_xml(_request_text(SENATE_CURRENT_MEMBERS_XML_URL))


class CongressGovClient:
    def __init__(self, api_key: str | None = None, base_url: str = CONGRESS_GOV_BASE_URL) -> None:
        self.api_key = api_key or settings.CONGRESS_GOV_API_KEY
        self.base_url = base_url.rstrip("/")

    def _get_json(self, path: str, params: dict | None = None, retries: int = 3) -> dict:
        if not self.api_key:
            raise RuntimeError("CONGRESS_GOV_API_KEY is required for live Congress.gov refreshes")
        query = urlencode({**(params or {}), "api_key": self.api_key})
        request = Request(f"{self.base_url}{path}?{query}", headers={"User-Agent": USER_AGENT})
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                with urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (IncompleteRead, TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == retries:
                    break
                time.sleep(attempt * 1.5)
        raise RuntimeError(f"Congress.gov request failed after {retries} attempts: {path}") from last_error

    def members_by_congress(self, congress_number: int, limit: int = 250) -> list[dict]:
        members: list[dict] = []
        offset = 0
        while True:
            payload = self._get_json(
                f"/member/congress/{congress_number}",
                {"format": "json", "limit": limit, "offset": offset},
            )
            batch = payload.get("members", [])
            members.extend(batch)
            if not payload.get("pagination", {}).get("next") or not batch:
                break
            offset += limit
        return members

    def laws_by_congress(self, congress_number: int, limit: int = 250) -> list[dict]:
        laws: list[dict] = []
        offset = 0
        while True:
            payload = self._get_json(
                f"/law/{congress_number}",
                {"format": "json", "limit": limit, "offset": offset},
            )
            batch = payload.get("bills", [])
            laws.extend(batch)
            if not payload.get("pagination", {}).get("next") or not batch:
                break
            offset += limit
        return laws


def congressional_member_dicts(members: Iterable[CurrentCongressionalMember]) -> list[dict]:
    return [member.as_dict() for member in members]
