# Roadmap

## Phase 0 - Stabilize Scaffold

- Align frontend and backend contracts.
- Move app files to the repository root.
- Add project truth docs.
- Add CI for backend syntax and frontend build.
- Verify Docker Compose boots.

## Phase 1 - Provenance-First MVP

- Add ingestion-run and raw-document tables.
- Implement one official-source ingestion path.
- Publish official legislative, executive, and judicial source registry through the API and methodology UI.
- Store raw documents before parsed records.
- Label fixture records across API, UI, and share cards.
- Add source detail views.
- Keep disclosure-completeness scorecards narrow and documented.

## Phase 2 - Timeline and Source UX

- Improve profile timelines.
- Add source filters and provenance completeness filters.
- Add event source detail pages.
- Add methodology links from scorecards and charts.
- Explain lag and color thresholds in neutral language.

## Phase 3 - Share Cards

Release blocker: no public share-card workflow until fixture labeling, source completeness, methodology versioning, dataset versioning, and rendered disclaimers are enforced.

Required before public use:

- Source links in generated output.
- Dataset and methodology version in generated output.
- Generated timestamp in generated output.
- Fixture/demo label when applicable.
- Disclaimer rendered in the artifact, not only returned by API metadata.

## Deferred

- Causal event analysis.
- Asset-level performance claims.
- Top or worst rankings.
- Alerts framed around suspicious timing.
- AI summaries about intent.
- Automated allegation generation.

## Cross-Branch Expansion

- Add executive branch OGE source intake as a separate parser path.
- Add judicial disclosure source intake as a separate parser path.
- Preserve requester/access restrictions from each source before retrieving or exporting records.
- Add branch-aware browse filters once non-legislative records exist.
- Avoid forcing executive agencies or courts into the legislative `chamber` field.

## Release Blockers

- Incomplete provenance display.
- Synthetic data ambiguity.
- Scorecard naming ambiguity.
- Missing share-card disclaimer in rendered artifacts.
- Frontend/API contract drift.
