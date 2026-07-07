from pathlib import Path

from app.services.congress_sources import (
    chamber_label,
    display_name_from_congress_gov,
    parse_house_current_members_xml,
    parse_senate_current_members_xml,
    role_category_for_chamber,
    role_title_for_category,
    state_code,
)


FIXTURES = Path(__file__).parent / "fixtures" / "congress"


def test_house_current_member_parser_normalizes_bioguide_and_districts():
    members = parse_house_current_members_xml((FIXTURES / "house_current_members.xml").read_text())

    assert len(members) == 2
    assert members[0].bioguide_id == "B001323"
    assert members[0].full_name == "Nicholas J. Begich III"
    assert members[0].chamber == "House"
    assert members[0].state == "AK"
    assert members[0].district == "At Large"
    assert members[0].party == "Republican"
    assert members[0].sworn_date == "20250103"
    assert members[0].source_metadata["congress_number"] == 119


def test_senate_current_member_parser_normalizes_contact_xml():
    members = parse_senate_current_members_xml((FIXTURES / "senate_current_members.xml").read_text())

    assert len(members) == 2
    assert members[0].bioguide_id == "A000382"
    assert members[0].full_name == "Angela D. Alsobrooks"
    assert members[0].chamber == "Senate"
    assert members[0].state == "MD"
    assert members[0].party == "Democratic"
    assert members[0].source_metadata["class"] == "Class I"


def test_congress_helpers_keep_legislative_labels_stable():
    assert state_code("California") == "CA"
    assert chamber_label("House of Representatives") == "House"
    assert chamber_label("Senate") == "Senate"
    assert display_name_from_congress_gov("Gallagher, James") == "James Gallagher"
    assert role_category_for_chamber("House", state="PR", district="At Large") == "resident_commissioner"
    assert role_title_for_category("senator") == "U.S. Senator"
