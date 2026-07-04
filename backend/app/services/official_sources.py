from app.config import settings


OFFICIAL_SOURCES = [
    {
        "id": "house-financial-disclosure",
        "name": "House Financial Disclosure Reports",
        "chamber": "House",
        "source_url": "https://disclosures-clerk.house.gov/FinancialDisclosure",
        "search_url": "https://disclosures-clerk.house.gov/FinancialDisclosure/ViewSearch",
        "download_url": "https://disclosures-clerk.house.gov/FinancialDisclosure",
        "ingestion_status": "planned",
        "records_scope": "Member, staff, and candidate financial disclosure reports published by the Office of the Clerk.",
        "rights_note": (
            "The House search page states statutory restrictions on use of financial "
            "disclosure information and notes redaction of certain personally identifiable "
            "information. CivicLedger must preserve this notice before ingesting or exporting records."
        ),
        "provenance_requirements": [
            "Persist the source URL used for the search or download.",
            "Archive the raw document or index payload before parsing.",
            "Record retrieval timestamp, retrieval source, file hash, parser version, and dataset version.",
            "Mark records as fixture/demo until an official-source ingestion run completes.",
        ],
    },
    {
        "id": "senate-public-financial-disclosure",
        "name": "Senate Public Financial Disclosure Database",
        "chamber": "Senate",
        "source_url": "https://www.disclosure.senate.gov/",
        "search_url": "https://efdsearch.senate.gov/",
        "download_url": None,
        "ingestion_status": "planned",
        "records_scope": "Senate public financial disclosures and periodic transaction reports maintained through public disclosure systems.",
        "rights_note": (
            "The Senate public disclosure page identifies the Senate Public Financial Disclosure "
            "Database as the public search entry point and describes STOCK Act transaction "
            "reporting for Senators and senior staff."
        ),
        "provenance_requirements": [
            "Persist the official disclosure database URL used for retrieval.",
            "Store raw response or document artifacts before normalized rows are created.",
            "Record retrieval timestamp, retrieval source, file hash, parser version, and dataset version.",
            "Keep chamber-specific parsing separate until field mappings are verified.",
        ],
    },
]


def get_official_sources_response() -> dict:
    return {
        "dataset_version": settings.DATASET_VERSION,
        "methodology_version": settings.METHODOLOGY_VERSION,
        "sources": OFFICIAL_SOURCES,
    }
