"""Add reviewer assignments, saved filters, and review sessions.

Revision ID: 0007_reviewer_workspaces
Revises: 0006_review_immutability
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_reviewer_workspaces"
down_revision = "0006_review_immutability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("filter_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'completed')", name="ck_review_sessions_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_review_sessions_reviewer", "review_sessions", ["reviewer", "started_at"])
    op.create_table(
        "review_saved_filters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("criteria", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner", "name", name="uq_review_saved_filters_owner_name"),
    )
    op.create_index("idx_review_saved_filters_owner", "review_saved_filters", ["owner", "name"])
    op.create_table(
        "review_assignment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("assignee", sa.Text(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('assign', 'release', 'complete')",
            name="ck_review_assignment_events_action",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["trade_event_candidates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_review_assignment_events_candidate",
        "review_assignment_events",
        ["candidate_id", "occurred_at"],
    )
    op.create_index(
        "idx_review_assignment_events_assignee",
        "review_assignment_events",
        ["assignee", "occurred_at"],
    )
    op.add_column(
        "relationship_reviews",
        sa.Column("review_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_relationship_reviews_session",
        "relationship_reviews",
        "review_sessions",
        ["review_session_id"],
        ["id"],
    )
    op.create_index(
        "idx_relationship_reviews_session", "relationship_reviews", ["review_session_id"]
    )
    op.execute(
        """
        CREATE TRIGGER trg_review_assignment_events_immutable
        BEFORE UPDATE OR DELETE ON review_assignment_events
        FOR EACH ROW EXECUTE FUNCTION reject_relationship_review_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_review_assignment_events_immutable ON review_assignment_events"
    )
    op.drop_index("idx_relationship_reviews_session", table_name="relationship_reviews")
    op.drop_constraint(
        "fk_relationship_reviews_session", "relationship_reviews", type_="foreignkey"
    )
    op.drop_column("relationship_reviews", "review_session_id")
    op.drop_index("idx_review_assignment_events_assignee", table_name="review_assignment_events")
    op.drop_index("idx_review_assignment_events_candidate", table_name="review_assignment_events")
    op.drop_table("review_assignment_events")
    op.drop_index("idx_review_saved_filters_owner", table_name="review_saved_filters")
    op.drop_table("review_saved_filters")
    op.drop_index("idx_review_sessions_reviewer", table_name="review_sessions")
    op.drop_table("review_sessions")
