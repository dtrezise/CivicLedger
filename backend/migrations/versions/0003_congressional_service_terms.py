"""Add congressional service terms.

Revision ID: 0003_congressional_service_terms
Revises: 0002_public_official_roles
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_congressional_service_terms"
down_revision = "0002_public_official_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "congressional_service_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("bioguide_id", sa.Text(), nullable=False),
        sa.Column("congress_number", sa.Integer(), nullable=False),
        sa.Column("chamber", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("district", sa.Text(), nullable=True),
        sa.Column("party", sa.Text(), nullable=True),
        sa.Column("service_start", sa.Date(), nullable=True),
        sa.Column("service_end", sa.Date(), nullable=True),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_retrieved_at", sa.Date(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("chamber IN ('House','Senate')", name="ck_congressional_service_terms_chamber"),
        sa.UniqueConstraint(
            "bioguide_id",
            "congress_number",
            "chamber",
            "state",
            "district",
            name="uq_congressional_service_terms_identity",
        ),
    )
    op.create_index(
        "idx_congressional_service_terms_person",
        "congressional_service_terms",
        ["person_id"],
    )
    op.create_index(
        "idx_congressional_service_terms_bioguide",
        "congressional_service_terms",
        ["bioguide_id"],
    )
    op.create_index(
        "idx_congressional_service_terms_congress",
        "congressional_service_terms",
        ["congress_number", "chamber"],
    )
    op.create_index(
        "idx_congressional_service_terms_state_party",
        "congressional_service_terms",
        ["state", "party"],
    )


def downgrade() -> None:
    op.drop_index("idx_congressional_service_terms_state_party", table_name="congressional_service_terms")
    op.drop_index("idx_congressional_service_terms_congress", table_name="congressional_service_terms")
    op.drop_index("idx_congressional_service_terms_bioguide", table_name="congressional_service_terms")
    op.drop_index("idx_congressional_service_terms_person", table_name="congressional_service_terms")
    op.drop_table("congressional_service_terms")
