# CivicLedger Release Readiness Program

This is the execution backlog for moving CivicLedger from a provenance-first
prototype to a useful, evidence-backed public research product. The target
historical window begins on January 20, 2009 and continues through the current
administration. Work must preserve source restrictions, immutable provenance,
neutral language, and explicit review states.

## Release Outcomes

- The public homepage opens directly into a useful trade comparison workbench.
- Career, calendar, and event-window comparisons have correct time semantics.
- Every public trade is traceable to an official filing and archived source.
- Legislative, executive, and judicial coverage is measurable from 2009 onward.
- Events are linked through explainable evidence tiers rather than causal claims.
- The public dataset can grow without shipping one monolithic browser payload.
- Desktop, tablet, and mobile interactions pass automated release gates.

## 120 Autonomous Steps

### Product Truth And Release Governance

1. [x] Fast-forward the canonical local checkout and reconcile the documented historical scope with the generated dataset.
2. [x] Make the trade comparison workbench the first public screen and move operational completeness reporting to a secondary Data Status view.
3. [x] Unify official search, selected officials, chart state, transaction rows, and profile details in one URL-addressable workspace.
4. [x] Replace the fixed hand-authored timeline SVG with a proven interactive chart engine that supports dense data, zoom, and responsive rendering.
5. [x] Correct career-time, calendar-time, and event-window semantics using explicit service-period segments.
6. [x] Add real trade-activity, disclosed-value-range, asset-price, and benchmark layers with honest units and labels.
7. [x] Add normalized asset, issuer, event-relationship, relevance-candidate, and review-decision data models through migrations.
8. [x] Build source-backed event pipelines for legislation, executive actions, court decisions, funding, and macro releases.
9. [x] Replace the monolithic public JSON payload with a manifest and independently loadable data partitions.
10. [x] Define measurable alpha, beta, release-candidate, and public-release gates.
11. [x] Publish a machine-readable coverage manifest by branch, source, year, and record state.
12. [x] Standardize record states for fixture, source status, parser preview, reviewed, production, superseded, and withdrawn data.
13. [x] Version the event-relevance methodology independently from parser and dataset versions.
14. [x] Convert agentic roles into required review checklists for data, visualization, legal language, accessibility, and release operations.
15. [x] Record an architecture decision naming one public frontend and one shared data-access contract as the long-term source of truth.

### Temporal And Entity Data Model

16. [x] Add canonical service-period records that preserve nonconsecutive terms and overlapping roles.
17. [x] Add cumulative active-service-day coordinates derived from service periods rather than minimum and maximum dates.
18. [x] Add canonical assets with stable identifiers, asset class, raw labels, and mapping confidence.
19. [ ] Add issuers and organizations with official identifiers, aliases, parent relationships, and sectors.
20. [ ] Add ticker-history records so symbol changes and date-bounded mappings remain reproducible.
21. [ ] Preserve ownership type, filer role, transaction code, notification date, filing date, and amendment state where sources provide them.
22. [x] Store disclosed minimum and maximum values as first-class fields and avoid treating midpoint estimates as exact amounts.
23. [x] Expand events to carry announcement, action, effective, publication, and source-retrieval dates where applicable.
24. [ ] Add immutable event-source snapshots with hashes and source-tier metadata.
25. [x] Add event-to-issuer and event-to-asset links with explicit relationship types.
26. [ ] Add event-to-agency, committee, court, and jurisdiction links.
27. [x] Add event-to-official links only for source-backed participation or institutional responsibility.
28. [x] Add trade-event candidate rows containing time distance, entity overlap, jurisdiction overlap, and methodology version.
29. [x] Add reviewer decisions that accept, narrow, reject, or supersede relationship candidates.
30. [x] Add data-quality issue records for identity ambiguity, parser ambiguity, duplicate filings, missing pages, and unmatched assets.

### Official Roster And Disclosure Acquisition

