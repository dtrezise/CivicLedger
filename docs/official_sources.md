# Official Source Intake

## Purpose

CivicLedger must move from fixture data to official-source records without weakening provenance, neutrality, or use restrictions. This document defines the first legislative, executive, and judicial official targets and the intake rules for the MVP.

## Initial Source Registry

### House Financial Disclosure Reports

- Source home: https://disclosures-clerk.house.gov/FinancialDisclosure
- Search entry point: https://disclosures-clerk.house.gov/FinancialDisclosure/ViewSearch
- Current status: official yearly index integrated; position-aware PTR parser previews integrated; image-only filings remain OCR/review queued.
- Scope: member, staff, and candidate financial disclosure reports published through the Office of the Clerk.

The House disclosure search page includes statutory restrictions on use of financial disclosure information and notes that certain personally identifiable information has been redacted. CivicLedger must surface or preserve that notice before records from this source are exported, shared, or used outside development.

### Senate Public Financial Disclosure Database

- Source home: https://www.disclosure.senate.gov/
- Search entry point: https://efdsearch.senate.gov/
- Initial status: planned
- Scope: Senate public financial disclosures and periodic transaction reports.

The Senate public disclosure page points users to the Senate Public Financial Disclosure Database and describes STOCK Act reporting for covered Senators and senior staff. Chamber-specific field mapping must be verified separately from House parsing.

### OGE Officials' Individual Disclosures

- Source home: https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm=
- Search/request entry point: https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm=
- Current status: presidential source index and 11 official documents integrated; 365 Trump transaction previews integrated; cabinet/senior-official backfill remains pending.
- Scope: executive branch public financial disclosure documents, including OGE Form 278e annual reports and OGE Form 278-T periodic transaction reports where available.

OGE displays statutory restrictions on obtaining or using public financial disclosure reports, including restrictions on unlawful, commercial, credit-rating, and solicitation uses. CivicLedger must preserve these restrictions in ingestion logs, exports, and share-card workflows.

### Federal Judicial Financial Disclosure Reports

- Source home: https://www.uscourts.gov/administration-policies/judiciary-financial-disclosure-reports
- Search/request entry point: https://pub.jefs.uscourts.gov/
- Current status: source registry, parser adapter, review workflow, and 850 dated judicial roles integrated; bulk report acquisition remains requester-governed and is not automated around JEFS acknowledgement controls.
- Scope: financial disclosure reports and periodic transaction reports for federal judges and covered judiciary personnel released through the Administrative Office of the U.S. Courts.

The judiciary database provides public access to downloadable reports but requires requester registration and acknowledgement of statutory access/use restrictions. CivicLedger must not automate around those access requirements.

### Federal Civic Events

- Congress.gov laws: official enacted-law records for the 111th-119th Congresses.
- Federal Register: official executive-order records from January 20, 2009 onward.
- Supreme Court: official slip-opinion tables from October Term 2017 onward.
- FRED: macro observations and release context from 2009 onward.

The event collector currently contains 2,822 raw public laws, 926 raw executive orders, and 579 structured Supreme Court opinions. A disclosed topic taxonomy selects records for possible market context. Pre-2017 Supreme Court bound-volume backfill remains explicit in coverage metadata. Event selection is not evidence that an event relates to a trade.

## Intake Rules

- Respect official terms, notices, robots controls, and rate limits.
- Prefer documented downloads, released documents, or manually supplied official document URLs before any broad crawling.
- Treat request/registration workflows as human-governed source access, not as scraping targets.
- Create an `ingestion_runs` record before retrieving documents.
- Store raw documents or raw index payloads before normalized filings or trades are created.
- Hash every retrieved artifact.
- Preserve source URL, retrieval timestamp, retrieval source, content type, parser version, dataset version, and provenance completeness.
- Keep fixture/demo records labeled until an official-source ingestion run completes and normalized records are traceable to archived raw documents.
- Do not generate causation, intent, ethics, legality, or investment conclusions from ingested data.

## First Implementation Slice

Implemented:

1. `python -m app.intake` archives a local artifact against a source ID and official source URL.
2. Intake creates `ingestion_runs` and `raw_documents` before parser preview output.
3. Parser adapters exist behind explicit source IDs: `house-financial-disclosure`, `senate-public-financial-disclosure`, `oge-individual-disclosures`, and `judicial-financial-disclosure`.
4. Parser output extracts common transaction fields into preview output and stores evidence in `parser_artifacts`.
5. `/meta/source-completeness` reports missing raw-document, filing, and completed-ingestion capabilities by source.
6. `python -m app.download_source` downloads a specific public official-source document URL or configured public sample, then archives it through the same provenance path.
7. `/review` exposes preview promotion, while `/evidence`, `/quality`, and `/admin/runs` expose evidence search, duplicate checks, and source-run history.
8. Parser previews include field-level confidence and branch-specific scorecards use branch-specific lag thresholds.

Example:

```bash
cd backend
python -m app.intake \
  --source-id judicial-financial-disclosure \
  --source-url "https://pub.jefs.uscourts.gov/" \
  --file /path/to/released-report.pdf \
  --access-acknowledged
```

Promotion requires explicit review:

```bash
python -m app.promote \
  --artifact-id <preview-artifact-id> \
  --reviewer "Reviewer Name" \
  --person-name "Judge Example" \
  --branch Judicial \
  --office "Circuit Judge" \
  --court "U.S. Court of Appeals"
```

Parser regression fixtures live under `backend/tests/fixtures/parsers/`.

Verified sample ingestion:

```bash
./scripts/run_sample_ingestion.sh
```

The current sample uses an official OGE public PDF URL. It is a smoke path for downloader, archiver, parser-preview, and provenance persistence; it is not a production ingestion policy.
