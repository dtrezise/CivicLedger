# Architecture

## Product Surfaces

CivicLedger has two intentional frontend surfaces:

1. `pages-site/` is the canonical public comparison workbench and long-term public frontend.
2. `frontend/` is the authenticated-capable Docker/FastAPI companion for ingestion review, evidence inspection, and operational workflows.

The shared public data contract is `pages-site/data/manifest.json` plus its hashed partitions. Public features must consume this contract rather than create a second interpretation of generated data.

## Runtime Stack

- Public workbench: static HTML/CSS/JavaScript, ECharts 5.6, GitHub Pages.
- Review frontend: Next.js 14, TypeScript, TailwindCSS, Recharts.
- Backend: FastAPI, SQLAlchemy, Pydantic.
- Database: PostgreSQL managed through Alembic migrations.
- Local orchestration: Docker Compose.
- Scheduled generation: GitHub Actions plus source-specific Python builders.

## Data Flow

1. Official roster and source indexes are retrieved with source metadata.
2. Raw documents or source snapshots are hashed before parser output is promoted.
3. Parsers emit review-gated preview records with row/page evidence and confidence.
4. Normalizers resolve people, dated roles, assets, service periods, and event context.
5. Validators enforce service-time, provenance, record-state, coverage, and partition-hash contracts.
6. The Pages builder writes a small manifest and query-oriented partitions.
7. The browser loads overview data first, then selected officials and market symbols on demand.

## Public Partition Contract

- `overview`: dataset versions, methodology, public claims, and summary counts.
- `officials_index`: all searchable federal officials and dated role facets.
- `timeline_index`: only officials with source-backed transaction timeline lanes.
- `events`: curated anchors, official laws/orders/opinions, and macro releases.
- `coverage`: branch/source/year/record-state counts and known blockers.
- `officials/*`: one detailed transaction/event relationship timeline per official.
- `market/*`: one price-series partition per supported symbol or crypto pair.

The source-side neutral reaction dataset uses a separate hash-verified symbol-year
manifest under `data/context/trade_market_reactions/`. The Pages builder verifies
and reassembles those shards before emitting compact per-trade context. This keeps
individual repository objects small without weakening provenance checks.

Every manifest entry carries byte size and SHA-256. The release validator rejects unsafe paths, missing partitions, hash drift, fixture contamination, out-of-service plotting, and initial-load budget violations.

## Temporal Semantics

- Career mode uses cumulative active-service days and preserves nonconsecutive terms.
- Calendar mode uses real dates and leaves inactive gaps visible.
- Event mode requires an explicit event and centers a configurable before/after window.
- Transactions outside an official's dated service periods are withheld from that official's public timeline.
- Event relationships communicate evidence tiers and reasons, never causal conclusions.

## Release Gates

- Alembic upgrades an empty PostgreSQL database through the current revision.
- Backend tests and parser fixtures pass.
- Frontend production build passes.
- Public data and market validators pass.
- Docker Compose smoke test passes.
- No fixture row appears in a public transaction timeline.
- No preview record is labeled as reviewed or production.
- Every public partition matches its manifest hash and size.
- Coverage cannot silently drop below committed baselines.
- The curated trade-event ranking regression benchmark must retain its minimum
  precision and recall thresholds; those metrics are software-quality checks,
  not evidence of causation or investigative accuracy.
- GitHub Pages deploys and serves the manifest and a representative official partition.
