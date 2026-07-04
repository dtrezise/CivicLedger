# CivicLedger Product Brief

## System Definition

CivicLedger presents publicly available federal financial disclosure records, provenance metadata, reporting-lag calculations, and contextual market or civic-event timelines for officials across the legislative, executive, and judicial branches. It does not determine whether any trade was lawful, ethical, suspicious, informed by nonpublic information, or financially advisable.

## What CivicLedger Is

- A searchable public disclosure ledger.
- A timeline explorer for reported financial activity.
- A source and provenance viewer.
- A disclosure-lag calculator.
- A methodology-transparent share-card generator.
- A data-quality and completeness tool.

## What CivicLedger Is Not

- A corruption detector.
- An ethics adjudicator.
- An insider-trading monitor.
- A legal compliance engine.
- A trading recommender.
- An opposition research tool.
- A real-time market data product.

## Primary User Jobs

- Find a federal public official and inspect available disclosure records.
- View reported trades in chronological context.
- Verify each record against original source metadata.
- Understand reporting lag and data completeness.
- Export or share a record summary with visible methodology and disclaimers.

## MVP Data Boundary

The MVP should use official or clearly labeled fixture data only. Fixture records must remain visibly labeled in API responses, UI views, exports, and share cards. Public presentation must not make fictional seed data look like real official records.

Initial official-source expansion order:

- Legislative: House Clerk and Senate public disclosure systems.
- Executive: Office of Government Ethics public disclosure resources and request workflows.
- Judicial: Administrative Office of the U.S. Courts financial disclosure database and request workflows.

Current first-draft implementation includes fixture officials for all three branches, branch-aware browse filters, source-readiness filters, a manual official-source archive command, preview-only parser adapters, and parser artifact evidence surfaces. These are scaffolding and review tools, not a claim that official executive or judicial records have been fully ingested.

## Language Policy

Preferred terms:

- disclosure
- reported
- filed
- source
- lag
- context
- data quality
- provenance
- completeness

Terms requiring legal or product review:

- suspicious
- improper
- well-timed
- profited from
- caught
- violated
- insider
- corrupt
- conflict score
- ethics score

## Public-Official Fairness Boundary

CivicLedger may show what was reported, when it was filed, how complete the source metadata is, and what other timeline context exists. CivicLedger must not state or imply that a public official acted unlawfully, unethically, profitably, knowingly, or with improper intent.

## Non-Goals

- Causal inference between trades and events.
- Asset-level performance claims without verified price data and methodology.
- Public rankings framed around suspicion or misconduct.
- Automated allegations.
- AI summaries about individual intent.
