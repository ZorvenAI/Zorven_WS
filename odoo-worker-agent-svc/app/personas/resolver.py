"""Persona resolver — two-tier resolution from prompt to persona."""

import logging
from typing import Optional

from app.personas.models import PersonaDefinition

logger = logging.getLogger(__name__)


class PersonaResolver:
    """Resolves the best persona for a given prompt.

    Tier 1: Gemini function-calling classification (if available).
    Tier 2: Keyword matching against persona triggers (fallback).
    Default: general_assistant.
    """

    def __init__(
        self,
        personas: dict[str, PersonaDefinition],
        gemini_client: Optional[object] = None,
    ) -> None:
        self._personas = personas
        self._gemini_client = gemini_client

    @property
    def persona_count(self) -> int:
        return len(self._personas)

    def get_persona(self, name: str) -> Optional[PersonaDefinition]:
        """Get a persona by name."""
        return self._personas.get(name)

    async def resolve(
        self, prompt: str, context: Optional[dict] = None
    ) -> PersonaDefinition:
        """Resolve the best persona for the given prompt.

        Resolution tiers:
          Tier 0: Explicit persona_hint from orchestrator config (instant).
          Tier 1: Gemini function-calling classification.
          Tier 2: Keyword matching against persona triggers.
          Default: general_assistant.
        """
        # Tier 0: Explicit persona_hint from orchestrator config
        if context and context.get("persona_hint"):
            hint = context["persona_hint"]
            if hint in self._personas:
                logger.info("Persona resolved via hint: %s", hint)
                return self._personas[hint]
            logger.warning("persona_hint '%s' not found, falling through", hint)

        # Tier 1: Gemini classification
        if self._gemini_client is not None:
            try:
                persona = await self._resolve_via_gemini(prompt, context)
                if persona:
                    logger.info("Gemini resolved persona: %s", persona.name)
                    return persona
            except Exception as exc:
                logger.warning("Gemini persona resolution failed: %s", exc)

        # Tier 2: Keyword matching
        persona = self._resolve_via_keywords(prompt)
        if persona:
            logger.info("Keyword resolved persona: %s", persona.name)
            return persona

        # Default fallback
        fallback = self._personas.get("general_assistant")
        if fallback:
            logger.info("Falling back to general_assistant persona")
            return fallback

        # Ultimate fallback if no personas loaded
        logger.warning("No personas loaded, returning synthetic fallback")
        return PersonaDefinition(
            name="general_assistant",
            display_name="General Assistant",
            description="General-purpose Odoo assistant",
            domains=["generic"],
            triggers=[],
        )

    async def _resolve_via_gemini(
        self, prompt: str, context: Optional[dict] = None
    ) -> Optional[PersonaDefinition]:
        """Use Gemini function-calling to classify the prompt."""
        from app.agent.llm import GeminiClient

        if not isinstance(self._gemini_client, GeminiClient):
            return None

        persona_options = [
            {"name": p.name, "description": p.description, "domains": p.domains}
            for p in self._personas.values()
        ]

        selected_name = await self._gemini_client.classify_persona(
            prompt=prompt,
            persona_options=persona_options,
        )

        if selected_name and selected_name in self._personas:
            return self._personas[selected_name]

        return None

    def _resolve_via_keywords(self, prompt: str) -> Optional[PersonaDefinition]:
        """Match persona based on trigger keywords in the prompt."""
        prompt_lower = prompt.lower()
        matches: list[tuple[int, int, PersonaDefinition]] = []

        for persona in self._personas.values():
            trigger_count = sum(
                1 for trigger in persona.triggers if trigger.lower() in prompt_lower
            )
            if trigger_count > 0:
                matches.append((trigger_count, persona.priority, persona))

        if not matches:
            return None

        # Sort by trigger count (desc), then priority (desc)
        matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
        return matches[0][2]
