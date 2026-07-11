"""Add release relationship and temporal models.

Revision ID: 0004_release_relationship_model
Revises: 0003_congressional_service_terms
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_release_relationship_model"
down_revision = "0003_congressional_service_terms"
branch_labels = None
depends_on = None


def uuid_column(name: str, *, nullable: bool = False, foreign_key: str | None = None):
    args = [name, postgresql.UUID(as_uuid=True)]
    if foreign_key:
        args.append(sa.ForeignKey(foreign_key))
    return sa.Column(*args, nullable=nullable)


def upgrade() -> None:
    op.drop_constraint("trades_asset_class_check", "trades", type_="check")
    op.create_check_constraint(
        "ck_trades_asset_class",
        "trades",
        "asset_class IN ('equity','etf','mutual_fund','bond','fixed_income','crypto','option','commodity','real_estate','private_equity','other','unknown')",
    )
    op.drop_constraint("events_event_type_check", "events", type_="check")
    op.create_check_constraint(
        "ck_events_event_type",
        "events",
        "event_type IN ('legislation','bill_action','vote','funding','executive_order','presidential_document','agency_rule','court_decision','macro_release','role_change','macro','crypto_policy','other')",
    )

    op.create_table(
        "service_periods",
        uuid_column("id", nullable=False),
        uuid_column("person_id", foreign_key="people.id"),
        uuid_column("public_official_role_id", nullable=True, foreign_key="public_official_roles.id"),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("role_title", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id", "role_title", "start_date", "source_id", name="uq_service_periods_identity"
        ),
    )
    op.create_index("idx_service_periods_person_dates", "service_periods", ["person_id", "start_date", "end_date"])
    op.create_index("idx_service_periods_branch_dates", "service_periods", ["branch", "start_date", "end_date"])

    op.create_table(
        "issuers",
        uuid_column("id", nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("cik", sa.Text(), nullable=True),
        sa.Column("lei", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name", "cik", name="uq_issuers_name_cik"),
    )
    op.create_index("idx_issuers_cik", "issuers", ["cik"])

    op.create_table(
        "assets",
        uuid_column("id", nullable=False),
        uuid_column("issuer_id", nullable=True, foreign_key="issuers.id"),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("asset_class", sa.Text(), nullable=False),
        sa.Column("primary_symbol", sa.Text(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name", "asset_class", "primary_symbol", name="uq_assets_identity"),
    )
    op.create_index("idx_assets_symbol", "assets", ["primary_symbol"])
    op.create_index("idx_assets_issuer", "assets", ["issuer_id"])

    op.add_column("trades", uuid_column("asset_id", nullable=True))
    op.create_foreign_key("fk_trades_asset_id", "trades", "assets", ["asset_id"], ["id"])
    op.create_index("idx_trades_asset", "trades", ["asset_id"])

    for name in ["announcement_date", "effective_date", "publication_date"]:
        op.add_column("events", sa.Column(name, sa.Date(), nullable=True))
    op.add_column("events", sa.Column("source_tier", sa.Text(), nullable=False, server_default="official"))
    op.add_column("events", sa.Column("editor_status", sa.Text(), nullable=False, server_default="curated"))
    op.add_column(
        "events",
        sa.Column("methodology_version", sa.Text(), nullable=False, server_default="event-relevance-v1"),
    )

    op.create_table(
        "event_relationships",
        uuid_column("id", nullable=False),
        uuid_column("event_id", foreign_key="events.id"),
        uuid_column("person_id", nullable=True, foreign_key="people.id"),
        uuid_column("asset_id", nullable=True, foreign_key="assets.id"),
        sa.Column("organization_name", sa.Text(), nullable=True),
        sa.Column("relationship_type", sa.Text(), nullable=False),
        sa.Column("evidence_tier", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("methodology_version", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "person_id IS NOT NULL OR asset_id IS NOT NULL OR organization_name IS NOT NULL",
            name="ck_event_relationships_target",
        ),
    )
    op.create_index("idx_event_relationships_event", "event_relationships", ["event_id"])
    op.create_index("idx_event_relationships_person", "event_relationships", ["person_id"])
    op.create_index("idx_event_relationships_asset", "event_relationships", ["asset_id"])
    op.create_index("idx_event_relationships_tier", "event_relationships", ["evidence_tier", "review_status"])

    op.create_table(
        "trade_event_candidates",
        uuid_column("id", nullable=False),
        uuid_column("trade_id", foreign_key="trades.id"),
        uuid_column("event_id", foreign_key="events.id"),
        sa.Column("days_from_event", sa.Integer(), nullable=False),
        sa.Column("evidence_tier", sa.Text(), nullable=False),
        sa.Column("relationship_reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("internal_rank", sa.Numeric(), nullable=True),
        sa.Column("methodology_version", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_id", "event_id", "methodology_version", name="uq_trade_event_candidates_version"),
    )
    op.create_index("idx_trade_event_candidates_trade", "trade_event_candidates", ["trade_id"])
    op.create_index("idx_trade_event_candidates_event", "trade_event_candidates", ["event_id"])
    op.create_index("idx_trade_event_candidates_tier", "trade_event_candidates", ["evidence_tier", "review_status"])

    op.create_table(
        "relationship_reviews",
        uuid_column("id", nullable=False),
        uuid_column("candidate_id", foreign_key="trade_event_candidates.id"),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_relationship_reviews_candidate", "relationship_reviews", ["candidate_id"])

    op.create_table(
        "data_quality_issues",
        uuid_column("id", nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("issue_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_data_quality_issues_entity", "data_quality_issues", ["entity_type", "entity_id"])
    op.create_index("idx_data_quality_issues_status", "data_quality_issues", ["status", "severity"])


def downgrade() -> None:
    op.drop_index("idx_data_quality_issues_status", table_name="data_quality_issues")
    op.drop_index("idx_data_quality_issues_entity", table_name="data_quality_issues")
    op.drop_table("data_quality_issues")
    op.drop_index("idx_relationship_reviews_candidate", table_name="relationship_reviews")
    op.drop_table("relationship_reviews")
    op.drop_index("idx_trade_event_candidates_tier", table_name="trade_event_candidates")
    op.drop_index("idx_trade_event_candidates_event", table_name="trade_event_candidates")
    op.drop_index("idx_trade_event_candidates_trade", table_name="trade_event_candidates")
    op.drop_table("trade_event_candidates")
    op.drop_index("idx_event_relationships_tier", table_name="event_relationships")
    op.drop_index("idx_event_relationships_asset", table_name="event_relationships")
    op.drop_index("idx_event_relationships_person", table_name="event_relationships")
    op.drop_index("idx_event_relationships_event", table_name="event_relationships")
    op.drop_table("event_relationships")
    for name in ["methodology_version", "editor_status", "source_tier", "publication_date", "effective_date", "announcement_date"]:
        op.drop_column("events", name)
    op.drop_index("idx_trades_asset", table_name="trades")
    op.drop_constraint("fk_trades_asset_id", "trades", type_="foreignkey")
    op.drop_column("trades", "asset_id")
    op.drop_index("idx_assets_issuer", table_name="assets")
    op.drop_index("idx_assets_symbol", table_name="assets")
    op.drop_table("assets")
    op.drop_index("idx_issuers_cik", table_name="issuers")
    op.drop_table("issuers")
    op.drop_index("idx_service_periods_branch_dates", table_name="service_periods")
    op.drop_index("idx_service_periods_person_dates", table_name="service_periods")
    op.drop_table("service_periods")
    op.drop_constraint("ck_events_event_type", "events", type_="check")
    op.create_check_constraint(
        "events_event_type_check",
        "events",
        "event_type IN ('legislation','role_change','macro','other')",
    )
    op.drop_constraint("ck_trades_asset_class", "trades", type_="check")
    op.create_check_constraint(
        "trades_asset_class_check",
        "trades",
        "asset_class IN ('equity','etf','mutual_fund','bond','crypto','other','unknown')",
    )
