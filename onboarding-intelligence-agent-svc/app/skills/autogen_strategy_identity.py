"""SKL-OIA-12 — Auto-generate strategy and identity drafts from the confirmed
onboarding profile.

Design §8.2 · implemented by story J-06.

The PROCESS pipeline calls ``ProcessExecutor._auto_generate`` directly; this
skill provides the standalone invocation path through the SkillRegistry for
LIVE/EDITOR use where the IG → RBAC → PG → OG chain must run.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services.backend_client import BackendClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

logger = get_logger(__name__)


class AutogenStrategyIdentity(BaseSkill):
    """Auto-generate strategy and identity drafts from the confirmed onboarding
    profile."""

    def __init__(
        self,
        meta: Any,
        *,
        backend: BackendClient | None = None,
    ) -> None:
        super().__init__(meta)
        self._backend = backend

    async def run(self, context: SkillContext) -> SkillResult:
        company_id = context.input_context.get("company_id")
        tenant_id = context.tenant_context.tenant_id

        if company_id is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                output={"generated": [], "reason": "no_company_id"},
            )

        if self._backend is None or not self._backend.configured:
            return SkillResult(
                skill_id=self.meta.skill_id,
                output={"generated": [], "reason": "backend_not_configured"},
            )

        generated: list[str] = []
        auto_strategy = context.input_context.get("auto_generate_strategy", True)
        auto_identity = context.input_context.get("auto_generate_identity", True)

        if auto_strategy:
            try:
                result = await self._backend.generate_brand_strategy(
                    tenant_id=tenant_id, company_id=company_id
                )
                if result is not None:
                    generated.append("brand_strategy")
            except Exception as exc:
                logger.warning(
                    "skl_oia_12_strategy_failed",
                    error=f"{type(exc).__name__}: {exc}",
                )

        if auto_identity:
            try:
                result = await self._backend.generate_brand_identity(
                    tenant_id=tenant_id, company_id=company_id
                )
                if result is not None:
                    generated.append("brand_identity")
            except Exception as exc:
                logger.warning(
                    "skl_oia_12_identity_failed",
                    error=f"{type(exc).__name__}: {exc}",
                )

        return SkillResult(
            skill_id=self.meta.skill_id,
            output={
                "generated": generated,
                "strategy_ref": (
                    {"type": "company_fields"}
                    if "brand_strategy" in generated
                    else None
                ),
                "identity_ref": (
                    {"type": "company_fields"}
                    if "brand_identity" in generated
                    else None
                ),
            },
        )
