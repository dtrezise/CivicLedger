# CivicLedger Data Model

The PostgreSQL schema separates source evidence, canonical entities, disclosed transactions, and analytical relationships. A normalized row must remain traceable to a source document, and a candidate relationship must never be mistaken for a finding of misconduct.

## Model Boundaries

| Boundary | Authoritative tables | Purpose |
| --- | --- | --- |
| Public officials | `people`, `public_official_roles`, `congressional_service_terms`, `service_periods` | Identity and dated federal service |
| Source provenance | `ingestion_runs`, `raw_documents`, `parser_artifacts` | Acquisition, file identity, parser evidence, and review inputs |
| Disclosures | `filings`, `trades` | Filing-level metadata and normalized reported transactions |
| Canonical entities | `organizations`, `issuers`, `organization_aliases`, `organization_identifiers` | Stable organization identity and issuer-specific attributes |
| Entity history | `organization_relationships`, `sectors`, `organization_sectors`, `assets`, `ticker_histories` | Dated ownership, classification, and security identifiers |
| Events and institutions | `events`, `event_sources`, `event_source_snapshots`, `jurisdictions`, `institutions`, `event_institution_links` | Context events, immutable evidence captures, and institutional responsibility |
| Analysis and review | `event_relationships`, `trade_event_candidates`, `relationship_reviews`, `data_quality_issues` | Explainable candidates, reviewer history, and quality exceptions |

## Canonical Organizations

`organizations` is the canonical identity grain for companies, funds, government bodies, nonprofits, partnerships, trusts, and other organizations. Every row has a stable, unique `canonical_key`; names are labels and must not be used as identifiers. `normalized_name` supports candidate matching but is deliberately not unique because unrelated organizations can share a name.

`issuers` remains the securities-issuer profile used by existing asset code. Migration `0005_entity_history_model` creates one organization for every existing issuer, backfills `issuers.organization_id`, and then enforces a required one-to-one relationship. Existing `canonical_name`, `cik`, and `lei` columns remain on `issuers` as compatibility fields. New integrations should resolve the organization first and treat `organization_identifiers` as the canonical identifier registry.

### Names and identifiers

- `organization_aliases` records alternate, former, trade, and disclosure names. `normalized_alias` is the lookup form; the original `alias` remains the display and evidence value.
- `organization_identifiers` stores globally scoped `(scheme, value)` pairs such as CIK and LEI. Identifier validity can be dated and supported by a source snapshot.
- Alias matching proposes an organization candidate. It does not establish identity without source evidence or review.
- `source_snapshot_id` is nullable so legacy and manually curated records can be migrated incrementally. Source-backed ingestion should populate it whenever a capture exists.

### Parent history

`organization_relationships` is directed from `parent_organization_id` to `child_organization_id`. The row records relationship type, directness, optional ownership percentage, and a half-open-style business interval represented by inclusive `valid_from` and `valid_to` dates. Self-links, inverted date ranges, and ownership outside 0–100 are rejected.

The same parent and child can have multiple historical relationships, but the combination of parent, child, relationship type, and start date is unique with PostgreSQL `NULLS NOT DISTINCT`. Unknown start dates therefore cannot create duplicate undated relationships.

## Sector History

`sectors` supports multiple named taxonomies such as GICS, NAICS, or a CivicLedger-specific taxonomy. `(taxonomy, code)` is canonical, and `parent_sector_id` supports hierarchical categories.

`organization_sectors` dates an organization’s assignment to a sector and records confidence and evidence. An organization may have several concurrent secondary sectors, but a partial unique index permits only one current primary sector. Historical primary assignments remain available after `valid_to` is set.

Sector classification is descriptive context. It is not evidence that an event affected every organization in the sector.

## Assets and Ticker History

`assets` identifies the disclosed security or other asset. It links to the compatibility issuer profile where known. `ticker_histories` records symbols separately because symbols, exchanges, and primary listings change over time.

Each ticker-history row includes:

- `asset_id` and canonical `organization_id`;
- symbol, exchange, optional ISO 10383 MIC, and currency;
- inclusive validity dates;
- primary-listing status;
- an optional immutable source snapshot.

The database prevents duplicate history rows when dates or MIC values are null and permits only one current primary ticker per asset. A ticker must be resolved as of the transaction date; the present-day symbol is not automatically valid for a historical trade.

## Disclosure Metadata

### Filings

`filings` now distinguishes the local UUID from the source identity:

