"""Reflection Context Enricher — inject skill metadata into GEPA reflection (US-055).

Generates a structured task_description from skill output_schema constraints
so the GEPA reflection model focuses on semantic quality rather than
rediscovering schema constraints through trial-and-error.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.registries.skill_definitions import SkillDefinition
from app.services.skill_registry_reader import SkillRegistryReader

logger = logging.getLogger(__name__)

_PREAMBLE = (
    "You are optimizing prompts for the following skills. The output MUST "
    "conform to these schema constraints \u2014 do not suggest changes that "
    "would violate them."
)

_FOOTER = (
    "Focus optimization on semantic quality, persuasiveness, and task accuracy.\n"
    "Schema compliance is already enforced by baseline scorers."
)


class ReflectionContextEnricher:
    """Enriches GEPA reflection context with skill metadata.

    Produces a task_description string for gepa_kwargs that tells the
    reflection model about the skill's output constraints, reducing
    wasted optimization cycles on schema discovery.
    """

    def __init__(self, skill_registry_reader: SkillRegistryReader) -> None:
        self._reader = skill_registry_reader

    def build_task_description(
        self,
        agent_code: str | list[str],
        prompt_names: list[str],
    ) -> str:
        """Build a task description from skill metadata for all prompts.

        Resolves each prompt to its skill, extracts output_schema constraints
        (field names, types, max_lengths, required flags, enum_values), and
        formats a structured context block.

        Args:
            agent_code: Single agent code or list of agent codes. When a list
                is provided, each prompt is resolved against every agent code,
                supporting joint optimization groups spanning multiple agents.
            prompt_names: Prompt names to resolve to skills.

        Returns empty string if no skills resolve.
        """
        agent_codes = [agent_code] if isinstance(agent_code, str) else list(agent_code)
        resolved: dict[str, SkillDefinition] = {}

        for prompt_name in prompt_names:
            for ac in agent_codes:
                skill = self._reader.get_skill_for_prompt(ac, prompt_name)
                if skill is not None and skill.skill_id not in resolved:
                    resolved[skill.skill_id] = skill
                    break

        if not resolved:
            return ""

        # Sort by skill_id for deterministic output
        skill_sections = [
            self._format_skill_context(resolved[sid]) for sid in sorted(resolved)
        ]

        parts = [_PREAMBLE, ""]
        parts.extend(skill_sections)
        parts.append(_FOOTER)
        return "\n".join(parts)

    def _format_skill_context(self, skill: SkillDefinition) -> str:
        """Format a single skill's metadata into reflection context."""
        lines = [f"### {skill.skill_id}: {skill.name}", "Output fields:"]

        for field in skill.output_schema:
            parts = [field.field, f"({field.type}"]
            if field.required:
                parts.append("required")
            else:
                parts.append("optional")
            if field.max_length is not None:
                parts.append(f"max_length={field.max_length}")
            if field.enum_values:
                parts.append(f"enum: {field.enum_values}")
            line = f"- {parts[0]} {', '.join(parts[1:])})"
            lines.append(line)

        lines.append("")
        return "\n".join(lines)

    def enrich_gepa_kwargs(
        self,
        agent_code: str | list[str],
        prompt_names: list[str],
        existing_kwargs: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Build gepa_kwargs dict with task_description from skill metadata.

        Merges with existing_kwargs if provided. Does not overwrite an
        existing task_description key. Returns existing_kwargs unchanged
        if no skills resolve or if task_description is already set.
        """
        merged = dict(existing_kwargs) if existing_kwargs else {}

        if "task_description" in merged:
            logger.debug(
                "task_description already set in gepa_kwargs — "
                "skipping enrichment for agent=%s",
                agent_code,
            )
            return merged

        description = self.build_task_description(agent_code, prompt_names)
        if not description:
            return merged

        merged["task_description"] = description
        logger.info(
            "Enriched GEPA reflection context: agent=%s, prompts=%d, "
            "context_length=%d",
            agent_code,
            len(prompt_names),
            len(description),
        )
        return merged
