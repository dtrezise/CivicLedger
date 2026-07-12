from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, event as sqlalchemy_event
from sqlalchemy.orm import configure_mappers

from app.models import (
    Base,
    EventInstitutionLink,
    EventSourceSnapshot,
    Filing,
    Institution,
    Issuer,
    Organization,
    OrganizationAlias,
    OrganizationIdentifier,
    OrganizationRelationship,
    OrganizationSector,
    Sector,
    TickerHistory,
    Trade,
    _reject_event_source_snapshot_mutation,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0005_entity_history_model.py"
)


def constraint_names(model, constraint_type):
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, constraint_type)
    }


def index_by_name(model, name):
    return next(index for index in model.__table__.indexes if index.name == name)


def foreign_key_target(model, column_name):
    foreign_keys = list(model.__table__.c[column_name].foreign_keys)
    assert len(foreign_keys) == 1
    return foreign_keys[0].target_fullname


def test_entity_history_tables_are_registered_and_mappers_configure():
    configure_mappers()

    assert {
        "organizations",
        "organization_aliases",
        "organization_identifiers",
        "organization_relationships",
        "sectors",
        "organization_sectors",
        "ticker_histories",
        "jurisdictions",
        "institutions",
        "event_institution_links",
        "event_source_snapshots",
    }.issubset(Base.metadata.tables)


def test_issuer_is_a_required_one_to_one_profile_of_canonical_organization():
    assert Issuer.__table__.c.organization_id.nullable is False
    assert foreign_key_target(Issuer, "organization_id") == "organizations.id"
    assert "uq_issuers_organization" in constraint_names(Issuer, UniqueConstraint)
    assert "uq_organizations_canonical_key" in constraint_names(Organization, UniqueConstraint)


def test_alias_and_identifier_lookup_keys_are_canonical_and_sourceable():
    assert foreign_key_target(OrganizationAlias, "organization_id") == "organizations.id"
    assert foreign_key_target(OrganizationAlias, "source_snapshot_id") == "event_source_snapshots.id"
    assert foreign_key_target(OrganizationIdentifier, "source_snapshot_id") == "event_source_snapshots.id"
    assert "uq_organization_aliases_identity" in constraint_names(
        OrganizationAlias, UniqueConstraint
    )
    assert "uq_organization_identifiers_scheme_value" in constraint_names(
        OrganizationIdentifier, UniqueConstraint
    )
    assert index_by_name(OrganizationAlias, "idx_organization_aliases_lookup") is not None


def test_parent_sector_and_ticker_histories_preserve_time_ranges():
    for model, check_name in [
        (OrganizationRelationship, "ck_organization_relationships_dates"),
        (OrganizationSector, "ck_organization_sectors_dates"),
        (TickerHistory, "ck_ticker_histories_dates"),
    ]:
        assert check_name in constraint_names(model, CheckConstraint)

    assert "ck_organization_relationships_not_self" in constraint_names(
        OrganizationRelationship, CheckConstraint
    )
    assert "uq_sectors_taxonomy_code" in constraint_names(Sector, UniqueConstraint)
    assert foreign_key_target(TickerHistory, "asset_id") == "assets.id"
    assert foreign_key_target(TickerHistory, "organization_id") == "organizations.id"

    identity_index = index_by_name(TickerHistory, "uq_ticker_histories_identity")
    assert identity_index.unique is True
    assert identity_index.dialect_options["postgresql"]["nulls_not_distinct"] is True

    current_primary_index = index_by_name(
        TickerHistory, "uq_ticker_histories_current_primary"
    )
    assert current_primary_index.unique is True
    assert "is_primary" in str(current_primary_index.dialect_options["postgresql"]["where"])


def test_event_source_snapshots_have_content_identity_and_orm_immutability_guards():
    assert "uq_event_source_snapshots_content" in constraint_names(
        EventSourceSnapshot, UniqueConstraint
    )
    assert foreign_key_target(EventSourceSnapshot, "event_source_id") == "event_sources.id"
    assert sqlalchemy_event.contains(
        EventSourceSnapshot, "before_update", _reject_event_source_snapshot_mutation
    )
    assert sqlalchemy_event.contains(
        EventSourceSnapshot, "before_delete", _reject_event_source_snapshot_mutation
    )

    with pytest.raises(ValueError, match="insert a new snapshot"):
        _reject_event_source_snapshot_mutation()


def test_institution_links_cover_agencies_committees_courts_and_jurisdictions():
    institution_checks = {
        str(constraint.sqltext)
        for constraint in Institution.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    institution_type_check = next(
        text for text in institution_checks if "institution_type IN" in text
    )
    assert all(
        institution_type in institution_type_check
        for institution_type in ["agency", "committee", "court"]
    )
    assert foreign_key_target(Institution, "jurisdiction_id") == "jurisdictions.id"
    assert foreign_key_target(EventInstitutionLink, "event_id") == "events.id"
    assert foreign_key_target(EventInstitutionLink, "institution_id") == "institutions.id"
    assert foreign_key_target(EventInstitutionLink, "jurisdiction_id") == "jurisdictions.id"
    assert foreign_key_target(EventInstitutionLink, "source_snapshot_id") == "event_source_snapshots.id"
    assert {"docket_number", "proceeding_id"}.issubset(EventInstitutionLink.__table__.c.keys())


def test_disclosure_models_capture_source_identity_periods_amendments_and_row_provenance():
    assert {
        "source_system",
        "source_filing_id",
        "reporting_period_start",
        "reporting_period_end",
        "received_date",
        "certified_date",
        "amendment_number",
        "amends_filing_id",
        "filing_status",
        "review_status",
        "is_late",
        "late_days",
        "source_metadata",
    }.issubset(Filing.__table__.c.keys())
    assert foreign_key_target(Filing, "amends_filing_id") == "filings.id"
    assert index_by_name(Filing, "uq_filings_source_identity").unique is True

    assert {
        "source_transaction_id",
        "owner",
        "asset_type_reported",
        "description",
        "source_page",
        "source_row",
        "capital_gains_over_200",
        "review_status",
        "source_metadata",
    }.issubset(Trade.__table__.c.keys())
    assert index_by_name(Trade, "uq_trades_source_transaction").unique is True
    assert "ck_trades_owner" in constraint_names(Trade, CheckConstraint)


def test_migration_is_chained_and_database_immutability_trigger_is_present():
    migration = MIGRATION_PATH.read_text()

    assert 'revision = "0005_entity_history_model"' in migration
    assert 'down_revision = "0004_release_relationship_model"' in migration
    assert "CREATE TRIGGER trg_event_source_snapshots_immutable" in migration
    assert "BEFORE UPDATE OR DELETE ON event_source_snapshots" in migration
    assert "DROP TRIGGER trg_event_source_snapshots_immutable" in migration