- `source_system` and `source_filing_id` identify a report in House, Senate, OGE, or another source system.
- `reporting_period_start` and `reporting_period_end` preserve the period covered by annual, termination, and periodic reports.
- `received_date`, `certified_date`, `filed_date`, and `retrieved_at` remain separate dates with separate meanings.
- `amendment_number` and `amends_filing_id` model amendment chains without overwriting the earlier filing.
- `filing_status`, `review_status`, `is_late`, and `late_days` preserve workflow and timeliness metadata.
- `source_metadata` retains source-specific fields that have not earned canonical columns.

The source identity is unique when a source filing ID is available. Reporting periods cannot run backward, amendment numbers and late-day counts cannot be negative, and a filing cannot amend itself.

### Trades

`trades` retains the disclosure’s value range rather than presenting a midpoint as an exact amount. It additionally records:

- `source_transaction_id`, unique within a filing when present;
- disclosed owner (`self`, `spouse`, `dependent_child`, `joint`, `trust`, `other`, or `unknown`);
- source-reported asset type and description;
- source page and row coordinates;
- the reported capital-gains-over-$200 flag;
- review status and source-specific metadata.

Page and row coordinates are one-based. Parser confidence and asset-match confidence describe extraction and resolution quality, not factual certainty or intent.

## Immutable Event Sources

`event_sources` describes a source citation attached to an event: URL, source type, title, publisher, and source publication time. `event_source_snapshots` records individual retrievals with the retrieval time, content hash, hash algorithm, media type, HTTP status, final URL, storage location, length, and response metadata.

Snapshots are append-only:

1. `(event_source_id, hash_algorithm, content_hash)` identifies captured content.
2. SQLAlchemy rejects ORM update and delete operations.
3. PostgreSQL trigger `trg_event_source_snapshots_immutable` rejects direct updates and deletes.
4. A changed page must produce a new snapshot row; it must never mutate an earlier capture.

The snapshot stores identity and retrieval metadata. Large response bodies belong in immutable object storage referenced by `storage_uri`.

## Institutions and Jurisdictions

`jurisdictions` is a hierarchy of federal, state, territorial, circuit, district, subject-matter, and other jurisdictions. Identity is `(jurisdiction_type, country_code, code)` rather than display name.

`institutions` specializes a canonical organization as an agency, committee, subcommittee, court, office, legislature, or other public institution. It can record branch, chamber, parent institution, active dates, source-specific external ID, and jurisdiction.

`event_institution_links` connects an event to an institution with a typed relationship. Court and administrative proceedings can retain `docket_number` and `proceeding_id`; the link may also specify the applicable jurisdiction and immutable evidence snapshot. This models institutional involvement, not the personal involvement of every official serving in that institution.

Examples:

- an agency `issued` a rule;
- a committee `reported` a bill;
- a court `decided` a docketed case;
- an office `signed` an executive order.

## Event and Review Semantics

`events` preserves event date plus announcement, publication, and effective dates. `event_relationships` stores source-backed links to people, assets, or named organizations. `trade_event_candidates` stores versioned analytical candidates based on explicit reasons such as entity overlap, institutional involvement, market movement, and temporal proximity.

Date proximity alone is contextual. It does not establish knowledge, causation, benefit, or wrongdoing. Reviewer decisions are append-only in `relationship_reviews`; narrowing or rejecting a candidate does not delete the original calculation.

Neutral market-reaction context is stored outside the relational review state as
a compact manifest plus symbol-year partitions. Each partition records its byte
length, SHA-256, symbol, year, and reaction count. Loading fails closed on hash,
identity, or count mismatch. These descriptive windows remain unsigned with
respect to BUY or SELL and are not promotion evidence by themselves.

## Temporal Conventions

- Dates are inclusive unless a source defines a more precise interval.
- A null `valid_from` means the start is unknown, not that the relationship began at organization creation.
- A null `valid_to` means no end is known; for partial indexes it represents the current row.
- Historical resolution uses the event or transaction date and must not silently substitute current ownership, sector, institution, or ticker data.
- Corrections add a superseding or amended row where history matters. Source snapshots are never corrected in place.

## Ingestion Order

1. Record the ingestion run and raw document.
2. Create or reuse the event source and append its immutable snapshot.
3. Resolve canonical organizations, identifiers, and aliases.
4. Resolve issuer profiles, assets, and date-appropriate ticker rows.
5. Create the filing and parser artifacts.
6. Create candidate trades with page/row provenance.
7. Link events to institutions and jurisdictions from source evidence.
8. Generate versioned trade-event candidates.
9. Promote records only through the review workflow.

## Migration Compatibility

Migration `0005_entity_history_model` is additive after `0004_release_relationship_model`. Existing issuer rows are backfilled before the required organization foreign key is enforced. New disclosure columns have conservative defaults or are nullable, so current parser and promotion constructors remain valid. The downgrade removes the new entity/history layer and metadata columns but intentionally cannot preserve data written only to those structures.
