from datetime import date

from app.services.judicial_disclosures import (
    build_judicial_disclosure_manifest,
    service_years,
)


def test_service_years_clamps_to_research_window_and_as_of():
    assert service_years(
        "2007-05-01", "2011-03-02", start_year=2009, as_of=date(2026, 7, 12)
    ) == [2009, 2010, 2011]
    assert service_years(
        "2025-01-01", None, start_year=2009, as_of=date(2026, 7, 12)
    ) == [2025, 2026]


def test_manifest_preserves_periods_without_claiming_document_absence():
    roster = {
        "people": [
            {
                "external_person_id": "fjc:judge-example",
                "full_name": "Judge Example",
                "branch": "Judicial",
                "roles": ["role-1", "role-2"],
            }
        ],
        "roles": [
            {
                "external_person_id": "fjc:judge-example",
                "external_role_id": "role-1",
                "full_name": "Judge Example",
                "branch": "Judicial",
                "role_category": "article_iii_judge",
                "role_title": "District Judge",
                "court": "Example District Court",
                "service_start": "2008-06-01",
                "service_end": "2012-03-01",
                "source_url": "https://www.fjc.gov/example",
                "source_metadata": {"sequence": "1"},
            },
            {
                "external_person_id": "fjc:judge-example",
                "external_role_id": "role-2",
                "full_name": "Judge Example",
                "branch": "Judicial",
                "role_category": "article_iii_judge",
                "role_title": "Circuit Judge",
                "court": "Example Circuit Court",
                "service_start": "2012-03-02",
                "service_end": None,
                "source_url": "https://www.fjc.gov/example",
                "source_metadata": {"sequence": "2"},
            },
        ],
    }

    payload = build_judicial_disclosure_manifest(
        roster,
        start_year=2009,
        as_of=date(2014, 7, 1),
        roster_sha256="a" * 64,
    )

    assert payload["summary"] == {
        "official_count": 1,
        "role_count": 2,
        "research_year_count": 6,
        "active_officials_by_year": {
            "2009": 1,
            "2010": 1,
            "2011": 1,
            "2012": 1,
            "2013": 1,
            "2014": 1,
        },
        "indexed_document_count": 0,
        "reviewed_trade_count": 0,
    }
    official = payload["officials"][0]
    assert official["research_years"] == [2009, 2010, 2011, 2012, 2013, 2014]
    assert len(official["service_periods"]) == 2
    assert official["document_status"]["absence_inference_allowed"] is False
    assert payload["access_policy"]["automated_document_acquisition"] is False