31. [x] Rebuild congressional service coverage for the 111th through 119th Congresses using Bioguide identifiers.
32. [x] Validate House and Senate roster boundaries against official chamber sources.
33. [x] Preserve party, state, district, chamber, Congress, and service-date changes as dated role records.
34. [x] Build an official House disclosure index collector for publicly downloadable filing indexes.
35. [ ] Build an idempotent House raw-document downloader with hashing, retry, and source-restriction metadata.
36. [ ] Expand the House parser for periodic transaction reports, amendments, and annual reports.
37. [ ] Add House parser fixtures for representative layouts from every covered year.
38. [ ] Build House filing and transaction deduplication across amendments and repeated index entries.
39. [ ] Build a Senate disclosure acquisition adapter that supports official released documents and acknowledged manual archives without bypassing access controls.
40. [ ] Expand the Senate parser for periodic transaction, annual, amendment, and termination report layouts.
41. [ ] Add Senate parser fixtures spanning legacy text, HTML, and PDF-derived records.
42. [ ] Resolve Senate filers to Bioguide records with explicit ambiguous-match queues.
43. [ ] Expand the OGE collection index to cover presidents, cabinet members, cabinet-level officials, and senior executive officials from 2009 onward.
44. [ ] Store every retrievable OGE document in a content-addressed archive before exposing parser output.
45. [ ] Expand OGE 278-T parsing across all observed table layouts and continuation pages.
46. [ ] Add OGE 278e asset, transaction, income, and position extraction while keeping sections semantically separate.
47. [ ] Build OGE amendment and supersession handling so corrected reports do not silently overwrite prior versions.
48. [ ] Resolve executive filers to dated offices and agencies across administration transitions.
49. [ ] Build a judiciary disclosure manifest from publicly released or supplied official report metadata.
50. [ ] Expand AO-10 and judiciary periodic-transaction parsing across supported document generations.
51. [ ] Resolve judges to court, appointment, elevation, senior-status, and termination periods.
52. [ ] Add judiciary report-year, requester-access, redaction, and rights metadata to provenance records.
53. [x] Build source-specific completeness metrics using expected filing types and covered service periods.
54. [x] Add resumable acquisition checkpoints so historical backfills can continue without reprocessing completed artifacts.
55. [x] Produce branch-by-year ingestion batches ordered by current officials, recent history, and then older history.

### Event And Relationship Coverage

56. [ ] Ingest enacted legislation and major bill actions from Congress.gov beginning with the 111th Congress.
57. [ ] Ingest sponsors, cosponsors, committees, recorded votes, and action dates needed for institutional relationships.
58. [ ] Normalize bill subjects and policy areas into versioned jurisdiction tags.
59. [x] Ingest executive orders and presidential documents from the Federal Register beginning in 2009.
60. [ ] Ingest significant agency rules and notices only when an issuer, asset, or jurisdiction mapping is supportable.
61. [x] Ingest Supreme Court opinions with decision dates, docket identifiers, source links, and subject tags.
62. [ ] Add an extensible federal-court decision adapter for source-backed appellate and district decisions.
63. [x] Add appropriations and major federal-funding events from official legislation and agency sources.
64. [ ] Add USAspending award context only after award recipients resolve reliably to canonical issuers or subsidiaries.
65. [ ] Expand macro events beyond CPI to FOMC decisions, employment releases, GDP releases, and recession indicators.
66. [ ] Deduplicate events that appear in multiple official feeds while preserving every source.
67. [x] Distinguish announcement, passage, signature, decision, publication, and effective-date event markers.
68. [x] Define direct, institutional, jurisdictional, asset-specific, sector, and general-macro relationship tiers.
69. [x] Remove the public opaque 0-to-100 relevance score and expose evidence reasons instead.
70. [x] Default the chart to direct, institutional, jurisdictional, and asset-specific events with macro context opt-in.
71. [x] Rename date-only matches as transactions within the selected window rather than related trades.
72. [x] Add event-editor status, source count, relationship status, and methodology version to every displayed event.
73. [x] Add automated checks preventing events from appearing inside inactive service gaps unless the view is explicitly global.
74. [ ] Add relationship-review queues sorted by evidence strength and public impact.
75. [x] Publish event coverage and unresolved relationship counts in the Data Status view.

### Market And Asset Context

