"""Shared optimization runner for all GEPA Celery tasks.

Encapsulates the full 15-step optimization pipeline:
QUEUED → ACQUIRING_LOCK → LOADING_DATA → OPTIMIZING → VALIDATING
→ CANARY (or PENDING_APPROVAL for critical agents) → COMPLETED

Called by optimize_wf{1,2,3} tasks after their schedule guards pass.
"""

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def run_group_optimization(
    group_name: str,
    scorers: list[Any],
    celery_task_self: Any,
) -> dict[str, Any]:
    """Run the full GEPA optimization pipeline for a named group.

    Args:
        group_name: Optimization group name (e.g., "wf1-discovery-pipeline").
        scorers: List of MLflow scorer callables for evaluation.
        celery_task_self: Celery task instance (for request.id).

    Returns:
        Dict with run_id, status, scores, and metadata.
    """
    run_id = getattr(getattr(celery_task_self, "request", None), "id", None) or str(
        uuid.uuid4()
    )

    try:
        return asyncio.run(_run_optimization_pipeline(run_id, group_name, scorers))
    except Exception as exc:
        logger.exception(
            "Optimization runner failed: group=%s, run=%s", group_name, run_id
        )
        return {
            "run_id": run_id,
            "group_name": group_name,
            "status": "FAILED",
            "error": str(exc),
        }


