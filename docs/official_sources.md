# Official Source Intake

## Purpose

CivicLedger must move from fixture data to official-source records without weakening provenance, neutrality, or use restrictions. This document defines the first official targets and the intake rules for the MVP.

## Initial Source Registry

### House Financial Disclosure Reports

- Source home: https://disclosures-clerk.house.gov/FinancialDisclosure
- Search entry point: https://disclosures-clerk.house.gov/FinancialDisclosure/ViewSearch
- Initial status: planned
- Scope: member, staff, and candidate financial disclosure reports published through the Office of the Clerk.

The House disclosure search page includes statutory restrictions on use of financial disclosure information and notes that certain personally identifiable information has been redacted. CivicLedger must surface or preserve that notice before records from this source are exported, shared, or used outside development.

### Senate Public Financial Disclosure Database

- Source home: https://www.disclosure.senate.gov/
- Search entry point: https://efdsearch.senate.gov/
- Initial status: planned
- Scope: Senate public financial disclosures and periodic transaction reports.

The Senate public disclosure page points users to the Senate Public Financial Disclosure Database and describes STOCK Act reporting for covered Senators and senior staff. Chamber-specific field mapping must be verified separately from House parsing.

## Intake Rules

- Respect official terms, notices, robots controls, and rate limits.
- Prefer documented downloads or manually supplied official document URLs before any broad crawling.
- Create an `ingestion_runs` record before retrieving documents.
- Store raw documents or raw index payloads before normalized filings or trades are created.
- Hash every retrieved artifact.
- Preserve source URL, retrieval timestamp, retrieval source, content type, parser version, dataset version, and provenance completeness.
- Keep fixture/demo records labeled until an official-source ingestion run completes and normalized records are traceable to archived raw documents.
- Do not generate causation, intent, ethics, legality, or investment conclusions from ingested data.

## First Implementation Slice

1. Add a manual official-source intake command that accepts a House or Senate source URL and archives the raw artifact.
2. Persist `raw_documents` before creating any parsed filing or trade records.
3. Add parser adapters behind explicit source IDs: `house-financial-disclosure` and `senate-public-financial-disclosure`.
4. Run parser output in preview mode before promoting records into public-facing tables.
5. Expose ingestion status in `/meta/status` once a non-fixture run completes.
