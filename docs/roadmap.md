# Roadmap

## Phase 0 - Stabilize Scaffold

- Align frontend and backend contracts.
- Move app files to the repository root.
- Add project truth docs.
- Add CI for backend syntax and frontend build.
- Verify Docker Compose boots.

## Phase 1 - Provenance-First MVP

- Add ingestion-run and raw-document tables.
- Implement manual official-source intake with preview-only parser adapters.
- Publish official legislative, executive, and judicial source registry through the API and methodology UI.
- Store raw documents before parsed records.
- Label fixture records across API, UI, and share cards.
- Add source detail views.
- Keep disclosure-completeness scorecards narrow and documented.
- Add branch-aware demo fixtures for legislative, executive, and judicial officials.
- Add parser artifact/evidence table and trade evidence display.

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
- Add source completeness filters to the methodology/source intake UI.
- Avoid forcing executive agencies or courts into the legislative `chamber` field.

## Parser and Promotion Workflow

- Source-specific parsers extract common transaction fields from CSV-like text, line-based text, and PDFs with extractable text.
- Parser output stays in preview/evidence state until `python -m app.promote` is run with reviewer context.
- Regression fixtures cover House, Senate, OGE, and judicial parser lanes.
- Raw-document and filing-evidence pages expose the provenance chain for review.
- Source-client download paths support specific public document URLs and configured public samples while preserving access acknowledgements.
- Reviewer/admin screens cover parser preview promotion, evidence search, duplicate detection, and source-run history.
- Promotion rollback and filing supersession are available through review API endpoints.
- CI now covers backend tests, frontend build, Alembic migration, and Docker smoke.

## Public Pages Edition

- GitHub Pages publishes a static, public-facing demo at the repository Pages URL.
- `scripts/build_pages_dataset.py` generates the fixture-data JSON snapshot used by `pages-site/`.
- The Pages UI presents search, branch and asset filtering, profile detail panels, transaction timelines, market context, source readiness, events, and methodology without requiring the FastAPI backend.
- The Pages edition remains clearly labeled as fixture/demo data until reviewed production records exist.

## Release Blockers

- Incomplete provenance display.
- Synthetic data ambiguity.
- Scorecard naming ambiguity.
- Missing share-card disclaimer in rendered artifacts.
- Frontend/API contract drift.
