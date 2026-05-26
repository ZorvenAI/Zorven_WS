"""Golden dataset miner — promotes high-quality optimization runs (§6.3).

Queries completed optimization runs, filters by quality threshold,
and inserts qualifying examples into the golden_datasets table.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class MiningResult:
    """Summary of a mining operation."""

    mined: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[str] = field(default_factory=list)


async def mine_completed_runs(
    session_factory,
    quality_threshold: float = 0.8,
    lookback_days: int = 7,
) -> MiningResult:
    """Mine high-quality completed optimization runs into golden datasets.

    Queries optimization_runs for COMPLETED runs in the lookback window,
    filters by quality_threshold, and inserts into golden_datasets.

    Args:
        session_factory: Async SQLAlchemy session factory.
        quality_threshold: Minimum average scorer score (exclusive).
        lookback_days: Number of days to look back for completed runs.

    Returns:
        MiningResult with counts and details.
    """
    from app.models.golden_dataset import GoldenDataset
    from app.models.optimization_run import OptimizationRun

    result = MiningResult()
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    async with session_factory() as session:
        # Query completed runs within lookback window
        stmt = select(OptimizationRun).where(
            OptimizationRun.state == "COMPLETED",
            OptimizationRun.updated_at >= cutoff,
        )
        runs_result = await session.execute(stmt)
        runs = runs_result.scalars().all()

        if not runs:
            result.details.append("No completed runs found in lookback window.")
            return result

        for run in runs:
            try:
                # Simulate quality score from run metadata
                # In production, this would fetch scores from MLflow metrics
                quality_score = _compute_quality_score(run)

                if quality_score <= quality_threshold:
                    result.skipped += 1
                    result.details.append(
                        f"SKIP: {run.prompt_name} (score {quality_score:.2f} "
                        f"<= threshold {quality_threshold})"
                    )
                    continue

                # Check if already mined (idempotent)
                existing_stmt = select(GoldenDataset).where(
                    GoldenDataset.prompt_name == run.prompt_name,
                    GoldenDataset.agent_code == run.agent_code,
                    GoldenDataset.source == "mined",
                )
                # Add tenant filter for isolation (AC-3)
                if hasattr(run, "tenant_id") and getattr(run, "tenant_id", None):
                    existing_stmt = existing_stmt.where(
                        GoldenDataset.tenant_id == run.tenant_id
                    )
                else:
                    existing_stmt = existing_stmt.where(
                        GoldenDataset.tenant_id.is_(None)
                    )

                existing = await session.execute(existing_stmt)
                if existing.scalar_one_or_none() is not None:
                    result.skipped += 1
                    result.details.append(f"SKIP: {run.prompt_name} (already mined)")
                    continue

                # Insert mined example
                dataset_entry = GoldenDataset(
                    prompt_name=run.prompt_name,
                    agent_code=run.agent_code,
                    tenant_id=getattr(run, "tenant_id", None),
                    input_context={
                        "context_prompt_name": run.prompt_name,
                        "context_agent_code": run.agent_code,
                    },
                    expected_output=f"Mined from optimization run {run.id}",
                    source="mined",
                    quality_score=quality_score,
                    active=True,
                    metadata_extra={
                        "mlflow_run_id": run.mlflow_run_id or "",
                        "optimization_run_id": run.id,
                        "mined_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                session.add(dataset_entry)
                result.mined += 1
                result.details.append(
                    f"MINED: {run.prompt_name} (score {quality_score:.2f})"
                )

            except Exception as exc:
                result.errors += 1
                result.details.append(f"ERROR: {run.prompt_name} — {exc}")
                logger.error("Failed to mine run %s: %s", run.id, exc)

        await session.commit()

    logger.info(
        "Mining complete: %d mined, %d skipped, %d errors",
        result.mined,
        result.skipped,
        result.errors,
    )
    return result


def _compute_quality_score(run) -> float:
    """Compute aggregate quality score for an optimization run.

    In production, this fetches scorer metrics from the MLflow run.
    For now, uses a heuristic based on run metadata.
    """
    # If the run completed successfully and has an MLflow run ID,
    # it's considered a candidate. The actual score would come from
    # MLflow metric aggregation in a future iteration.
    if run.mlflow_run_id:
        return 0.85  # Placeholder — will be replaced with real MLflow metrics
    return 0.5  # Runs without MLflow tracking score lower
