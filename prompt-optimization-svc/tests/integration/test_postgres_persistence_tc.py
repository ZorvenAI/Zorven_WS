"""Integration tests for PostgreSQL persistence via testcontainers (US-059).

Tests golden dataset, optimization run, schema snapshot, and tenant config
persistence against a real PostgreSQL container. Uses a test-specific
engine/session to avoid the module-level singleton in database.py.
"""

import os
import subprocess
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.models.golden_dataset import GoldenDataset
from app.models.optimization_run import OptimizationRun
from app.models.schema_snapshot import SchemaSnapshot
from app.models.tenant_config import TenantConfig

TEST_PREFIX = "__tc_pg_"


@pytest.mark.integration
class TestPostgresPersistenceTC:
    """PostgreSQL persistence via testcontainers."""

    @pytest.fixture
    async def session(self):
        """Create a test-specific async engine and session."""
        sync_url = os.environ.get(
            "POI_DATABASE_URL", "postgresql://mlflow:mlflow@localhost:5432/mlflow"
        )
        async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "postgresql+psycopg2://" in async_url:
            async_url = async_url.replace(
                "postgresql+psycopg2://", "postgresql+asyncpg://", 1
            )

        engine = create_async_engine(async_url, pool_pre_ping=True, echo=False)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with factory() as session:
            yield session

        # Cleanup test data
        async with factory() as cleanup:
            await cleanup.execute(
                text(
                    "DELETE FROM prompt_optimization.golden_datasets "
                    "WHERE prompt_name LIKE :prefix"
                ),
                {"prefix": f"{TEST_PREFIX}%"},
            )
            await cleanup.execute(
                text(
                    "DELETE FROM prompt_optimization.optimization_runs "
                    "WHERE prompt_name LIKE :prefix"
                ),
                {"prefix": f"{TEST_PREFIX}%"},
            )
            await cleanup.execute(
                text(
                    "DELETE FROM prompt_optimization.schema_snapshots "
                    "WHERE prompt_name LIKE :prefix"
                ),
                {"prefix": f"{TEST_PREFIX}%"},
            )
            await cleanup.execute(
                text(
                    "DELETE FROM prompt_optimization.tenant_configs "
                    "WHERE tenant_id LIKE :prefix"
                ),
                {"prefix": f"{TEST_PREFIX}%"},
            )
            await cleanup.commit()

        await engine.dispose()

    async def test_golden_dataset_insert_and_query(self, session):
        """Insert GoldenDataset row, query back, verify fields."""
        row = GoldenDataset(
            prompt_name=f"{TEST_PREFIX}gd-roundtrip",
            agent_code="mra",
            tenant_id=None,
            input_context={"context": {"brand_name": "TestBrand"}},
            expected_output="A comprehensive market research analysis.",
            source="manual",
            quality_score=0.95,
            active=True,
            metadata_extra={"industry": "tech"},
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        assert row.id is not None
        assert row.prompt_name == f"{TEST_PREFIX}gd-roundtrip"
        assert row.agent_code == "mra"
        assert row.input_context["context"]["brand_name"] == "TestBrand"
        assert row.quality_score == 0.95
        assert row.active is True
        assert row.created_at is not None

    async def test_golden_dataset_tenant_isolation(self, session):
        """Tenant A rows not visible when filtering by tenant B."""
        row_a = GoldenDataset(
            prompt_name=f"{TEST_PREFIX}gd-iso",
            agent_code="cga",
            tenant_id="tenant-a",
            input_context={"key": "value-a"},
            source="manual",
            active=True,
        )
        row_b = GoldenDataset(
            prompt_name=f"{TEST_PREFIX}gd-iso",
            agent_code="cga",
            tenant_id="tenant-b",
            input_context={"key": "value-b"},
            source="manual",
            active=True,
        )
        session.add_all([row_a, row_b])
        await session.commit()

        result = await session.execute(
            text(
                "SELECT tenant_id FROM prompt_optimization.golden_datasets "
                "WHERE prompt_name = :name AND tenant_id = :tid"
            ),
            {"name": f"{TEST_PREFIX}gd-iso", "tid": "tenant-a"},
        )
        rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "tenant-a"

    async def test_optimization_run_state_transitions(self, session):
        """QUEUED → RUNNING → COMPLETED persists correctly."""
        run_id = str(uuid.uuid4())
        run = OptimizationRun(
            id=run_id,
            prompt_name=f"{TEST_PREFIX}run-states",
            agent_code="bpa",
            group_name="wf2-positioning",
            state="QUEUED",
        )
        session.add(run)
        await session.commit()

        # Transition to RUNNING
        run.state = "RUNNING"
        run.mlflow_run_id = "mlflow-run-123"
        await session.commit()
        await session.refresh(run)
        assert run.state == "RUNNING"
        assert run.mlflow_run_id == "mlflow-run-123"

        # Transition to COMPLETED
        run.state = "COMPLETED"
        await session.commit()
        await session.refresh(run)
        assert run.state == "COMPLETED"

    async def test_schema_snapshot_roundtrip(self, session):
        """Insert SchemaSnapshot, verify schema_json round-trips."""
        schema_data = [
            {"name": "summary", "type": "string", "required": True, "max_length": 500},
            {"name": "score", "type": "number", "required": False},
        ]
        snap = SchemaSnapshot(
            prompt_name=f"{TEST_PREFIX}snap-rt",
            agent_code="mra",
            schema_json=schema_data,
            optimization_run_id=str(uuid.uuid4()),
        )
        session.add(snap)
        await session.commit()
        await session.refresh(snap)

        assert snap.id is not None
        assert snap.schema_json == schema_data
        assert len(snap.schema_json) == 2
        assert snap.schema_json[0]["name"] == "summary"
        assert snap.schema_json[1]["required"] is False

    async def test_tenant_config_persistence(self, session):
        """Insert TenantConfig row, query back, verify schedule."""
        config = TenantConfig(
            tenant_id=f"{TEST_PREFIX}cfg-persist",
            wf3_optimization_schedule="weekly",
        )
        session.add(config)
        await session.commit()
        await session.refresh(config)

        assert config.id is not None
        assert config.tenant_id == f"{TEST_PREFIX}cfg-persist"
        assert config.wf3_optimization_schedule == "weekly"
        assert config.created_at is not None

    async def test_alembic_migrations_at_head(self):
        """Verify alembic current shows head revision."""
        svc_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        env = os.environ.copy()
        result = subprocess.run(
            ["alembic", "current"],
            cwd=svc_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0
        assert "head" in result.stdout.lower() or "(head)" in result.stdout
