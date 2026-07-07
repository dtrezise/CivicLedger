"""Initial CivicLedger schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-06
"""

from pathlib import Path

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    init_sql = Path(__file__).resolve().parents[3] / "db" / "init.sql"
    statements = [
        statement.strip()
        for statement in init_sql.read_text().split(";")
        if statement.strip()
        and "public_official_roles" not in statement
        and "congressional_service_terms" not in statement
    ]
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for table_name in [
        "congressional_service_terms",
        "sharecards",
        "market_series",
        "event_sources",
        "events",
        "parser_artifacts",
        "trades",
        "filings",
        "raw_documents",
        "ingestion_runs",
        "people",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
