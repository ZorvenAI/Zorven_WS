"""Canary deployment manager (§3.3, §18.2).

Routes 10% of agent invocations to a candidate prompt for 24 hours.
Auto-rollbacks on >5% scorer regression. Covers all 15 agents.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Canary parameters — configurable via POI_* env vars
CANARY_TRAFFIC_PCT = settings.CANARY_TRAFFIC_PCT
CANARY_DURATION_HOURS = settings.CANARY_DURATION_HOURS

# Redis key templates
CANARY_STATE_KEY = "prompt:canary:{name}"
CANARY_METRICS_KEY = "prompt:metrics:{name}:v{version}"
CANARY_HISTORY_KEY = "prompt:canary_history:{name}:v{version}"


def is_canary_request(tenant_id: str, canary_pct: float = CANARY_TRAFFIC_PCT) -> bool:
    """Determine if a request should be routed to the canary prompt.

    Deterministic via stable hash of tenant_id (AC-1). Same tenant
    always gets the same routing decision for a given canary_pct.

    Args:
        tenant_id: Tenant identifier.
        canary_pct: Fraction of traffic to route to canary (default 10%).

    Returns:
        True if request should use the canary prompt.
    """
    if not tenant_id:
        return False
    # Use SHA-256 for deterministic, uniform distribution (not Python hash())
    digest = hashlib.sha256(tenant_id.encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < int(canary_pct * 100)


@dataclass
class CanaryState:
    """State of an active canary deployment."""

    prompt_name: str
    canary_version: int
    production_version: int
    started_at: datetime
    expires_at: datetime
    agent_code: str
    active: bool = True


class CanaryManager:
    """Manages canary deployments for prompt optimization.

    Stores canary state and metrics in Redis (DB 2) with PostgreSQL
    persistence for canary history.
    """

    def __init__(self, prompt_cache, lifecycle_manager=None, db_session_factory=None) -> None:
        self.prompt_cache = prompt_cache
        self.lifecycle_manager = lifecycle_manager
        self.db_session_factory = db_session_factory

    async def start_canary(
        self,
        prompt_name: str,
        canary_version: int,
        production_version: int,
        agent_code: str,
    ) -> CanaryState:
        """Start a 24-hour canary deployment.

        Args:
            prompt_name: Prompt being canary-tested.
            canary_version: New candidate version.
            production_version: Current production version.
            agent_code: Agent code (covers all 15, AC-4).

        Returns:
            CanaryState with start/expiry times.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=CANARY_DURATION_HOURS)

        state = CanaryState(
            prompt_name=prompt_name,
            canary_version=canary_version,
            production_version=production_version,
            started_at=now,
            expires_at=expires_at,
            agent_code=agent_code,
            active=True,
        )

        r = await self.prompt_cache.connect()
        key = CANARY_STATE_KEY.format(name=prompt_name)
        state_data = {
            "prompt_name": prompt_name,
            "canary_version": str(canary_version),
            "production_version": str(production_version),
            "started_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "agent_code": agent_code,
            "active": "true",
        }
        await r.hset(key, mapping=state_data)
        # The Redis key must outlive the canary duration so the health check
        # (every 15 min) can discover, evaluate, and promote/rollback before
        # Redis evicts the key. Add a 2-hour buffer beyond the canary window.
        # When duration=0 (testing), this guarantees at least 2h for the
        # health check to process the immediately-expired canary.
        ttl = CANARY_DURATION_HOURS * 3600 + 7200
        await r.expire(key, ttl)

        logger.info(
            "Canary started: %s v%d (production v%d) for %s, expires %s",
            prompt_name,
            canary_version,
            production_version,
            agent_code,
            expires_at.isoformat(),
        )
        return state

    async def get_canary_state(self, prompt_name: str) -> Optional[CanaryState]:
        """Get active canary state, or None if expired/not found."""
        r = await self.prompt_cache.connect()
        key = CANARY_STATE_KEY.format(name=prompt_name)
        data = await r.hgetall(key)

        if not data:
            return None

        return CanaryState(
            prompt_name=data.get("prompt_name", prompt_name),
            canary_version=int(data.get("canary_version", 0)),
            production_version=int(data.get("production_version", 0)),
            started_at=datetime.fromisoformat(data["started_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            agent_code=data.get("agent_code", ""),
            active=data.get("active", "true") == "true",
        )

    async def record_canary_metric(
        self,
        prompt_name: str,
        version: int,
        scorer_name: str,
        score: float,
    ) -> None:
        """Record a scorer metric for a canary or production version (AC-5).

        Stored in prompt:metrics:<name>:v<version> with 30-day TTL.
        """
        r = await self.prompt_cache.connect()
        key = CANARY_METRICS_KEY.format(name=prompt_name, version=version)
        await r.hset(key, scorer_name, str(score))
        ttl_seconds = settings.CANARY_METRICS_TTL_DAYS * 86400
        await r.expire(key, ttl_seconds)

    async def get_canary_metrics(
        self, prompt_name: str, version: int
    ) -> dict[str, float]:
        """Get all scorer metrics for a version."""
        r = await self.prompt_cache.connect()
        key = CANARY_METRICS_KEY.format(name=prompt_name, version=version)
        data = await r.hgetall(key)
        return {k: float(v) for k, v in data.items()}

    async def check_canary_regression(self, prompt_name: str) -> Optional[float]:
        """Check if canary version has regressed vs production (AC-3).

        Returns regression percentage if > 5%, None otherwise.
        """
        state = await self.get_canary_state(prompt_name)
        if state is None:
            return None

        canary_metrics = await self.get_canary_metrics(
            prompt_name, state.canary_version
        )
        prod_metrics = await self.get_canary_metrics(
            prompt_name, state.production_version
        )

        if not canary_metrics or not prod_metrics:
            return None

        # Compute aggregate regression
        common = set(canary_metrics.keys()) & set(prod_metrics.keys())
        if not common:
            return None

        canary_agg = sum(canary_metrics[k] for k in common) / len(common)
        prod_agg = sum(prod_metrics[k] for k in common) / len(common)

        if prod_agg <= 0:
            return None

        regression = (prod_agg - canary_agg) / prod_agg
        threshold = settings.CANARY_REGRESSION_THRESHOLD

        if regression > threshold:
            logger.error(
                "ADMIN ALERT: Canary regression detected for %s: "
                "%.2f%% > %.2f%% threshold. Triggering auto-rollback.",
                prompt_name,
                regression * 100,
                threshold * 100,
            )
            await self.rollback_canary(prompt_name)
            return regression

        return None

    async def rollback_canary(self, prompt_name: str) -> bool:
        """Roll back a canary deployment (AC-3).

        Transitions the prompt version to ROLLED_BACK via the lifecycle
        manager, clears canary state from Redis, records outcome, and
        logs ADMIN alert.
        """
        state = await self.get_canary_state(prompt_name)
        if state is None:
            return False

        # Transition prompt lifecycle to ROLLED_BACK
        try:
            from app.logic.lifecycle import PromptState

            if self.lifecycle_manager is not None:
                self.lifecycle_manager.rollback(
                    prompt_name,
                    state.canary_version,
                    PromptState.CANARY,
                )
            else:
                logger.warning(
                    "No lifecycle_manager — skipping state transition for %s",
                    prompt_name,
                )
        except Exception as exc:
            logger.error(
                "Failed to transition %s v%d to ROLLED_BACK: %s",
                prompt_name,
                state.canary_version,
                exc,
            )

        # Compute final regression for history
        regression = await self._compute_regression(state)

        # Record outcome in history
        await self._record_canary_outcome(state, "rolled_back", regression)

        # Clear canary state from Redis
        r = await self.prompt_cache.connect()
        key = CANARY_STATE_KEY.format(name=prompt_name)
        await r.delete(key)

        logger.error(
            "ADMIN ALERT: Canary ROLLED_BACK for %s v%d "
            "(reverted to production v%d)",
            prompt_name,
            state.canary_version,
            state.production_version,
        )
        return True

    async def promote_canary(self, prompt_name: str) -> bool:
        """Promote a canary to PRODUCTION after successful evaluation.

        Called when a canary expires with healthy metrics or is manually
        promoted. Records outcome in history.
        """
        state = await self.get_canary_state(prompt_name)
        if state is None:
            return False

        try:
            if self.lifecycle_manager is not None:
                self.lifecycle_manager.promote_to_production(
                    prompt_name, state.canary_version
                )
            else:
                logger.warning(
                    "No lifecycle_manager — skipping promotion for %s", prompt_name
                )
        except Exception as exc:
            logger.error(
                "Failed to promote canary %s v%d: %s",
                prompt_name,
                state.canary_version,
                exc,
            )
            return False

        regression = await self._compute_regression(state)
        await self._record_canary_outcome(state, "promoted", regression)

        # Clear canary state
        r = await self.prompt_cache.connect()
        key = CANARY_STATE_KEY.format(name=prompt_name)
        await r.delete(key)

        logger.info(
            "Canary promoted: %s v%d → PRODUCTION",
            prompt_name,
            state.canary_version,
        )
        return True

    async def _compute_regression(self, state: CanaryState) -> Optional[float]:
        """Compute regression percentage for a canary vs production."""
        canary_metrics = await self.get_canary_metrics(
            state.prompt_name, state.canary_version
        )
        prod_metrics = await self.get_canary_metrics(
            state.prompt_name, state.production_version
        )
        if not canary_metrics or not prod_metrics:
            return None
        common = set(canary_metrics.keys()) & set(prod_metrics.keys())
        if not common:
            return None
        canary_agg = sum(canary_metrics[k] for k in common) / len(common)
        prod_agg = sum(prod_metrics[k] for k in common) / len(common)
        if prod_agg <= 0:
            return None
        return (prod_agg - canary_agg) / prod_agg

    async def _record_canary_outcome(
        self,
        state: CanaryState,
        outcome: str,
        regression_pct: Optional[float],
    ) -> None:
        """Record canary outcome in Redis (30-day TTL) and PostgreSQL."""
        r = await self.prompt_cache.connect()
        now = datetime.now(timezone.utc)
        key = CANARY_HISTORY_KEY.format(
            name=state.prompt_name, version=state.canary_version
        )
        data = {
            "prompt_name": state.prompt_name,
            "canary_version": str(state.canary_version),
            "production_version": str(state.production_version),
            "agent_code": state.agent_code,
            "started_at": state.started_at.isoformat(),
            "ended_at": now.isoformat(),
            "outcome": outcome,
            "final_regression_pct": (
                str(regression_pct) if regression_pct is not None else ""
            ),
        }
        await r.hset(key, mapping=data)
        await r.expire(key, settings.CANARY_METRICS_TTL_DAYS * 86400)

        # Persist to PostgreSQL for long-term storage
        if self.db_session_factory is not None:
            try:
                from app.models.canary_history import CanaryHistory

                async with self.db_session_factory() as session:
                    record = CanaryHistory(
                        prompt_name=state.prompt_name,
                        canary_version=state.canary_version,
                        production_version=state.production_version,
                        agent_code=state.agent_code,
                        started_at=state.started_at,
                        ended_at=now,
                        outcome=outcome,
                        final_regression_pct=regression_pct,
                    )
                    session.add(record)
                    await session.commit()
            except Exception as exc:
                logger.warning("Failed to persist canary history to DB: %s", exc)

    async def list_active_canaries(self) -> list[CanaryState]:
        """Scan Redis for all active canary deployments."""
        r = await self.prompt_cache.connect()
        canaries = []
        async for key in r.scan_iter(match="prompt:canary:*"):
            data = await r.hgetall(key)
            if not data or data.get("active") != "true":
                continue
            try:
                canaries.append(
                    CanaryState(
                        prompt_name=data.get("prompt_name", ""),
                        canary_version=int(data.get("canary_version", 0)),
                        production_version=int(data.get("production_version", 0)),
                        started_at=datetime.fromisoformat(data["started_at"]),
                        expires_at=datetime.fromisoformat(data["expires_at"]),
                        agent_code=data.get("agent_code", ""),
                        active=True,
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed canary key %s: %s", key, exc)
        return canaries

    async def get_canary_comparison(self, prompt_name: str) -> Optional[dict]:
        """Fetch metrics for canary and production, compute regression."""
        state = await self.get_canary_state(prompt_name)
        if state is None:
            return None

        canary_metrics = await self.get_canary_metrics(
            prompt_name, state.canary_version
        )
        prod_metrics = await self.get_canary_metrics(
            prompt_name, state.production_version
        )

        regression_pct = await self._compute_regression(state)

        if regression_pct is not None:
            if regression_pct > 0.05:
                status = "regressed"
            elif regression_pct > 0.03:
                status = "warning"
            else:
                status = "healthy"
        else:
            status = "healthy"

        return {
            "prompt_name": prompt_name,
            "canary_version": state.canary_version,
            "production_version": state.production_version,
            "canary_metrics": canary_metrics,
            "production_metrics": prod_metrics,
            "regression_pct": regression_pct,
            "status": status,
        }

    async def list_canary_history(self, days: int = 30) -> list[dict]:
        """Retrieve recent canary outcomes from Redis."""
        r = await self.prompt_cache.connect()
        history = []
        async for key in r.scan_iter(match="prompt:canary_history:*"):
            data = await r.hgetall(key)
            if not data:
                continue
            try:
                reg_pct_str = data.get("final_regression_pct", "")
                history.append(
                    {
                        "prompt_name": data.get("prompt_name", ""),
                        "canary_version": int(data.get("canary_version", 0)),
                        "started_at": data.get("started_at", ""),
                        "ended_at": data.get("ended_at", ""),
                        "outcome": data.get("outcome", ""),
                        "final_regression_pct": (
                            float(reg_pct_str) if reg_pct_str else None
                        ),
                    }
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed history key %s: %s", key, exc)
        # Sort by ended_at descending
        history.sort(key=lambda h: h.get("ended_at", ""), reverse=True)
        return history
