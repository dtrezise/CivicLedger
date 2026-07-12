from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_relationship_review_migration_enforces_database_append_only_history():
    migration = (
        ROOT
        / "backend"
        / "migrations"
        / "versions"
        / "0006_review_immutability.py"
    ).read_text()

    assert 'down_revision = "0005_entity_history_model"' in migration
    assert "BEFORE UPDATE OR DELETE ON relationship_reviews" in migration
    assert "relationship_reviews is append-only" in migration
