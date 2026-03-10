"""PAOR reasoning engine — Plan, Act, Observe, Reflect."""

import json
import logging
from typing import Any, Optional

from app.agent.llm import GeminiClient
from app.agent.models import (
    AgentResult,
    ReasoningStep,
    ToolCall,
    ToolResult,
)
from app.personas.models import PersonaDefinition
from app.rbac.preflight import RBACPreflight
from app.rag.client import RAGClient
from app.services.mcp_client import MCPClient

logger = logging.getLogger(__name__)


class AgentEngine:
    """PAOR reasoning loop using Gemini 2.0 Flash.

    Executes a Plan → Act → Observe → Reflect cycle:
    1. PLAN: Gemini analyzes prompt + persona + skills → action plan
    2. ACT: Execute MCP tool calls from the plan
    3. OBSERVE: Collect and structure tool results
    4. REFLECT: Gemini evaluates results → done or loop back to PLAN
    """

    def __init__(
        self,
        gemini_client: Optional[GeminiClient],
        mcp_client: MCPClient,
        rbac_preflight: Optional[RBACPreflight] = None,
        rag_client: Optional[RAGClient] = None,
        max_steps: int = 10,
        trace_producer: Optional[Any] = None,
        audit_producer: Optional[Any] = None,
    ) -> None:
        self._gemini = gemini_client
        self._mcp = mcp_client
        self._rbac = rbac_preflight
        self._rag = rag_client
        self._max_steps = max_steps
        self._trace_producer = trace_producer
        self._audit_producer = audit_producer

    async def execute(
        self,
        prompt: str,
        persona: PersonaDefinition,
        skill_context: str,
        tenant_id: str,
        context: dict[str, Any],
    ) -> AgentResult:
        """Execute the full PAOR reasoning loop."""
        tools_called: list[str] = []
        reasoning_steps: list[ReasoningStep] = []
        observation_history = ""
        failed_tools: dict[str, int] = {}  # tool_name → failure count

        # Enrich context with RAG if available
        rag_context = ""
        if self._rag and self._rag.enabled:
            rag_context = await self._rag.get_context(
                query=prompt,
                tenant_id=tenant_id,
                data_store_id=context.get("rag_data_store_id", ""),
            )
            if rag_context:
                skill_context = f"{skill_context}\n\n## RAG Context\n{rag_context}"

        # Stub mode when no Gemini client
        if self._gemini is None:
            return self._stub_result(prompt, persona)

        # Merge orchestrator skill_context with worker skill_context
        orchestrator_skills = context.get("skill_context", "")
        combined_skill_context = orchestrator_skills
        if skill_context:
            combined_skill_context = f"{combined_skill_context}\n\n{skill_context}"

        # Get available tools description
        available_tools = await self._get_available_tools(tenant_id)

        for step_num in range(1, self._max_steps + 1):
            # --- PLAN ---
            await self._emit_trace(
                tenant_id, "plan", step_num, "Planning next action..."
            )

            plan = await self._gemini.plan(
                prompt=prompt,
                persona_prompt=persona.system_prompt,
                skill_context=combined_skill_context,
                observation_history=observation_history,
                available_tools=available_tools,
            )

            plan_step = ReasoningStep(
                step_number=step_num,
                phase="plan",
                thought=plan.thought,
                tool_calls=plan.tool_calls,
            )

            # Check if planning says we're done
            if plan.is_complete:
                plan_step.reflection = plan.final_answer
                reasoning_steps.append(plan_step)
                return AgentResult(
                    persona_used=persona.name,
                    reasoning_steps=reasoning_steps,
                    final_answer=plan.final_answer,
                    findings=self._extract_findings(plan.final_answer),
                    recommendations=[],
                    tools_called=tools_called,
                    total_steps=step_num,
                    success=True,
                )

            reasoning_steps.append(plan_step)

            # --- ACT ---
            if not plan.tool_calls:
                # Gemini returned no tool calls but didn't declare complete.
                # Return an explicit error rather than falling through to the
                # misleading "max steps reached" message.
                return AgentResult(
                    persona_used=persona.name,
                    reasoning_steps=reasoning_steps,
                    final_answer="I was unable to determine which tools to call "
                    "for this request. Please try rephrasing your prompt.",
                    findings=[f"Plan thought: {plan.thought}"],
                    recommendations=[
                        "Try a more specific request",
                        "Ensure the relevant Odoo modules are installed",
                    ],
                    tools_called=tools_called,
                    total_steps=step_num,
                    success=False,
                    error="No tool calls planned",
                )

            await self._emit_trace(
                tenant_id,
                "act",
                step_num,
                f"Executing {len(plan.tool_calls)} tool call(s)...",
            )

            act_results: list[ToolResult] = []
            for tc in plan.tool_calls:
                # Block retries after first failure — matches the LLM prompt
                # instruction "If a tool call FAILED, do NOT retry it."
                if failed_tools.get(tc.tool_name, 0) >= 1:
                    act_results.append(
                        ToolResult(
                            tool_name=tc.tool_name,
                            success=False,
                            error=f"Skipped: {tc.tool_name} already failed "
                            f"— retries are blocked per policy",
                        )
                    )
                    continue

                # RBAC pre-flight check
                if self._rbac and not await self._rbac.check(
                    tool_name=tc.tool_name,
                    tenant_id=tenant_id,
                    user_roles=context.get("user_roles", []),
                ):
                    act_results.append(
                        ToolResult(
                            tool_name=tc.tool_name,
                            success=False,
                            error=f"RBAC denied: insufficient permissions "
                            f"for {tc.tool_name}",
                        )
                    )
                    continue

                # Execute MCP tool call
                response = await self._mcp.call_tool(
                    tool_name=tc.tool_name,
                    arguments=tc.arguments,
                    tenant_id=tenant_id,
                )
                result = ToolResult(
                    tool_name=tc.tool_name,
                    success=response.success,
                    data=response.data,
                    error=response.error,
                )
                act_results.append(result)
                tools_called.append(tc.tool_name)

                # Track failures for retry prevention
                if not result.success:
                    failed_tools[tc.tool_name] = failed_tools.get(tc.tool_name, 0) + 1

                # Emit audit event
                await self._emit_audit(
                    tenant_id, tc.tool_name, tc.arguments, response.success
                )

            # --- OBSERVE ---
            act_step = ReasoningStep(
                step_number=step_num,
                phase="act",
                tool_calls=plan.tool_calls,
                tool_results=act_results,
            )
            reasoning_steps.append(act_step)

            # Build observation history for next iteration
            obs = [
                {
                    "tool": r.tool_name,
                    "success": r.success,
                    "data": r.data,
                    "error": r.error,
                }
                for r in act_results
            ]
            observation_history += (
                f"\n### Step {step_num} Results\n"
                f"{json.dumps(obs, indent=2, default=str)}\n"
            )
            if failed_tools:
                observation_history += (
                    f"\n### BLOCKED TOOLS (do NOT retry): "
                    f"{', '.join(f'{k} (failed {v}x)' for k, v in failed_tools.items())}\n"
                )

            # --- REFLECT ---
            await self._emit_trace(
                tenant_id, "reflect", step_num, "Evaluating results..."
            )

            reflection = await self._gemini.reflect(
                original_prompt=prompt,
                plan_thought=plan.thought,
                observations=obs,
                persona_prompt=persona.system_prompt,
            )

            reflect_step = ReasoningStep(
                step_number=step_num,
                phase="reflect",
                reflection=reflection.reflection,
            )
            reasoning_steps.append(reflect_step)

            if reflection.is_complete:
                return AgentResult(
                    persona_used=persona.name,
                    reasoning_steps=reasoning_steps,
                    final_answer=reflection.final_answer,
                    findings=self._extract_findings(reflection.final_answer),
                    recommendations=[],
                    tools_called=tools_called,
                    total_steps=step_num,
                    success=True,
                )

            # If reflection suggests next actions, use them for next plan
            if reflection.next_actions:
                observation_history += (
                    f"\n### Reflection suggested actions: "
                    f"{[a.tool_name for a in reflection.next_actions]}\n"
                )

        # Max steps reached
        logger.warning("PAOR loop reached max steps (%d)", self._max_steps)
        return AgentResult(
            persona_used=persona.name,
            reasoning_steps=reasoning_steps,
            final_answer="Reached maximum reasoning steps. "
            "Partial results may be available.",
            findings=[f"Completed {len(tools_called)} tool calls"],
            recommendations=["Consider breaking this into smaller tasks"],
            tools_called=tools_called,
            total_steps=self._max_steps,
            success=False,
            error="Max reasoning steps reached",
        )

    async def _get_available_tools(self, tenant_id: str) -> list[dict[str, Any]]:
        """Get available MCP tools for the tenant."""
        try:
            tools = await self._mcp.list_tools(tenant_id)
            return tools
        except Exception:
            return []

    def _stub_result(self, prompt: str, persona: PersonaDefinition) -> AgentResult:
        """Return a stub result when Gemini is unavailable."""
        return AgentResult(
            persona_used=persona.name,
            reasoning_steps=[
                ReasoningStep(
                    step_number=1,
                    phase="plan",
                    thought=f"Stub mode: would process '{prompt[:100]}' "
                    f"as {persona.display_name}",
                )
            ],
            final_answer=f"Stub: {persona.display_name} received your request "
            f"'{prompt[:100]}'. Configure Gemini API key for full processing.",
            findings=[
                f"Persona resolved: {persona.display_name}",
                f"Domains: {', '.join(persona.domains)}",
            ],
            recommendations=["Set ODOO_WORKER_GOOGLE_API_KEY for full PAOR execution"],
            tools_called=[],
            total_steps=1,
            success=True,
        )

    @staticmethod
    def _extract_findings(text: str) -> list[str]:
        """Extract key findings from a final answer text."""
        if not text:
            return []
        # Split on newlines and take non-empty lines as findings
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        # Cap at 10 findings
        return lines[:10]

    async def _emit_trace(
        self, tenant_id: str, phase: str, step: int, message: str
    ) -> None:
        """Emit a trace event for real-time UI updates."""
        if self._trace_producer:
            try:
                await self._trace_producer.send_trace(
                    tenant_id=tenant_id,
                    phase=phase,
                    step=step,
                    message=message,
                )
            except Exception as exc:
                logger.debug("Failed to emit trace: %s", exc)

    async def _emit_audit(
        self,
        tenant_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
    ) -> None:
        """Emit an audit event for tool call tracking."""
        if self._audit_producer:
            try:
                await self._audit_producer.send_audit(
                    tenant_id=tenant_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    success=success,
                )
            except Exception as exc:
                logger.debug("Failed to emit audit: %s", exc)