76. [ ] Backfill equity, ETF, and benchmark market data to January 2009 for every mapped disclosed symbol supported by the provider.
77. [x] Backfill crypto market data to each asset's earliest reliable provider date.
78. [x] Normalize price series for comparison views without presenting them as portfolio performance.
79. [ ] Add trade-date, report-date, 7-day, 30-day, and 90-day context windows with provider provenance.
80. [x] Handle weekends, holidays, missing bars, and nearest-market-date selection deterministically.
81. [ ] Track splits, symbol changes, mergers, delistings, and stale mappings as explicit corporate-action context.
82. [x] Select sector and broad-market benchmarks through documented asset-reference rules.
83. [x] Display market-data coverage separately from disclosure-data completeness.
84. [ ] Cache and partition price series by symbol and year for efficient public loading.
85. [x] Add anomaly detection for discontinuities, duplicate bars, impossible values, and provider fallbacks.

### Public Comparison Workbench

86. [x] Put official selection and the comparison chart in the first viewport on desktop and mobile.
87. [ ] Add a searchable multi-select supporting branch, chamber, state, district, party, agency, court, office, and service-period filters.
88. [ ] Preserve selected officials, mode, date range, assets, event filters, and zoom state in the URL.
89. [ ] Limit default comparison density to four officials on desktop and two on mobile while allowing deliberate expansion.
90. [x] Keep the requested presidential baseline while clearly distinguishing no-data, preview, reviewed, and production lanes.
91. [x] Render career mode using cumulative active-service time and visible term-break markers.
92. [x] Render calendar mode using real dates and visible inactive periods.
93. [x] Render event mode only after event selection and center it on a configurable before-and-after window.
94. [x] Aggregate trade count and disclosed minimum-to-maximum value ranges when zoomed out.
95. [x] Reveal individual trade markers, filing lag, asset, action, range, and provenance when zoomed in.
96. [x] Add an event rail that clusters dense markers and communicates relationship tier through shape and label, not accusation-oriented color.
97. [x] Add normalized asset and benchmark price lines only for explicitly selected assets.
98. [ ] Synchronize chart selections with a virtualized transaction table below the visualization.
99. [x] Open an evidence drawer for selected trades and events without navigating away from the comparison state.
100. [ ] Link every production transaction to filing, raw document, source page or row, parser version, and review status.
101. [x] Add clear empty, loading, partial-coverage, source-restricted, and error states.
102. [x] Add a compact legend that explains trade actions, record states, relationship tiers, and market layers.
103. [x] Ensure all controls are keyboard operable and every visual mark has an accessible textual equivalent.
104. [ ] Eliminate page-level horizontal overflow and verify touch targets at common mobile widths.
105. [x] Add shareable comparison links and evidence-aware static summaries without making causal or performance claims.

### Scale, Quality, And Release Operations

106. [x] Introduce a small public manifest containing dataset versions, partition URLs, counts, hashes, and coverage metadata.
107. [x] Partition officials, roles, trades, events, relationships, and market data by stable query boundaries.
108. [x] Add schema validation for every generated artifact before commit or deployment.
109. [x] Add deterministic build checks so unchanged source data produces unchanged artifacts apart from explicit generation metadata.
110. [x] Add fixture, preview, reviewed, and production contamination tests for every public artifact.
111. [ ] Add end-to-end tests for search, compare, zoom, event selection, evidence inspection, URL restoration, and mobile navigation.
112. [ ] Add automated accessibility checks for labels, focus order, contrast, landmarks, and chart alternatives.
113. [ ] Add desktop and mobile screenshot regression tests for the public comparison workbench.
114. [x] Enforce performance budgets for initial manifest size, first useful render, interaction latency, and maximum loaded partitions.
115. [x] Run backend tests, frontend builds, data validation, interaction smoke tests, and Pages verification in scheduled refreshes.
116. [x] Prevent scheduled refresh commits from deploying when coverage unexpectedly drops or production records lose provenance.
117. [x] Publish a machine-readable refresh-health record and a human-readable Data Status summary.
118. [x] Add correction, withdrawal, supersession, and dataset rollback procedures with preserved prior state.
119. [x] Produce a release-candidate dataset with documented branch, year, source, trade, event, and market coverage.
120. [ ] Release only after the public workbench passes data-integrity, neutrality, accessibility, responsive-layout, performance, and provenance gates.

## Milestones

- **Usable comparison alpha:** steps 1-9, 16-30, 68-73, and 86-104.
- **Evidence-backed data beta:** steps 31-85 plus reviewed production records from at least two branches.
- **All-branch research beta:** reviewed records and coverage reporting for legislative, executive, and judicial sources from 2009 onward.
- **Public release candidate:** steps 106-120 with no known fixture contamination or provenance regressions.
