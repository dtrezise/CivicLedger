# Architecture

## Current Stack

- Frontend: Next.js 14, TypeScript, TailwindCSS, Recharts.
- Backend: FastAPI, SQLAlchemy, Pydantic.
- Database: PostgreSQL.
- Local orchestration: Docker Compose.

## Runtime Services

- `frontend`: user interface on port 3000.
- `backend`: FastAPI service on port 8000.
- `db`: PostgreSQL database with schema from `db/init.sql`.

## System Layers

1. Data layer: raw source documents, fixture data, normalized tables.
2. Entity layer: people, offices, organizations, assets.
3. Filing layer: official filing metadata and retrieval provenance.
4. Trade layer: normalized transaction rows and parser confidence.
5. Temporal layer: trade dates, reported dates, service periods, event timelines.
6. Methodology layer: scoring rules, lag thresholds, benchmark rules.
7. Presentation layer: browse, profile, timeline, detail, methodology, and share-card views.

## API Contract Priorities

- Prefer stable explicit IDs such as `person_id`, `filing_id`, `trade_id`, and `event_id`.
- Include range metadata on timeline responses.
- Keep scorecard fields tied to disclosure completeness and data quality.
- Never expose a UI-only interpretation as if it were source data.

## Release Gates

- Backend Python syntax passes.
- Frontend typecheck/build passes.
- Docker Compose boots all services.
- API/frontend contracts are aligned.
- Fixture data is visibly labeled.
- Share-card disclaimers render in public-facing output.
