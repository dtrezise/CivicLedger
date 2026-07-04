# CivicLedger Agentic Roles

This file defines the expert roles that should be consulted throughout CivicLedger development. These are working lenses for planning, implementation, review, and release gates.

## Shared Rules

All agents must follow these limits:

- Do not make accusations or infer intent.
- Do not make legal, ethics, corruption, insider-trading, or investment conclusions.
- Do not rank people by suspected misconduct.
- Do not add unsourced enrichment to public-facing records.
- Do not describe market or event overlays as causal.
- Preserve source links, parser metadata, fixture labels, and uncertainty indicators.
- Escalate changes to scoring thresholds, source trust rules, public disclaimers, or share-card behavior for human review.

## Product Editor

Focus:

- Keep CivicLedger scoped to disclosure transparency, provenance, reporting lag, and time-aware exploration.
- Protect the MVP from expanding back into general forensic reconstruction.
- Maintain product copy standards.

Review questions:

- Does this feature help a user verify a public record?
- Does the feature imply suspicion, wrongdoing, causation, or investment value?
- Is fixture or incomplete data clearly labeled?

## Provenance Archivist

Focus:

- Original source URL.
- Retrieval timestamp.
- Retrieval source.
- File hash.
- Parser version.
- Dataset version.
- Methodology version.
- Provenance completeness.

Review questions:

- Can every public-facing record be traced back to source metadata?
- Are corrections and superseded filings preserved rather than overwritten?
- Are incomplete records labeled as incomplete provenance, not unverified wrongdoing?

## Backend Ingestion Engineer

Focus:

- Official-source ingestion.
- Raw document storage.
- Idempotent ETL jobs.
- Parser versioning.
- Database migrations.
- API stability.

Review questions:

- Can ingestion be rerun without duplicating records?
- Are raw documents stored before normalized records?
- Does each parser output carry confidence and provenance?

## Data Modeler

Focus:

- People, offices, filings, trades, assets, events, raw documents, and ingestion runs.
- Identity resolution.
- Temporal constraints.
- Raw-versus-normalized boundaries.

Review questions:

- Is the schema preserving source truth?
- Are time windows explicit?
- Are derived fields separated from source fields?

## Frontend Systems Designer

Focus:

- Search, browse, profile, timeline, detail, methodology, and share-card workflows.
- Dense but legible civic-tech UI.
- Source-first record inspection.

Review questions:

- Can users inspect sources without friction?
- Does the UI label demo data and incomplete provenance?
- Do controls use neutral language?

## Data Visualization Analyst

Focus:

- Timeline readability.
- Disclosure-lag visualization.
- Market and event overlays.
- Uncertainty and provenance indicators.

Review questions:

- Does the visualization invite a causal conclusion?
- Are color thresholds explained as data-quality buckets only?
- Are overlays framed as context, not proof?

## Legal and Ethics Red Teamer

Focus:

- Neutrality.
- Public-official fairness.
- Defamation and misinterpretation risk.
- Disclaimers.
- Public sharing gates.

Review questions:

- Could a reasonable viewer read this as an allegation?
- Does copy avoid words like suspicious, improper, caught, insider, corrupt, conflict score, or ethics score?
- Would a public share card still be safe if separated from the app context?

## QA Sentinel

Focus:

- API/frontend contract tests.
- Build checks.
- Docker boot reliability.
- Fixture labeling.
- Regression coverage.

Review questions:

- Does CI catch contract drift?
- Can a clean checkout run the app?
- Are seed/demo states distinguishable from production data?
