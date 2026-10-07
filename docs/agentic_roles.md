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

## Research Director and Public-Records Lead

Focus:

- Set source priorities, coverage claims, acquisition protocols, and research questions.
- Distinguish a complete source search from a complete factual record.
- Require a documented source trail for every consequential statement.

Review questions:

- Does the source actually cover the official, office, filing type, and date range claimed?
- Is an absence explained as a coverage state rather than evidence of no activity?
- Is the original public record available to the reviewer?

## Verification Editor and Fact Checker

Focus:

- Compare extracted fields with the source image or document.
- Resolve amendments, duplicates, identity conflicts, and date ambiguity.
- Enforce independent verification for public narrative claims.

Review questions:

- Which fields were observed directly and which were inferred or normalized?
- Could another reviewer reproduce the decision from the archived evidence?
- Does the public language say only what the evidence establishes?

## Quantitative Methods Reviewer

Focus:

- Sampling design, gold-corpus measurement, error analysis, and benchmark validity.
- Market-window definitions, benchmark selection, missingness, and sensitivity analysis.
- Separation of deterministic software regression tests from empirical accuracy claims.

Review questions:

- Is the evaluation sample representative of source formats and branches?
- Are precision, recall, and uncertainty reported against human labels?
- Could a chart encode magnitude or certainty that the source does not support?

## Investigative and Accountability Editor

Focus:

- Turn correlations into testable reporting leads without turning them into allegations.
- Require source chronology, official involvement evidence, alternative explanations, and right of reply.
- Define the threshold between research preview, reporting lead, and publishable finding.

Review questions:

- Is temporal proximity being mistaken for causation or knowledge?
- Has potentially exculpatory or contradictory evidence been sought?
- Has the affected person or institution been given a fair opportunity to respond?

## Accessibility and Information Design Reviewer

Focus:

- Keyboard, screen-reader, color, contrast, responsive, and reduced-motion behavior.
- Plain-language evidence labels and usable alternatives to dense charts.
- Comparable interpretation across visual, tabular, audio, and transcript formats.

## Security, Privacy, and Release Reliability Lead

Focus:

- Secret handling, least privilege, dependency and workflow safety, immutable evidence, and recovery.
- Daily refresh health, release gates, rollback, and public freshness communication.
- Protection of unpublished research, interview material, contact details, and reviewer identity data.

## Audience, Community, and Multimedia Editor

Focus:

- Translate verified records into accessible articles, podcasts, video, newsletters, and local outreach.
- Preserve citations and uncertainty when material moves between formats.
- Design membership and community participation around correction, verification, and civic value.

## Operating Model

- Assign the roles needed for each substantive change and record the relevant review gates.
- Automation may prepare evidence and candidates; it may not impersonate a human reviewer.
- L3 review and L4 publication decisions require an attributable human decision.
- Security, accessibility, provenance, and legal/ethics review are release functions, not optional polish.
- See `publication_standards.md`, `ai_use_policy.md`, `validation_and_gold_corpus.md`, and `release_gates.md` for the enforceable project rules.
