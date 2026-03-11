"""Worker executor — wires persona, skills, and PAOR engine together."""

import logging
from typing import Any, Optional

from app.agent.engine import AgentEngine
from app.api.schemas import ExecuteRequest, ExecuteResponse
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.personas.resolver import PersonaResolver
from app.skills.router import SkillRouter

logger = logging.getLogger(__name__)


class WorkerExecutor:
    """Orchestrates persona resolution, skill loading, and PAOR execution."""

    def __init__(
        self,
        persona_resolver: PersonaResolver,
        skill_router: SkillRouter,
        agent_engine: AgentEngine,
        redis_manager: Optional[RedisManager] = None,
        trace_producer: Optional[Any] = None,
    ) -> None:
        self._persona_resolver = persona_resolver
        self._skill_router = skill_router
        self._agent_engine = agent_engine
        self._redis = redis_manager
        self._trace_producer = trace_producer

    async def execute(self, request: ExecuteRequest, tenant_id: str) -> ExecuteResponse:
        """Execute an Odoo operation via persona-driven PAOR loop."""
        prompt = request.input_prompt
        context = {
            **request.input_context,
            **request.tenant_context,
            "skill_context": request.config.get("skill_context", ""),
            "user_roles": request.tenant_context.get("user_roles", []),
            "persona_hint": request.config.get("persona_hint", ""),
        }

        # 1. Rate limit check
        if self._redis:
            allowed = await self._redis.check_rate_limit(
                tenant_id, limit=settings.RATE_LIMIT_PER_MINUTE
            )
            if not allowed:
                return ExecuteResponse(
                    status="error",
                    error="Rate limit exceeded. Please try again later.",
                )

        try:
            # 2. Resolve persona
            persona = await self._persona_resolver.resolve(prompt, context)
            logger.info(
                "Resolved persona: %s for tenant: %s",
                persona.name,
                tenant_id,
            )

            # 3. Resolve worker-level skills
            skill_data = self._skill_router.resolve_skills_for_persona(
                persona_name=persona.name,
                prompt=prompt,
            )
            worker_skill_context = skill_data.get("worker_skill_context", "")

            # 4. Use sub_task as effective prompt if provided by orchestrator
            effective_prompt = request.config.get("sub_task", "") or prompt

            # 5. Run PAOR loop
            result = await self._agent_engine.execute(
                prompt=effective_prompt,
                persona=persona,
                skill_context=worker_skill_context,
                tenant_id=tenant_id,
                context=context,
            )

            # 6. Collect tool results data from reasoning steps
            tool_results_data: list[dict] = []
            for step in result.reasoning_steps:
                for tr in step.tool_results:
                    if tr.data:
                        tool_results_data.append(
                            {
                                "tool_name": tr.tool_name,
                                "data": tr.data,
                            }
                        )

            # 7. Build response
            return ExecuteResponse(
                status="success" if result.success else "error",
                findings=result.findings,
                recommendations=result.recommendations,
                data={
                    "final_answer": result.final_answer,
                    "tool_results": tool_results_data,
                    "reasoning_steps": [
                        {
                            "step": s.step_number,
                            "phase": s.phase,
                            "thought": s.thought,
                            "reflection": s.reflection,
                        }
                        for s in result.reasoning_steps
                    ],
                },
                result_data={
                    "persona": persona.name,
                    "tools_called": result.tools_called,
                    "total_steps": result.total_steps,
                },
                error=result.error,
                persona_used=result.persona_used,
                tools_called=result.tools_called,
                reasoning_steps=result.total_steps,
            )

        except Exception as exc:
            logger.error("Worker execution failed: %s", exc, exc_info=True)
            return ExecuteResponse(
                status="error",
                error=f"Worker execution failed: {exc}",
            )

    async def close(self) -> None:
        """Cleanup resources."""
        pass
