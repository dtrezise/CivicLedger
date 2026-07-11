# Data Model

## Existing MVP Tables

- `people`: public officials and service metadata across legislative, executive, and judicial branches.
- `public_official_roles`: source-backed role records across presidential terms and federal branches.
- `congressional_service_terms`: Bioguide-keyed congressional service terms by Congress number.
- `ingestion_runs`: ingestion job metadata, parser version, dataset version, and status.
- `raw_documents`: source-first archival metadata for raw filing documents.
- `filings`: filing metadata, source URL, retrieval timestamp, file hash, retrieval source.
- `trades`: normalized reported transactions.
- `parser_artifacts`: parser evidence, preview output, row/page references, and confidence metadata.
- `events`: contextual civic or market events.
- `event_sources`: source links for events.
- `market_series`: benchmark time series.
- `sharecards`: generated share-card metadata.

## Provenance Tables

### ingestion_runs

Tracks each ingestion job:

- `id`
- `source_name`
- `source_url`
- `started_at`
- `completed_at`
- `status`
- `dataset_version`
- `parser_version`
- `notes`

### raw_documents

Stores source-first archival metadata:

- `id`
- `ingestion_run_id`
- `source_url`
- `retrieved_at`
- `retrieval_source`
- `content_type`
- `file_hash`
- `storage_uri`
- `rights_status`
- `parser_version`
- `provenance_complete`
- `source_metadata`

### parser_artifacts

Stores parser evidence without promoting unreviewed data into public-facing tables:

- `id`
- `source_id`
- `raw_document_id`
- `filing_id`
- `trade_id`
- `artifact_type`
- `page_number`
- `row_number`
- `text_span`
- `parser_output`
- `confidence`

## Release Relationship Model

Migration `0004_release_relationship_model` adds the release-grade temporal and relationship layer:

- `service_periods`: explicit dated service segments, including nonconsecutive terms.
- `issuers`: canonical organizations behind disclosed assets.
- `assets`: normalized assets with raw labels, class, symbol, and mapping confidence.
- `event_relationships`: typed event links with evidence reasons and methodology versions.
- `trade_event_candidates`: explainable temporal/entity/jurisdiction candidate evidence.
- `relationship_reviews`: accept, narrow, reject, and supersede decisions.
- `data_quality_issues`: identity, parser, duplicate, page, and asset-mapping issues.

Trades retain disclosed minimum and maximum values; no midpoint is presented as an exact amount. Events can preserve announcement, effective, publication, and retrieval dates separately.

## Role Fields

### people branch fields

The root `people` table now treats `branch` as the primary branch discriminator. `chamber` is nullable and should only be used for legislative records. Executive records should use `office` and `agency`; judicial records should use `court` and, later, judge-type metadata.

### congressional service terms

Congressional records use `bioguide_id` as the canonical legislative person key. The durable service grain is one person in one Congress/chamber/state/district combination. Public Pages data mirrors these fields into `public_official_roles.source_metadata` so the static explorer can filter by chamber, Congress, party, state, and district without requiring the FastAPI backend.

### Event-to-official boundary

An event links to a person only for source-backed participation or institutional responsibility. Date proximity alone is labeled as a transaction within a selected window. Asset, jurisdiction, institutional, sector, macro, and general context remain distinct relationship tiers.

### Parser artifact coordinates

Parser artifacts preserve page and row references. The House electronic-PTR adapter additionally uses PDF table coordinates to keep owner, asset, action, dates, and amount columns aligned. Image-only reports remain `ocr_required` instead of being treated as no-activity filings.

## Derived Data Rules

- Raw source records should be stored before normalized rows.
- Normalized trades must retain links to source filing and raw document metadata.
- Parser confidence should be exposed as parser confidence, not factual certainty.
- Parser previews must be promoted only after explicit human review.
- Data-quality scores must remain separate from conduct or ethics judgments.
