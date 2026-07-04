# Data Model

## Existing MVP Tables

- `people`: public officials and service metadata across legislative, executive, and judicial branches.
- `ingestion_runs`: ingestion job metadata, parser version, dataset version, and status.
- `raw_documents`: source-first archival metadata for raw filing documents.
- `filings`: filing metadata, source URL, retrieval timestamp, file hash, retrieval source.
- `trades`: normalized reported transactions.
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

## Near-Term Additions

### people branch fields

The root `people` table now treats `branch` as the primary branch discriminator. `chamber` is nullable and should only be used for legislative records. Executive records should use `office` and `agency`; judicial records should use `court` and, later, judge-type metadata.

### event_people

Links a global event to specific people only when there is an explicit source-backed relevance rule. Until this exists, frontend views should label events as global context, not person-specific context.

### parser_artifacts

Stores row, page, span, parser output, and extraction evidence for each normalized trade.

## Derived Data Rules

- Raw source records should be stored before normalized rows.
- Normalized trades must retain links to source filing and raw document metadata.
- Parser confidence should be exposed as parser confidence, not factual certainty.
- Data-quality scores must remain separate from conduct or ethics judgments.
