"""Gemini integration for the PAOR reasoning loop."""

import json
import logging
from typing import Any, Optional

from app.agent.models import PlanOutput, ReflectionOutput, ToolCall
from app.prompts.fallbacks import (
    FALLBACK_PLAN_INSTRUCTIONS,
    FALLBACK_REFLECT_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper around Google Generative AI for plan/reflect/classify."""

    def __init__(
        self,
        model_name: str = "gemini-2.0-flash",
        max_tool_calls_per_step: int = 5,
        prompt_loader: Optional[Any] = None,
    ) -> None:
        self._model_name = model_name
        self._max_tool_calls_per_step = max_tool_calls_per_step
        self._model = None
        self._prompt_loader = prompt_loader

    def _get_model(self) -> Any:
        """Lazy-load the Gemini model."""
        if self._model is None:
            import google.generativeai as genai

            self._model = genai.GenerativeModel(self._model_name)
        return self._model

    async def plan(
        self,
        prompt: str,
        persona_prompt: str,
        skill_context: str,
        observation_history: str,
        available_tools: list[dict[str, Any]],
    ) -> PlanOutput:
        """Generate an action plan using Gemini.

        Returns tool calls to execute or a final answer if the task is complete.
        """
        system_prompt = await self._build_plan_prompt(
            persona_prompt=persona_prompt,
            skill_context=skill_context,
            observation_history=observation_history,
            available_tools=available_tools,
        )

        try:
            model = self._get_model()
            response = await model.generate_content_async(
                [system_prompt, prompt],
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            )

            return self._parse_plan_response(response.text)

        except Exception as exc:
            logger.error("Gemini plan generation failed: %s", exc)
            return PlanOutput(
                thought=f"Planning failed: {exc}",
                is_complete=True,
                final_answer=f"I encountered an error while planning: {exc}",
            )

    async def reflect(
        self,
        original_prompt: str,
        plan_thought: str,
        observations: list[dict[str, Any]],
        persona_prompt: str,
    ) -> ReflectionOutput:
        """Evaluate results and decide: done or re-plan."""
        system_prompt = await self._build_reflect_prompt(
            persona_prompt=persona_prompt,
            plan_thought=plan_thought,
            observations=observations,
        )

        try:
            model = self._get_model()
            response = await model.generate_content_async(
                [system_prompt, original_prompt],
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            )

            return self._parse_reflect_response(response.text)

        except Exception as exc:
            logger.error("Gemini reflection failed: %s", exc)
            return ReflectionOutput(
                reflection=f"Reflection failed: {exc}",
                is_complete=True,
                final_answer="I completed the available actions but "
                "could not fully evaluate the results.",
            )

    async def classify_persona(
        self,
        prompt: str,
        persona_options: list[dict[str, Any]],
    ) -> Optional[str]:
        """Use Gemini to classify which persona best fits the prompt."""
        options_text = "\n".join(
            f"- {p['name']}: {p['description']} (domains: {', '.join(p['domains'])})"
            for p in persona_options
        )

        system_prompt = (
            "You are a persona classifier. Given a user prompt about Odoo ERP "
            "operations, select the single best-matching persona.\n\n"
            f"Available personas:\n{options_text}\n\n"
            "Respond with ONLY a JSON object: "
            '{"persona": "<persona_name>"}'
        )

        try:
            model = self._get_model()
            response = await model.generate_content_async(
                [system_prompt, f"User prompt: {prompt}"],
                generation_config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                },
            )

            data = json.loads(response.text)
            return data.get("persona")

        except Exception as exc:
            logger.warning("Gemini persona classification failed: %s", exc)
            return None

    async def _build_plan_prompt(
        self,
        persona_prompt: str,
        skill_context: str,
        observation_history: str,
        available_tools: list[dict[str, Any]],
    ) -> str:
        """Build the system prompt for the PLAN phase."""
        tools_desc = "\n".join(
            f"- {t['name']}: {t.get('description', 'No description')}"
            for t in available_tools
        )

        # Load static plan instructions from prompt-optimization-svc
        plan_instructions = FALLBACK_PLAN_INSTRUCTIONS
        if self._prompt_loader:
            plan_instructions = await self._prompt_loader.load(
                name="zorven-odoo-worker-plan",
                fallback=FALLBACK_PLAN_INSTRUCTIONS,
            )

        parts = [
            persona_prompt,
            "",
            "## Available MCP Tools",
            tools_desc if tools_desc else "No tools available.",
            "",
        ]

        if skill_context:
            parts.extend([skill_context, ""])

        if observation_history:
            parts.extend(["## Previous Observations", observation_history, ""])

        parts.extend(
            [
                plan_instructions,
                f"Maximum {self._max_tool_calls_per_step} tool calls per step.",
            ]
        )

        return "\n".join(parts)

    async def _build_reflect_prompt(
        self,
        persona_prompt: str,
        plan_thought: str,
        observations: list[dict[str, Any]],
    ) -> str:
        """Build the system prompt for the REFLECT phase."""
        obs_text = json.dumps(observations, indent=2, default=str)

        # Load static reflect instructions from prompt-optimization-svc
        reflect_instructions = FALLBACK_REFLECT_INSTRUCTIONS
        if self._prompt_loader:
            reflect_instructions = await self._prompt_loader.load(
                name="zorven-odoo-worker-reflect",
                fallback=FALLBACK_REFLECT_INSTRUCTIONS,
            )

        return (
            f"{persona_prompt}\n\n"
            f"## Plan\n{plan_thought}\n\n"
            f"## Tool Results\n{obs_text}\n\n"
            f"{reflect_instructions}"
        )

    def _parse_plan_response(self, text: str) -> PlanOutput:
        """Parse Gemini's plan response into a PlanOutput."""
        try:
            data = json.loads(text)
            tool_calls = [ToolCall(**tc) for tc in data.get("tool_calls", [])]
            return PlanOutput(
                thought=data.get("thought", ""),
                tool_calls=tool_calls[: self._max_tool_calls_per_step],
                is_complete=data.get("is_complete", False),
                final_answer=data.get("final_answer", ""),
            )
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to parse plan response: %s", exc)
            return PlanOutput(
                thought=text[:500],
                is_complete=True,
                final_answer=text[:1000],
            )

    def _parse_reflect_response(self, text: str) -> ReflectionOutput:
        """Parse Gemini's reflection response into a ReflectionOutput."""
        try:
            data = json.loads(text)
            next_actions = [ToolCall(**tc) for tc in data.get("next_actions", [])]
            return ReflectionOutput(
                reflection=data.get("reflection", ""),
                is_complete=data.get("is_complete", True),
                final_answer=data.get("final_answer", ""),
                next_actions=next_actions,
            )
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to parse reflect response: %s", exc)
            return ReflectionOutput(
                reflection=text[:500],
                is_complete=True,
                final_answer=text[:1000],
            )
