"""Tests for Alembic migration structure."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


class TestMigrationFiles:
    """Verify migration files exist and are well-formed."""

    def test_baseline_migration_exists(self):
        """001_create_golden_datasets.py migration file exists."""
        migration = MIGRATIONS_DIR / "001_create_golden_datasets.py"
        assert migration.exists(), f"Migration not found at {migration}"

    def test_baseline_has_upgrade_and_downgrade(self):
        """Baseline migration defines both upgrade() and downgrade()."""
        migration = MIGRATIONS_DIR / "001_create_golden_datasets.py"
        content = migration.read_text()
        assert "def upgrade()" in content
        assert "def downgrade()" in content

    def test_upgrade_creates_schema(self):
        """upgrade() creates the prompt_optimization schema."""
        migration = MIGRATIONS_DIR / "001_create_golden_datasets.py"
        content = migration.read_text()
        assert "CREATE SCHEMA IF NOT EXISTS" in content
        assert 'SCHEMA = "prompt_optimization"' in content

    def test_upgrade_creates_table(self):
        """upgrade() creates the golden_datasets table."""
        migration = MIGRATIONS_DIR / "001_create_golden_datasets.py"
        content = migration.read_text()
        assert "create_table" in content
        assert '"golden_datasets"' in content

    def test_upgrade_creates_indexes(self):
        """upgrade() creates both required indexes."""
        migration = MIGRATIONS_DIR / "001_create_golden_datasets.py"
        content = migration.read_text()
        assert '"idx_golden_prompt"' in content
        assert '"idx_golden_tenant"' in content

    def test_downgrade_drops_indexes(self):
        """downgrade() drops both indexes before the table."""
        migration = MIGRATIONS_DIR / "001_create_golden_datasets.py"
        content = migration.read_text()
        # downgrade should drop indexes first, then table, then schema
        down_start = content.index("def downgrade()")
        down_section = content[down_start:]
        assert "drop_index" in down_section
        assert "drop_table" in down_section
        assert "DROP SCHEMA" in down_section

    def test_downgrade_is_reversible(self):
        """downgrade() drops table and schema (reversibility check)."""
        migration = MIGRATIONS_DIR / "001_create_golden_datasets.py"
        content = migration.read_text()
        down_start = content.index("def downgrade()")
        down_section = content[down_start:]
        # Must drop in correct order: indexes → table → schema
        idx_pos = down_section.index("drop_index")
        tbl_pos = down_section.index("drop_table")
        schema_pos = down_section.index("DROP SCHEMA")
        assert idx_pos < tbl_pos < schema_pos

    def test_table_columns_present(self):
        """Migration includes all required columns."""
        migration = MIGRATIONS_DIR / "001_create_golden_datasets.py"
        content = migration.read_text()
        required_columns = [
            "prompt_name",
            "agent_code",
            "tenant_id",
            "input_context",
            "expected_output",
            "source",
            "quality_score",
            "active",
            "metadata",
            "created_at",
            "updated_at",
        ]
        for col in required_columns:
            assert f'"{col}"' in content, f"Column {col} not found in migration"


class TestAlembicConfig:
    """Verify Alembic configuration."""

    def test_alembic_ini_exists(self):
        """alembic.ini exists in service root."""
        ini = Path(__file__).resolve().parents[1] / "alembic.ini"
        assert ini.exists()

    def test_env_py_exists(self):
        """alembic/env.py exists."""
        env = Path(__file__).resolve().parents[1] / "alembic" / "env.py"
        assert env.exists()

    def test_env_imports_base_metadata(self):
        """env.py imports Base metadata for autogeneration support."""
        env = Path(__file__).resolve().parents[1] / "alembic" / "env.py"
        content = env.read_text()
        assert "from app.models import Base" in content
        assert "target_metadata = Base.metadata" in content
