"""Add canonical entities, temporal history, and source snapshots.

Revision ID: 0005_entity_history_model
Revises: 0004_release_relationship_model
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_entity_history_model"
down_revision = "0004_release_relationship_model"
branch_labels = None
depends_on = None


def uuid_column(name: str, *, nullable: bool = False, foreign_key: str | None = None):
    args = [name, postgresql.UUID(as_uuid=True)]
    if foreign_key:
        args.append(sa.ForeignKey(foreign_key))
    return sa.Column(*args, nullable=nullable)


def jsonb_column(name: str = "source_metadata"):
    return sa.Column(
        name,
        postgresql.JSONB(),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def upgrade() -> None:
    op.add_column(
        "event_sources",
        sa.Column("source_type", sa.Text(), nullable=False, server_default="web"),
    )
    op.add_column("event_sources", sa.Column("title", sa.Text(), nullable=True))
    op.add_column("event_sources", sa.Column("publisher", sa.Text(), nullable=True))
    op.add_column(
        "event_sources", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("idx_event_sources_event", "event_sources", ["event_id"])
    op.create_index("idx_event_sources_url", "event_sources", ["url"])
    op.create_index("idx_event_sources_publisher", "event_sources", ["publisher"])

    op.create_table(
        "event_source_snapshots",
        uuid_column("id"),
        uuid_column("event_source_id", foreign_key="event_sources.id"),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hash_algorithm", sa.Text(), nullable=False, server_default="sha256"),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("content_length", sa.Integer(), nullable=True),
        jsonb_column("snapshot_metadata"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_source_id",
            "hash_algorithm",
            "content_hash",
            name="uq_event_source_snapshots_content",
        ),
        sa.CheckConstraint(
            "length(btrim(content_hash)) > 0", name="ck_event_source_snapshots_hash"
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="ck_event_source_snapshots_http_status",
        ),
        sa.CheckConstraint(
            "content_length IS NULL OR content_length >= 0",
            name="ck_event_source_snapshots_content_length",
        ),
    )
    op.create_index(
        "idx_event_source_snapshots_source_retrieved",
        "event_source_snapshots",
        ["event_source_id", "retrieved_at"],
    )
    op.create_index(
        "idx_event_source_snapshots_hash",
        "event_source_snapshots",
        ["hash_algorithm", "content_hash"],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_event_source_snapshot_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'event_source_snapshots are immutable; insert a new snapshot'
                USING ERRCODE = '55000';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_event_source_snapshots_immutable
        BEFORE UPDATE OR DELETE ON event_source_snapshots
        FOR EACH ROW EXECUTE FUNCTION prevent_event_source_snapshot_mutation()
        """
    )

    op.create_table(
        "jurisdictions",
        uuid_column("id"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("jurisdiction_type", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default="US"),
        uuid_column("parent_jurisdiction_id", nullable=True, foreign_key="jurisdictions.id"),
        sa.Column("source_url", sa.Text(), nullable=True),
        jsonb_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "jurisdiction_type", "country_code", "code", name="uq_jurisdictions_identity"
        ),
        sa.CheckConstraint(
            "parent_jurisdiction_id IS NULL OR parent_jurisdiction_id <> id",
            name="ck_jurisdictions_not_self_parent",
        ),
    )
    op.create_index("idx_jurisdictions_parent", "jurisdictions", ["parent_jurisdiction_id"])
    op.create_index("idx_jurisdictions_name", "jurisdictions", ["name"])

    op.create_table(
        "organizations",
        uuid_column("id"),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("organization_type", sa.Text(), nullable=False, server_default="company"),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        uuid_column("jurisdiction_id", nullable=True, foreign_key="jurisdictions.id"),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        jsonb_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_key", name="uq_organizations_canonical_key"),
        sa.CheckConstraint("length(btrim(canonical_name)) > 0", name="ck_organizations_name"),
        sa.CheckConstraint(
            "length(btrim(normalized_name)) > 0", name="ck_organizations_normalized_name"
        ),
        sa.CheckConstraint(
            "organization_type IN ('company','fund','government','nonprofit','partnership','trust','other')",
            name="ck_organizations_type",
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive','merged','dissolved','unknown')",
            name="ck_organizations_status",
        ),
    )
    op.create_index("idx_organizations_normalized_name", "organizations", ["normalized_name"])
    op.create_index("idx_organizations_type_status", "organizations", ["organization_type", "status"])
    op.create_index("idx_organizations_jurisdiction", "organizations", ["jurisdiction_id"])

    op.create_table(
        "organization_aliases",
        uuid_column("id"),
        uuid_column("organization_id", foreign_key="organizations.id"),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.Text(), nullable=False),
        sa.Column("alias_type", sa.Text(), nullable=False, server_default="name"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        uuid_column("source_snapshot_id", nullable=True, foreign_key="event_source_snapshots.id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "normalized_alias", "alias_type", name="uq_organization_aliases_identity"
        ),
        sa.CheckConstraint("length(btrim(alias)) > 0", name="ck_organization_aliases_alias"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_organization_aliases_dates",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_organization_aliases_confidence",
        ),
    )
    op.create_index("idx_organization_aliases_lookup", "organization_aliases", ["normalized_alias"])
    op.create_index("idx_organization_aliases_organization", "organization_aliases", ["organization_id"])

    op.create_table(
        "organization_identifiers",
        uuid_column("id"),
        uuid_column("organization_id", foreign_key="organizations.id"),
        sa.Column("scheme", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        uuid_column("source_snapshot_id", nullable=True, foreign_key="event_source_snapshots.id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheme", "value", name="uq_organization_identifiers_scheme_value"),
        sa.CheckConstraint("length(btrim(value)) > 0", name="ck_organization_identifiers_value"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_organization_identifiers_dates",
        ),
    )
    op.create_index("idx_organization_identifiers_organization", "organization_identifiers", ["organization_id"])
    op.create_index("idx_organization_identifiers_lookup", "organization_identifiers", ["scheme", "value"])

    op.create_table(
        "organization_relationships",
        uuid_column("id"),
        uuid_column("parent_organization_id", foreign_key="organizations.id"),
        uuid_column("child_organization_id", foreign_key="organizations.id"),
        sa.Column("relationship_type", sa.Text(), nullable=False, server_default="parent"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("ownership_percent", sa.Numeric(), nullable=True),
        sa.Column("is_direct", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        uuid_column("source_snapshot_id", nullable=True, foreign_key="event_source_snapshots.id"),
        jsonb_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "parent_organization_id <> child_organization_id",
            name="ck_organization_relationships_not_self",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_organization_relationships_dates",
        ),
        sa.CheckConstraint(
            "ownership_percent IS NULL OR (ownership_percent >= 0 AND ownership_percent <= 100)",
            name="ck_organization_relationships_ownership",
        ),
    )
    op.create_index(
        "uq_organization_relationships_identity",
        "organization_relationships",
        ["parent_organization_id", "child_organization_id", "relationship_type", "valid_from"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "idx_organization_relationships_parent",
        "organization_relationships",
        ["parent_organization_id", "valid_from", "valid_to"],
    )
    op.create_index(
        "idx_organization_relationships_child",
        "organization_relationships",
        ["child_organization_id", "valid_from", "valid_to"],
    )

    op.create_table(
        "sectors",
        uuid_column("id"),
        sa.Column("taxonomy", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        uuid_column("parent_sector_id", nullable=True, foreign_key="sectors.id"),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        jsonb_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("taxonomy", "code", name="uq_sectors_taxonomy_code"),
        sa.CheckConstraint(
            "parent_sector_id IS NULL OR parent_sector_id <> id", name="ck_sectors_not_self_parent"
        ),
        sa.CheckConstraint("level IS NULL OR level >= 0", name="ck_sectors_level"),
    )
    op.create_index("idx_sectors_parent", "sectors", ["parent_sector_id"])
    op.create_index("idx_sectors_name", "sectors", ["taxonomy", "name"])

    op.create_table(
        "organization_sectors",
        uuid_column("id"),
        uuid_column("organization_id", foreign_key="organizations.id"),
        uuid_column("sector_id", foreign_key="sectors.id"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        uuid_column("source_snapshot_id", nullable=True, foreign_key="event_source_snapshots.id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_organization_sectors_dates",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_organization_sectors_confidence",
        ),
    )
    op.create_index(
        "uq_organization_sectors_identity",
        "organization_sectors",
        ["organization_id", "sector_id", "valid_from"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "uq_organization_sectors_current_primary",
        "organization_sectors",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("is_primary AND valid_to IS NULL"),
    )
    op.create_index(
        "idx_organization_sectors_sector",
        "organization_sectors",
        ["sector_id", "valid_from", "valid_to"],
    )

    op.add_column("issuers", uuid_column("organization_id", nullable=True))
    op.create_foreign_key(
        "fk_issuers_organization_id", "issuers", "organizations", ["organization_id"], ["id"]
    )
    op.execute(
        """
        INSERT INTO organizations (
            id, canonical_key, canonical_name, normalized_name, organization_type,
            status, source_metadata, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            'legacy-issuer:' || id::text,
            canonical_name,
            lower(regexp_replace(btrim(canonical_name), '\\s+', ' ', 'g')),
            'company',
            'active',
            jsonb_build_object('migrated_from_issuer_id', id::text),
            COALESCE(created_at, now()),
            now()
        FROM issuers
        """
    )
    op.execute(
        """
        UPDATE issuers
        SET organization_id = organizations.id
        FROM organizations
        WHERE organizations.canonical_key = 'legacy-issuer:' || issuers.id::text
        """
    )
    op.execute(
        """
        INSERT INTO organization_identifiers (
            id, organization_id, scheme, value, is_primary, created_at
        )
        SELECT gen_random_uuid(), organization_id, 'cik', cik, true, now()
        FROM issuers WHERE cik IS NOT NULL AND btrim(cik) <> ''
        ON CONFLICT (scheme, value) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO organization_identifiers (
            id, organization_id, scheme, value, is_primary, created_at
        )
        SELECT gen_random_uuid(), organization_id, 'lei', lei, true, now()
        FROM issuers WHERE lei IS NOT NULL AND btrim(lei) <> ''
        ON CONFLICT (scheme, value) DO NOTHING
        """
    )
    op.alter_column("issuers", "organization_id", nullable=False)
    op.create_unique_constraint("uq_issuers_organization", "issuers", ["organization_id"])
    op.create_index("idx_issuers_organization", "issuers", ["organization_id"])

    op.create_table(
        "ticker_histories",
        uuid_column("id"),
        uuid_column("asset_id", foreign_key="assets.id"),
        uuid_column("organization_id", foreign_key="organizations.id"),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=True),
        sa.Column("mic", sa.String(length=4), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        uuid_column("source_snapshot_id", nullable=True, foreign_key="event_source_snapshots.id"),
        jsonb_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(btrim(symbol)) > 0", name="ck_ticker_histories_symbol"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_ticker_histories_dates",
        ),
    )
    op.create_index(
        "uq_ticker_histories_identity",
        "ticker_histories",
        ["asset_id", "symbol", "mic", "valid_from"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "uq_ticker_histories_current_primary",
        "ticker_histories",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("is_primary AND valid_to IS NULL"),
    )
    op.create_index(
        "idx_ticker_histories_symbol_dates", "ticker_histories", ["symbol", "valid_from", "valid_to"]
    )
    op.create_index(
        "idx_ticker_histories_organization",
        "ticker_histories",
        ["organization_id", "valid_from", "valid_to"],
    )

    op.create_table(
        "institutions",
        uuid_column("id"),
        uuid_column("organization_id", foreign_key="organizations.id"),
        sa.Column("institution_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("acronym", sa.Text(), nullable=True),
        sa.Column("branch", sa.Text(), nullable=True),
        sa.Column("chamber", sa.Text(), nullable=True),
        uuid_column("jurisdiction_id", nullable=True, foreign_key="jurisdictions.id"),
        uuid_column("parent_institution_id", nullable=True, foreign_key="institutions.id"),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("active_from", sa.Date(), nullable=True),
        sa.Column("active_to", sa.Date(), nullable=True),
        jsonb_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_institutions_organization"),
        sa.CheckConstraint(
            "institution_type IN ('agency','committee','subcommittee','court','office','legislature','other')",
            name="ck_institutions_type",
        ),
        sa.CheckConstraint(
            "parent_institution_id IS NULL OR parent_institution_id <> id",
            name="ck_institutions_not_self_parent",
        ),
        sa.CheckConstraint(
            "active_to IS NULL OR active_from IS NULL OR active_to >= active_from",
            name="ck_institutions_dates",
        ),
    )
    op.create_index("idx_institutions_type_name", "institutions", ["institution_type", "name"])
    op.create_index("idx_institutions_jurisdiction", "institutions", ["jurisdiction_id"])
    op.create_index("idx_institutions_parent", "institutions", ["parent_institution_id"])
    op.create_index(
        "uq_institutions_external_identity",
        "institutions",
        ["institution_type", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )

    op.create_table(
        "event_institution_links",
        uuid_column("id"),
        uuid_column("event_id", foreign_key="events.id"),
        uuid_column("institution_id", foreign_key="institutions.id"),
        uuid_column("jurisdiction_id", nullable=True, foreign_key="jurisdictions.id"),
        sa.Column("relationship_type", sa.Text(), nullable=False),
        sa.Column("docket_number", sa.Text(), nullable=True),
        sa.Column("proceeding_id", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        uuid_column("source_snapshot_id", nullable=True, foreign_key="event_source_snapshots.id"),
        jsonb_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_event_institution_links_identity",
        "event_institution_links",
        ["event_id", "institution_id", "relationship_type", "docket_number", "proceeding_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index("idx_event_institution_links_event", "event_institution_links", ["event_id"])
    op.create_index(
        "idx_event_institution_links_institution",
        "event_institution_links",
        ["institution_id", "relationship_type"],
    )
    op.create_index(
        "idx_event_institution_links_jurisdiction", "event_institution_links", ["jurisdiction_id"]
    )
    op.create_index("idx_event_institution_links_docket", "event_institution_links", ["docket_number"])

    filing_columns = [
        sa.Column("source_system", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("source_filing_id", sa.Text(), nullable=True),
        sa.Column("reporting_period_start", sa.Date(), nullable=True),
        sa.Column("reporting_period_end", sa.Date(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("certified_date", sa.Date(), nullable=True),
        sa.Column("amendment_number", sa.Integer(), nullable=False, server_default="0"),
        uuid_column("amends_filing_id", nullable=True),
        sa.Column("filing_status", sa.Text(), nullable=False, server_default="filed"),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="candidate"),
        sa.Column("is_late", sa.Boolean(), nullable=True),
        sa.Column("late_days", sa.Integer(), nullable=True),
        jsonb_column(),
    ]
    for column in filing_columns:
        op.add_column("filings", column)
    op.create_foreign_key(
        "fk_filings_amends_filing_id", "filings", "filings", ["amends_filing_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_filings_reporting_period",
        "filings",
        "reporting_period_end IS NULL OR reporting_period_start IS NULL OR reporting_period_end >= reporting_period_start",
    )
    op.create_check_constraint("ck_filings_amendment_number", "filings", "amendment_number >= 0")
    op.create_check_constraint(
        "ck_filings_source_system", "filings", "length(btrim(source_system)) > 0"
    )
    op.create_check_constraint(
        "ck_filings_status",
        "filings",
        "filing_status IN ('filed','amended','superseded','withdrawn','unknown')",
    )
    op.create_check_constraint(
        "ck_filings_review_status",
        "filings",
        "review_status IN ('candidate','reviewed','promoted','rejected','superseded')",
    )
    op.create_check_constraint(
        "ck_filings_not_self_amendment", "filings", "amends_filing_id IS NULL OR amends_filing_id <> id"
    )
    op.create_check_constraint("ck_filings_late_days", "filings", "late_days IS NULL OR late_days >= 0")
    op.create_index(
        "uq_filings_source_identity",
        "filings",
        ["source_system", "source_filing_id"],
        unique=True,
        postgresql_where=sa.text("source_filing_id IS NOT NULL"),
    )
    op.create_index(
        "idx_filings_person_period",
        "filings",
        ["person_id", "reporting_period_start", "reporting_period_end"],
    )
    op.create_index("idx_filings_review_status", "filings", ["review_status", "filed_date"])
    op.create_index("idx_filings_amends", "filings", ["amends_filing_id"])

    trade_columns = [
        sa.Column("source_transaction_id", sa.Text(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("asset_type_reported", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("capital_gains_over_200", sa.Boolean(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="candidate"),
        jsonb_column(),
    ]
    for column in trade_columns:
        op.add_column("trades", column)
    op.create_check_constraint(
        "ck_trades_owner",
        "trades",
        "owner IN ('self','spouse','dependent_child','joint','trust','other','unknown')",
    )
    op.create_check_constraint("ck_trades_source_page", "trades", "source_page IS NULL OR source_page > 0")
    op.create_check_constraint("ck_trades_source_row", "trades", "source_row IS NULL OR source_row > 0")
    op.create_check_constraint(
        "ck_trades_review_status",
        "trades",
        "review_status IN ('candidate','reviewed','promoted','rejected','superseded')",
    )
    op.create_index(
        "uq_trades_source_transaction",
        "trades",
        ["filing_id", "source_transaction_id"],
        unique=True,
        postgresql_where=sa.text("source_transaction_id IS NOT NULL"),
    )
    op.create_index("idx_trades_review_status", "trades", ["review_status", "trade_date"])


def downgrade() -> None:
    op.drop_index("idx_trades_review_status", table_name="trades")
    op.drop_index("uq_trades_source_transaction", table_name="trades")
    op.drop_constraint("ck_trades_review_status", "trades", type_="check")
    op.drop_constraint("ck_trades_source_row", "trades", type_="check")
    op.drop_constraint("ck_trades_source_page", "trades", type_="check")
    op.drop_constraint("ck_trades_owner", "trades", type_="check")
    for name in [
        "source_metadata",
        "review_status",
        "capital_gains_over_200",
        "source_row",
        "source_page",
        "description",
        "asset_type_reported",
        "owner",
        "source_transaction_id",
    ]:
        op.drop_column("trades", name)

    op.drop_index("idx_filings_amends", table_name="filings")
    op.drop_index("idx_filings_review_status", table_name="filings")
    op.drop_index("idx_filings_person_period", table_name="filings")
    op.drop_index("uq_filings_source_identity", table_name="filings")
    op.drop_constraint("ck_filings_late_days", "filings", type_="check")
    op.drop_constraint("ck_filings_not_self_amendment", "filings", type_="check")
    op.drop_constraint("ck_filings_review_status", "filings", type_="check")
    op.drop_constraint("ck_filings_status", "filings", type_="check")
    op.drop_constraint("ck_filings_source_system", "filings", type_="check")
    op.drop_constraint("ck_filings_amendment_number", "filings", type_="check")
    op.drop_constraint("ck_filings_reporting_period", "filings", type_="check")
    op.drop_constraint("fk_filings_amends_filing_id", "filings", type_="foreignkey")
    for name in [
        "source_metadata",
        "late_days",
        "is_late",
        "review_status",
        "filing_status",
        "amends_filing_id",
        "amendment_number",
        "certified_date",
        "received_date",
        "reporting_period_end",
        "reporting_period_start",
        "source_filing_id",
        "source_system",
    ]:
        op.drop_column("filings", name)

    for name in [
        "idx_event_institution_links_docket",
        "idx_event_institution_links_jurisdiction",
        "idx_event_institution_links_institution",
        "idx_event_institution_links_event",
        "uq_event_institution_links_identity",
    ]:
        op.drop_index(name, table_name="event_institution_links")
    op.drop_table("event_institution_links")
    for name in [
        "uq_institutions_external_identity",
        "idx_institutions_parent",
        "idx_institutions_jurisdiction",
        "idx_institutions_type_name",
    ]:
        op.drop_index(name, table_name="institutions")
    op.drop_table("institutions")
    for name in [
        "idx_ticker_histories_organization",
        "idx_ticker_histories_symbol_dates",
        "uq_ticker_histories_current_primary",
        "uq_ticker_histories_identity",
    ]:
        op.drop_index(name, table_name="ticker_histories")
    op.drop_table("ticker_histories")
    op.drop_index("idx_issuers_organization", table_name="issuers")
    op.drop_constraint("uq_issuers_organization", "issuers", type_="unique")
    op.drop_constraint("fk_issuers_organization_id", "issuers", type_="foreignkey")
    op.drop_column("issuers", "organization_id")

    op.drop_index("idx_organization_sectors_sector", table_name="organization_sectors")
    op.drop_index("uq_organization_sectors_current_primary", table_name="organization_sectors")
    op.drop_index("uq_organization_sectors_identity", table_name="organization_sectors")
    op.drop_table("organization_sectors")
    op.drop_index("idx_sectors_name", table_name="sectors")
    op.drop_index("idx_sectors_parent", table_name="sectors")
    op.drop_table("sectors")
    op.drop_index("idx_organization_relationships_child", table_name="organization_relationships")
    op.drop_index("idx_organization_relationships_parent", table_name="organization_relationships")
    op.drop_index("uq_organization_relationships_identity", table_name="organization_relationships")
    op.drop_table("organization_relationships")
    op.drop_index("idx_organization_identifiers_lookup", table_name="organization_identifiers")
    op.drop_index("idx_organization_identifiers_organization", table_name="organization_identifiers")
    op.drop_table("organization_identifiers")
    op.drop_index("idx_organization_aliases_organization", table_name="organization_aliases")
    op.drop_index("idx_organization_aliases_lookup", table_name="organization_aliases")
    op.drop_table("organization_aliases")
    op.drop_index("idx_organizations_jurisdiction", table_name="organizations")
    op.drop_index("idx_organizations_type_status", table_name="organizations")
    op.drop_index("idx_organizations_normalized_name", table_name="organizations")
    op.drop_table("organizations")
    op.drop_index("idx_jurisdictions_name", table_name="jurisdictions")
    op.drop_index("idx_jurisdictions_parent", table_name="jurisdictions")
    op.drop_table("jurisdictions")

    op.execute("DROP TRIGGER trg_event_source_snapshots_immutable ON event_source_snapshots")
    op.execute("DROP FUNCTION prevent_event_source_snapshot_mutation()")
    op.drop_index("idx_event_source_snapshots_hash", table_name="event_source_snapshots")
    op.drop_index("idx_event_source_snapshots_source_retrieved", table_name="event_source_snapshots")
    op.drop_table("event_source_snapshots")
    op.drop_index("idx_event_sources_publisher", table_name="event_sources")
    op.drop_index("idx_event_sources_url", table_name="event_sources")
    op.drop_index("idx_event_sources_event", table_name="event_sources")
    for name in ["published_at", "publisher", "title", "source_type"]:
        op.drop_column("event_sources", name)
