"""Celery task: optimize OIA prompts for a specific tenant.

On-demand only — no Beat schedule. Triggered via the /v1/optimize endpoint
with a tenant_id parameter. Checks the tenant's dataset floor before
running GEPA.
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

GROUP_NAME = "oia-onboarding-pipeline"
DEFAULT_DATASET_FLOOR = 50


async def _get_tenant_floor(tenant_id: str) -> int:
    """Load the tenant's min_gepa_dataset_size from TenantConfig."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from app.core.config import settings
    from app.models.database import get_async_url
    from app.models.tenant_config import TenantConfig

    engine = create_async_engine(
        get_async_url(settings.DATABASE_URL), pool_pre_ping=True, echo=False
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        stmt = select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
    await engine.dispose()
    return config.min_gepa_dataset_size if config else DEFAULT_DATASET_FLOOR


async def _count_tenant_examples(tenant_id: str) -> int:
    """Count active golden examples for the tenant's OIA agents."""
    from sqlalchemy import func, or_, select
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from app.core.config import settings
    from app.models.database import get_async_url
    from app.models.golden_dataset import GoldenDataset
    from app.registries.optimization_groups import get_group

    group = get_group(GROUP_NAME)
    agent_codes = list(group.agent_codes)

    engine = create_async_engine(
        get_async_url(settings.DATABASE_URL), pool_pre_ping=True, echo=False
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        stmt = (
            select(func.count())
            .select_from(GoldenDataset)
            .where(GoldenDataset.agent_code.in_(agent_codes))
            .where(GoldenDataset.active.is_(True))
            .where(
                or_(
                    GoldenDataset.tenant_id == tenant_id,
                    GoldenDataset.tenant_id.is_(None),
                )
            )
        )
        result = await session.execute(stmt)
        count = result.scalar_one()
    await engine.dispose()
    return count


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_tenant_oia.optimize_tenant_oia_pipeline",
)
def optimize_tenant_oia_pipeline(self, tenant_id: str, force: bool = False):
    """Run GEPA optimization for a tenant's OIA prompt overrides.

    Checks the dataset floor before proceeding. On-demand only.
    """
    if not tenant_id:
        return {
            "group_name": GROUP_NAME,
            "status": "FAILED",
            "error": "tenant_id is required",
        }

    floor = asyncio.run(_get_tenant_floor(tenant_id))
    count = asyncio.run(_count_tenant_examples(tenant_id))

    if count < floor:
        logger.info(
            "Tenant GEPA refused: tenant=%s, examples=%d, floor=%d",
            tenant_id,
            count,
            floor,
        )
        return {
            "group_name": GROUP_NAME,
            "tenant_id": tenant_id,
            "status": "REFUSED",
            "reason": (
                f"Dataset too small: {count} examples, minimum {floor} required"
            ),
            "current_count": count,
            "min_required": floor,
        }

    logger.info(
        "Starting tenant OIA optimization: tenant=%s, examples=%d",
        tenant_id,
        count,
    )

    from app.scorers import COMMON_SCORERS, OIA_SCORERS
    from app.tasks.optimization_runner import run_group_optimization

    return run_group_optimization(
        group_name=GROUP_NAME,
        scorers=COMMON_SCORERS + OIA_SCORERS,
        celery_task_self=self,
        tenant_id=tenant_id,
    )
