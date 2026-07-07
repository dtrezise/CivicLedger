from app.config import settings


OFFICIAL_SOURCES = [
    {
        "id": "house-financial-disclosure",
        "name": "House Financial Disclosure Reports",
        "branch": "Legislative",
        "chamber": "House",
        "source_url": "https://disclosures-clerk.house.gov/FinancialDisclosure",
        "search_url": "https://disclosures-clerk.house.gov/FinancialDisclosure/ViewSearch",
        "download_url": "https://disclosures-clerk.house.gov/FinancialDisclosure",
        "access_mode": "public_portal",
        "public_sample_url": None,
        "ingestion_status": "parser_preview_ready",
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
        "branch": "Legislative",
        "chamber": "Senate",
        "source_url": "https://www.disclosure.senate.gov/",
        "search_url": "https://efdsearch.senate.gov/",
        "download_url": None,
        "access_mode": "public_portal_acknowledged",
        "public_sample_url": None,
        "ingestion_status": "parser_preview_ready",
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
    {
        "id": "oge-individual-disclosures",
        "name": "OGE Officials' Individual Disclosures",
        "branch": "Executive",
        "chamber": None,
        "source_url": "https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm=",
        "search_url": "https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm=",
        "download_url": None,
        "access_mode": "direct_public_document_or_acknowledged_portal",
        "public_sample_url": "https://www.oge.gov/Web/oge.nsf/OGE%20Forms/FE904FADB163B45A852585B6005A23E8/%24FILE/OGE%20Form%20278e%20Public%20Financial%20Disclosure%20Report.pdf?open=",
        "ingestion_status": "source_index_ready",
        "records_scope": "Executive branch public financial disclosure documents, including OGE Form 278e annual reports and OGE Form 278-T periodic transaction reports where available.",
        "rights_note": (
            "OGE displays statutory restrictions on obtaining or using public financial "
            "disclosure reports, including restrictions on unlawful, commercial, credit-rating, "
            "and solicitation uses. CivicLedger must preserve this notice before ingestion, "
            "export, or share-card use."
        ),
        "provenance_requirements": [
            "Persist the OGE collection URL or request workflow used for access.",
            "Archive any released PDF, spreadsheet, or request response before parsing.",
            "Record filer office, agency, document type, retrieval timestamp, file hash, parser version, and dataset version.",
            "Keep executive branch parser mappings separate from legislative mappings.",
        ],
    },
    {
        "id": "judicial-financial-disclosure",
        "name": "Federal Judicial Financial Disclosure Reports",
        "branch": "Judicial",
        "chamber": None,
        "source_url": "https://www.uscourts.gov/administration-policies/judiciary-financial-disclosure-reports",
        "search_url": "https://pub.jefs.uscourts.gov/",
        "download_url": None,
        "access_mode": "public_portal_acknowledged",
        "public_sample_url": None,
        "ingestion_status": "parser_preview_ready",
        "records_scope": "Financial disclosure reports and periodic transaction reports for federal judges and covered judiciary personnel released through the Administrative Office of the U.S. Courts.",
        "rights_note": (
            "The judicial database requires requester information and acknowledgement of "
            "statutory access and use restrictions. CivicLedger must not automate around "
            "those access requirements."
        ),
        "provenance_requirements": [
            "Persist the judiciary disclosure database URL or request workflow used for access.",
            "Archive released reports before normalized records are created.",
            "Record court, judge type, report type, retrieval timestamp, file hash, parser version, and dataset version.",
            "Keep judicial parser mappings separate from legislative and executive mappings.",
        ],
    },
]


def get_official_sources_response() -> dict:
    return {
        "dataset_version": settings.DATASET_VERSION,
        "methodology_version": settings.METHODOLOGY_VERSION,
        "sources": OFFICIAL_SOURCES,
    }
