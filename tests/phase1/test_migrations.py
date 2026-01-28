from pathlib import Path


def test_migrations_include_extensions_and_tables():
    sql = Path("db/migrations/001_phase1_core.sql").read_text()
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in sql
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE TABLE IF NOT EXISTS document_snapshots" in sql
    assert "CREATE TABLE IF NOT EXISTS evidence" in sql
    assert "CREATE TABLE IF NOT EXISTS fact_evidence" in sql


def test_migrations_are_idempotent():
    sql = Path("db/migrations/001_phase1_core.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql
    assert "IF NOT EXISTS (SELECT 1 FROM pg_type" in sql
    assert "IF NOT EXISTS (SELECT 1 FROM pg_trigger" in sql
