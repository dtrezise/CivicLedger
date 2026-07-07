"""Add source-backed public official roles.

Revision ID: 0002_public_official_roles
Revises: 0001_initial_schema
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_public_official_roles"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_official_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("external_role_id", sa.Text(), nullable=False, unique=True),
        sa.Column("external_person_id", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("presidential_term", sa.Text(), nullable=False),
        sa.Column("administration", sa.Text(), nullable=False),
        sa.Column("role_category", sa.Text(), nullable=False),
        sa.Column("role_title", sa.Text(), nullable=False),
        sa.Column("office", sa.Text(), nullable=True),
        sa.Column("agency", sa.Text(), nullable=True),
        sa.Column("court", sa.Text(), nullable=True),
        sa.Column("service_start", sa.Date(), nullable=True),
        sa.Column("service_end", sa.Date(), nullable=True),
        sa.Column("appointing_president", sa.Text(), nullable=True),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_tier", sa.Text(), nullable=False, server_default="official"),
        sa.Column("source_retrieved_at", sa.Date(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("branch IN ('Executive','Judicial','Legislative')", name="ck_public_official_roles_branch"),
    )
    op.create_index("idx_public_official_roles_person", "public_official_roles", ["person_id"])
    op.create_index(
        "idx_public_official_roles_branch_term",
        "public_official_roles",
        ["branch", "presidential_term"],
    )
    op.create_index("idx_public_official_roles_category", "public_official_roles", ["role_category"])


def downgrade() -> None:
    op.drop_index("idx_public_official_roles_category", table_name="public_official_roles")
    op.drop_index("idx_public_official_roles_branch_term", table_name="public_official_roles")
    op.drop_index("idx_public_official_roles_person", table_name="public_official_roles")
    op.drop_table("public_official_roles")
