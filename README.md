# CivicLedger

Federal public financial disclosure tracker. View reporting timelines, disclosure completeness scorecards, and provenance data for officials across the legislative, executive, and judicial branches.

> Current data is fixture/demo data. CivicLedger is a disclosure-transparency and provenance tool; it does not make legal, ethics, causation, insider-trading, or investment conclusions.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (v2+)

## Quick Start

```bash
docker compose up --build
```

This will:
1. Start PostgreSQL with the schema (`init.sql`)
2. Start the FastAPI backend on **:8000** (runs seed script on first boot)
3. Start the Next.js frontend on **:3000**

## URLs

| Service          | URL                            |
|------------------|--------------------------------|
| Frontend         | http://localhost:3000           |
| Backend API      | http://localhost:8000           |
| API Docs (Swagger) | http://localhost:8000/docs    |
| API Docs (ReDoc) | http://localhost:8000/redoc     |

## Seed Data

On first startup the backend automatically seeds the database with:
- **3 congressional fixture officials** (2 senators, 1 representative)
- **3–5 filings** per person
- **10–20 trades** per person across 18+ months
- **SPY and DIA** daily market series (Jan 2023 – Aug 2024)
- **10 curated events** with source links

## Architecture

```
.
├── frontend/          Next.js 14 + TypeScript + Recharts + TailwindCSS
├── backend/           FastAPI + SQLAlchemy + Pydantic
├── db/                PostgreSQL schema (init.sql)
├── docs/              Product, architecture, provenance, roadmap, and agent roles
└── docker-compose.yml
```

## Project Docs

| File | Purpose |
|------|---------|
| `docs/product_brief.md` | Product boundaries and MVP definition |
| `docs/architecture.md` | System layers and release gates |
| `docs/data_model.md` | Current and next data model |
| `docs/provenance_policy.md` | Source, fixture, correction, and share-card rules |
| `docs/official_sources.md` | Official legislative, executive, and judicial source intake plan |
| `docs/roadmap.md` | Stabilization and phased build plan |
| `docs/agentic_roles.md` | Expert roles and guardrails for project development |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/meta/status` | Dataset version and ingestion status |
| GET | `/meta/methodology` | Methodology blocks and key rules |
| GET | `/meta/sources` | Official source registry and intake status |
| GET | `/search/people?q=` | Autocomplete search |
| GET | `/people` | Browse directory (filterable, paginated) |
| GET | `/people/batch_stats?ids=` | Batch stats for multiple people |
| GET | `/people/{id}` | Person detail |
| GET | `/people/{id}/scorecard` | Disclosure scorecard |
| GET | `/people/{id}/timeline` | Timeline buckets + gaps |
| GET | `/people/{id}/trades` | Trade list (filterable, paginated) |
| GET | `/trades/{id}` | Trade detail + provenance |
| GET | `/filings/{id}` | Filing detail + provenance |
| GET | `/market/series` | Market overlay data (SPY, DIA) |
| GET | `/events` | Curated events |
| GET | `/events/{id}` | Event detail + source links |
| POST | `/sharecards` | Generate a share card |
| GET | `/sharecards/{id}` | Retrieve share card |

## Frontend Pages

| Route | Screen |
|-------|--------|
| `/` | Home (search + status) |
| `/browse` | Browse Directory |
| `/people/[id]` | Profile Overview (scorecard + timeline) |
| `/people/[id]/timeline` | Timeline Detail |
| `/people/[id]/trades` | Trades List |
| `/trades/[tradeId]` | Trade Detail + Provenance |
| `/sharecards/new` | Share Card Builder |
| `/methodology` | Methodology |

## Resetting Data

```bash
docker compose down -v
docker compose up --build
```

## Development

```bash
# Backend only
cd backend && pip install -e . && uvicorn app.main:app --reload

# Frontend only
cd frontend && npm install && npm run dev
```
