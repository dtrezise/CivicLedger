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

## Near-Term Additions

### people branch fields

The root `people` table now treats `branch` as the primary branch discriminator. `chamber` is nullable and should only be used for legislative records. Executive records should use `office` and `agency`; judicial records should use `court` and, later, judge-type metadata.

### congressional service terms

Congressional records use `bioguide_id` as the canonical legislative person key. The durable service grain is one person in one Congress/chamber/state/district combination. Public Pages data mirrors these fields into `public_official_roles.source_metadata` so the static explorer can filter by chamber, Congress, party, state, and district without requiring the FastAPI backend.

### event_people

Links a global event to specific people only when there is an explicit source-backed relevance rule. Until this exists, frontend views should label events as global context, not person-specific context.

### parser artifact coordinates

Promoted from near-term plan into the MVP schema. Next additions should include richer coordinates for PDFs and table cells once source-specific parsers move beyond preview mode.

## Derived Data Rules

- Raw source records should be stored before normalized rows.
- Normalized trades must retain links to source filing and raw document metadata.
- Parser confidence should be exposed as parser confidence, not factual certainty.
- Parser previews must be promoted only after explicit human review.
- Data-quality scores must remain separate from conduct or ethics judgments.
