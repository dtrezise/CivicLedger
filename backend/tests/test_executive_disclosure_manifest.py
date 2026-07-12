from datetime import date

from app.services.executive_disclosures import build_executive_disclosure_manifest


def test_manifest_links_known_documents_and_keeps_unknowns_noninferential():
    roster = {
        "people": [
            {"external_person_id": "exec:president", "full_name": "President Example", "branch": "Executive"},
            {"external_person_id": "exec:secretary", "full_name": "Secretary Example", "branch": "Executive"},
        ],
        "roles": [
            {
                "external_person_id": "exec:president", "external_role_id": "role-president",
                "branch": "Executive", "role_category": "elected_executive", "role_title": "President",
                "office": "President of the United States", "agency": "Executive Office of the President",
                "presidential_term": "example-1", "service_start": "2021-01-20", "service_end": "2025-01-20",
                "source_url": "https://example.gov/president",
            },
            {
                "external_person_id": "exec:secretary", "external_role_id": "role-secretary",
                "branch": "Executive", "role_category": "cabinet", "role_title": "Secretary",
                "office": "Secretary of Examples", "agency": "Department of Examples",
                "presidential_term": "example-1", "service_start": "2022-01-01", "service_end": None,
                "source_url": "https://example.gov/secretary",
            },
        ],
    }
    documents = {
        "documents": [
            {
                "official_id": "exec:president", "document_id": "doc-1", "document_type": "OGE Form 278e",
                "filing_date": "2024-05-15", "source_url": "https://oge.gov/doc-1", "file_sha256": "a" * 64,
                "document_status": "parser_preview",
            }
        ]
    }

    payload = build_executive_disclosure_manifest(
        roster, documents, first_year=2009, as_of=date(2026, 7, 12)
    )

    assert payload["summary"]["official_count"] == 2
    assert payload["summary"]["indexed_document_count"] == 1
    by_id = {row["official_id"]: row for row in payload["officials"]}
    assert by_id["exec:president"]["document_status"]["indexed_document_count"] == 1
    assert by_id["exec:secretary"]["document_status"]["state"] == "metadata_only_collection_search_pending"
    assert by_id["exec:secretary"]["document_status"]["absence_inference_allowed"] is False
    assert by_id["exec:secretary"]["research_years"] == [2022, 2023, 2024, 2025, 2026]
