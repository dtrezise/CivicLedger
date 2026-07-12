"""Enforce append-only relationship review history in PostgreSQL.

Revision ID: 0006_review_immutability
Revises: 0005_entity_history_model
Create Date: 2026-07-12
"""

from alembic import op


revision = "0006_review_immutability"
down_revision = "0005_entity_history_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_relationship_review_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'relationship_reviews is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_relationship_reviews_immutable
        BEFORE UPDATE OR DELETE ON relationship_reviews
        FOR EACH ROW EXECUTE FUNCTION reject_relationship_review_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_relationship_reviews_immutable ON relationship_reviews"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_relationship_review_mutation()")