async def _run_optimization_pipeline(
    run_id: str,
    group_name: str,
    scorers: list[Any],
) -> dict[str, Any]:
    """Async pipeline orchestrating the full optimization flow.

    The GEPA call itself is synchronous (MLflow optimize_prompts is sync),
    so it blocks the event loop — acceptable in a Celery worker context
    where only one task runs per prefork.
    """
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings
    from app.logic.approval_gate import requires_approval
    from app.logic.canary_manager import CanaryManager
    from app.logic.guardrails import (
        run_candidate_guardrails,
        run_pre_optimization_guardrails,
    )
    from app.logic.gepa_guardrails import check_gepa_mutation
    from app.logic.lifecycle import PromptLifecycleManager, PromptState
    from app.logic.run_lifecycle import RunLifecycleManager, RunState
    from app.metrics import record_optimization_run, record_prompt_quality
    from app.models.database import async_session_factory
    from app.predict_fns.factory import make_predict_fn
    from app.registries.optimization_groups import get_group
    from app.services.gepa_optimizer import ZorvenGepaOptimizer
    from app.services.joint_optimizer import JointOptimizer
    from app.services.mlflow_registry import MLflowPromptRegistry
    from app.services.reflection_context_enricher import ReflectionContextEnricher
    from app.services.skill_registry_reader import SkillRegistryReader

    # ── Initialize service dependencies ──
    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()

    run_lcm = RunLifecycleManager(
        prompt_cache=cache,
        lifecycle_producer=None,
        db_session_factory=async_session_factory,
    )

    registry = MLflowPromptRegistry(settings.MLFLOW_TRACKING_URI)
    lifecycle_mgr = PromptLifecycleManager(registry)
    canary_mgr = CanaryManager(cache, lifecycle_manager=lifecycle_mgr)

    group = get_group(group_name)
    primary_agent = group.agent_codes[0]

    try:
        # ── Step 1: QUEUED ──
        await run_lcm.transition(
            run_id=run_id,
            from_state=RunState.QUEUED,
            to_state=RunState.ACQUIRING_LOCK,
            prompt_name=group.prompt_names[0],
            agent_code=primary_agent,
        )

        # ── Step 2: ACQUIRING_LOCK ──
        lock_acquired = await cache.acquire_optimization_lock(
            group=group_name, owner=run_id
        )
        if not lock_acquired:
            retry_at = await run_lcm.defer_on_lock_conflict(
                run_id=run_id,
                prompt_name=group.prompt_names[0],
                agent_code=primary_agent,
            )
            logger.info(
                "Optimization deferred (lock conflict): group=%s, retry_at=%s",
                group_name,
                retry_at.isoformat(),
            )
            return {
                "run_id": run_id,
                "group_name": group_name,
                "status": "DEFERRED",
                "retry_at": retry_at.isoformat(),
            }

        # ── Step 3: LOADING_DATA ──
        await run_lcm.transition(
            run_id=run_id,
            from_state=RunState.ACQUIRING_LOCK,
            to_state=RunState.LOADING_DATA,
            prompt_name=group.prompt_names[0],
            agent_code=primary_agent,
        )

        train_data = await _load_golden_dataset(group, async_session_factory)
        if not train_data:
            await run_lcm.transition(
                run_id=run_id,
                from_state=RunState.LOADING_DATA,
                to_state=RunState.FAILED,
                prompt_name=group.prompt_names[0],
                agent_code=primary_agent,
                error_message="No golden dataset examples found",
            )
            return {
                "run_id": run_id,
                "group_name": group_name,
                "status": "FAILED",
                "error": "No golden dataset examples found",
            }

        # ── Step 4: Pre-optimization guardrails ──
        pre_result = await run_pre_optimization_guardrails(
            examples=train_data,
            min_dataset_size=3,
            cache_manager=cache,
            optimization_group=group_name,
            lock_owner=run_id,
        )
        if not pre_result.all_passed:
            failure_msg = (
                pre_result.first_failure.message
                if pre_result.first_failure
                else "Pre-optimization guardrail failed"
            )
            await run_lcm.transition(
                run_id=run_id,
                from_state=RunState.LOADING_DATA,
                to_state=RunState.FAILED,
                prompt_name=group.prompt_names[0],
                agent_code=primary_agent,
                error_message=failure_msg,
            )
            return {
                "run_id": run_id,
                "group_name": group_name,
                "status": "FAILED",
                "error": failure_msg,
            }

        # ── Step 5: OPTIMIZING ──
        await run_lcm.transition(
            run_id=run_id,
            from_state=RunState.LOADING_DATA,
            to_state=RunState.OPTIMIZING,
            prompt_name=group.prompt_names[0],
            agent_code=primary_agent,
        )

        # Get current production prompt template for baseline comparison
        base_prompt_text = ""
        prod_info = registry.get_prompt_by_state(group.prompt_names[0], "PRODUCTION")
        if prod_info:
            base_prompt_text = prod_info.template

        # Create predict function for the primary prompt
        predict_fn = make_predict_fn(group.prompt_names[0])

        # Create GEPA optimizer with reflection context enrichment
        gepa = ZorvenGepaOptimizer()
        enricher = None
        try:
            skill_reader = SkillRegistryReader()
            enricher = ReflectionContextEnricher(skill_reader)
        except Exception as exc:
            logger.warning("Reflection context enricher unavailable: %s", exc)

        joint_opt = JointOptimizer(
            gepa_optimizer=gepa,
            registry=registry,
            lifecycle_manager=lifecycle_mgr,
            reflection_enricher=enricher,
        )

        # ── Step 7: Run GEPA optimization (synchronous, blocks event loop) ──
        logger.info(
            "Starting GEPA optimization: group=%s, examples=%d, scorers=%d",
            group_name,
            len(train_data),
            len(scorers),
        )
        opt_result = joint_opt.optimize_group(
            group_name=group_name,
            predict_fn=predict_fn,
            train_data=train_data,
            scorers=scorers,
        )

        if opt_result.error:
            await run_lcm.transition(
                run_id=run_id,
                from_state=RunState.OPTIMIZING,
                to_state=RunState.FAILED,
                prompt_name=group.prompt_names[0],
                agent_code=primary_agent,
                error_message=opt_result.error,
            )
            return {
                "run_id": run_id,
                "group_name": group_name,
                "status": "FAILED",
                "error": opt_result.error,
                "candidates_evaluated": opt_result.candidates_evaluated,
                "duration_seconds": opt_result.duration_seconds,
            }

        # ── Step 8: VALIDATING ──
        await run_lcm.transition(
            run_id=run_id,
            from_state=RunState.OPTIMIZING,
            to_state=RunState.VALIDATING,
            prompt_name=group.prompt_names[0],
            agent_code=primary_agent,
        )

        # Run candidate guardrails (OPT-02, OPT-06, OPT-09, OPT-10, OPT-12)
        estimated_cost = (
            opt_result.candidates_evaluated * settings.COST_PER_CANDIDATE_USD
        )
        candidate_result = run_candidate_guardrails(
            candidate_text=opt_result.best_prompt,
            base_text=base_prompt_text,
            current_cost_usd=estimated_cost,
        )

        if not candidate_result.all_passed:
            failure_msg = (
                candidate_result.first_failure.message
                if candidate_result.first_failure
                else "Candidate guardrail failed"
            )
            await run_lcm.transition(
                run_id=run_id,
                from_state=RunState.VALIDATING,
                to_state=RunState.FAILED,
                prompt_name=group.prompt_names[0],
                agent_code=primary_agent,
                error_message=failure_msg,
            )
            return {
                "run_id": run_id,
                "group_name": group_name,
                "status": "FAILED",
                "error": failure_msg,
                "guardrail_failures": [
                    r.guardrail_id for r in candidate_result.results if not r.passed
                ],
            }

        # OPT-11: Placeholder invariance check
        if base_prompt_text and opt_result.best_prompt:
            mutation_ok, invariance = check_gepa_mutation(
                base_prompt_text, opt_result.best_prompt
            )
            if not mutation_ok:
                await run_lcm.transition(
                    run_id=run_id,
                    from_state=RunState.VALIDATING,
                    to_state=RunState.REJECTED,
                    prompt_name=group.prompt_names[0],
                    agent_code=primary_agent,
                    error_message=f"OPT-11: Placeholder invariance violated — {invariance}",
                )
                return {
                    "run_id": run_id,
                    "group_name": group_name,
                    "status": "REJECTED",
                    "error": f"OPT-11: Placeholder invariance violated",
                }

        # ── Step 10: Check improvement threshold ──
        score_before = 0.0
        score_after = opt_result.overall_score
        improvement_pct = 0.0
        if score_before > 0:
            improvement_pct = (score_after - score_before) / score_before

        # ── Step 12: Register optimized prompt as new MLflow version ──
        new_version = None
        if opt_result.best_prompt:
            for prompt_name in group.prompt_names:
                prompt_result = opt_result.prompt_results.get(
                    prompt_name, opt_result.best_prompt
                )
                if prompt_result:
                    new_info = registry.register_prompt(
                        name=prompt_name,
                        template=prompt_result,
                        tags={
                            "state": PromptState.STAGING.value,
                            "optimization_run_id": run_id,
                            "mlflow_run_id": opt_result.mlflow_run_id,
                            "agent_code": primary_agent,
                        },
                    )
                    if new_version is None:
                        new_version = new_info

        # Update Redis progress with scores
        if cache is not None:
            await cache.set_optimization_progress(
                run_id,
                {
                    "state": "VALIDATING",
                    "prompt_name": group.prompt_names[0],
                    "agent_code": primary_agent,
                    "group_name": group_name,
                    "score_before": str(score_before),
                    "score_after": str(score_after),
                    "improvement": str(improvement_pct),
                    "cost_usd": str(estimated_cost),
                    "candidates_evaluated": str(opt_result.candidates_evaluated),
                    "mlflow_run_id": opt_result.mlflow_run_id,
                },
            )

        # ── Step 13/14: Route to approval or canary ──
        any_critical = any(requires_approval(ac) for ac in group.agent_codes)

        if any_critical:
            # CRITICAL agents (adpub, coa) require human approval
            await run_lcm.transition(
                run_id=run_id,
                from_state=RunState.VALIDATING,
                to_state=RunState.PENDING_APPROVAL,
                prompt_name=group.prompt_names[0],
                agent_code=primary_agent,
            )
            final_status = "PENDING_APPROVAL"
            logger.info(
                "Optimization awaiting approval: group=%s, run=%s (critical agents: %s)",
                group_name,
                run_id,
                [ac for ac in group.agent_codes if requires_approval(ac)],
            )
        else:
            # Non-critical: start canary deployment
            await run_lcm.transition(
                run_id=run_id,
                from_state=RunState.VALIDATING,
                to_state=RunState.CANARY,
                prompt_name=group.prompt_names[0],
                agent_code=primary_agent,
            )

            if new_version is not None:
                prod_version = 1
                if prod_info:
                    prod_version = prod_info.version
                await canary_mgr.start_canary(
                    prompt_name=group.prompt_names[0],
                    canary_version=new_version.version,
                    production_version=prod_version,
                    agent_code=primary_agent,
                )
                logger.info(
                    "Canary started: group=%s, prompt=%s, v%d vs v%d",
                    group_name,
                    group.prompt_names[0],
                    new_version.version,
                    prod_version,
                )

            final_status = "CANARY"

        # ── Step 15: Record Prometheus metrics ──
        record_optimization_run(
            agent_code=primary_agent,
            group_name=group_name,
            duration_seconds=opt_result.duration_seconds,
            cost_usd=estimated_cost,
        )
        record_prompt_quality(
            agent_code=primary_agent,
            prompt_name=group.prompt_names[0],
            improvement_pct=improvement_pct * 100,
            regression_pct=0.0,
        )

        logger.info(
            "Optimization complete: group=%s, status=%s, score=%.3f, "
            "candidates=%d, duration=%.1fs, cost=$%.2f",
            group_name,
            final_status,
            opt_result.overall_score,
            opt_result.candidates_evaluated,
            opt_result.duration_seconds,
            estimated_cost,
        )

        return {
            "run_id": run_id,
            "group_name": group_name,
            "status": final_status,
            "overall_score": opt_result.overall_score,
            "candidates_evaluated": opt_result.candidates_evaluated,
            "duration_seconds": opt_result.duration_seconds,
            "cost_usd": estimated_cost,
            "mlflow_run_id": opt_result.mlflow_run_id,
            "prompt_count": len(group.prompt_names),
            "agent_codes": list(group.agent_codes),
        }

    except Exception as exc:
        # Catch-all: transition to FAILED
        try:
            await run_lcm.transition(
                run_id=run_id,
                from_state=RunState.OPTIMIZING,
                to_state=RunState.FAILED,
                prompt_name=group.prompt_names[0],
                agent_code=primary_agent,
                error_message=str(exc),
            )
        except Exception:
            pass
        raise

    finally:
        # Always release the optimization lock
        try:
            await cache.release_optimization_lock(group_name, run_id)
        except Exception as release_exc:
            logger.warning(
                "Failed to release optimization lock: group=%s, error=%s",
                group_name,
                release_exc,
            )
        # Close the cache connection
        try:
            await cache.close()
        except Exception:
            pass


async def _load_golden_dataset(group, session_factory) -> list[dict[str, Any]]:
    """Load golden dataset examples for all agents in the group.

    Returns list of dicts in GEPA format: {"inputs": {...}, "expected_output": "..."}.
    """
    from sqlalchemy import select

    from app.models.golden_dataset import GoldenDataset

    agent_codes = list(group.agent_codes)

    async with session_factory() as session:
        stmt = (
            select(GoldenDataset)
            .where(GoldenDataset.agent_code.in_(agent_codes))
            .where(GoldenDataset.active.is_(True))
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    train_data = []
    for row in rows:
        entry = {"inputs": row.input_context or {}}
        if row.expected_output:
            entry["expected_output"] = row.expected_output
        train_data.append(entry)

    logger.info(
        "Loaded %d golden examples for agents %s",
        len(train_data),
        agent_codes,
    )
    return train_data
