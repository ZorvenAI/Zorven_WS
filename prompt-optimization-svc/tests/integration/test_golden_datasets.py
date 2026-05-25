"""Integration tests for golden datasets (US-026).

Requires real PostgreSQL database.
"""

import os

import pytest

from app.datasets.golden_seed import GOLDEN_EXAMPLES


def _postgres_available() -> bool:
    """Check if PostgreSQL is reachable."""
    db_url = os.environ.get("POI_DATABASE_URL", "")
    if not db_url:
        return False
    try:
        import psycopg2

        conn = psycopg2.connect(db_url)
        conn.close()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="PostgreSQL not available (set POI_DATABASE_URL)",
)


@requires_postgres
class TestGoldenDatasetSeeder:
    """Seeder integration tests — require PostgreSQL."""

    async def test_seeder_creates_rows(self):
        from app.datasets.seeder import seed_golden_datasets
        from app.models.database import async_session_factory

        result = await seed_golden_datasets(async_session_factory)
        assert result.created + result.skipped == len(GOLDEN_EXAMPLES)
        assert result.errors == 0

    async def test_seeder_is_idempotent(self):
        from app.datasets.seeder import seed_golden_datasets
        from app.models.database import async_session_factory

        r1 = await seed_golden_datasets(async_session_factory)
        r2 = await seed_golden_datasets(async_session_factory)
        assert r2.skipped == r1.created + r1.skipped
        assert r2.created == 0


class TestGoldenDatasetStats:
    """Stats endpoint validation (no DB required)."""

    def test_stats_counts_match(self):
        from collections import Counter

        agent_counts = Counter(e.agent_code for e in GOLDEN_EXAMPLES)
        assert sum(agent_counts.values()) == len(GOLDEN_EXAMPLES)
        assert len(agent_counts) == 15

    def test_stats_industry_coverage(self):
        industries = {
            e.metadata_extra.get("industry")
            for e in GOLDEN_EXAMPLES
            if e.metadata_extra.get("industry")
        }
        assert len(industries) >= 10
