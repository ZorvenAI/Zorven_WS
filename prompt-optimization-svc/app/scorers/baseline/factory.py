"""Baseline Scorer Factory — auto-generates scorers from output schema (US-054).

Creates MLflow GEPA-compatible scorer functions from a SkillDefinition's
output_schema fields. Each generated scorer validates a specific constraint
(field presence, max length, enum compliance) and returns Feedback.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.registries.skill_definitions import SkillDefinition
from app.scorers.baseline.checks import (
    make_enum_compliance_scorer,
    make_field_presence_scorer,
    make_max_length_scorer,
    make_schema_completeness_scorer,
)
from app.services.skill_registry_reader import SkillRegistryReader


class BaselineScorerFactory:
    """Generates baseline scorers from skill output schemas."""

    def __init__(self, skill_registry_reader: SkillRegistryReader) -> None:
        self._reader = skill_registry_reader

    def create_scorers(self, skill: SkillDefinition) -> list[Callable]:
        """Generate baseline scorers for a skill's output schema.

        Creates up to 3 types of scorers per output field:
        1. field_presence — required field exists in output
        2. max_length — string field within max_length constraint
        3. enum_compliance — field value in allowed enum_values
        Plus one aggregate scorer:
        4. schema_completeness — fraction of required fields present
        """
        scorers: list[Callable] = []
        required_fields: list[str] = []

        for field in skill.output_schema:
            # Field presence for required fields
            if field.required:
                required_fields.append(field.field)
                scorers.append(make_field_presence_scorer(field.field, skill.skill_id))

            # Max length check
            if field.max_length is not None:
                scorers.append(
                    make_max_length_scorer(
                        field.field, field.max_length, skill.skill_id
                    )
                )

            # Enum compliance check
            if field.enum_values:
                scorers.append(
                    make_enum_compliance_scorer(
                        field.field, field.enum_values, skill.skill_id
                    )
                )

        # Always add schema completeness scorer
        scorers.append(make_schema_completeness_scorer(required_fields, skill.skill_id))

        return scorers

    def create_scorers_for_prompt(
        self, agent_code: str, prompt_name: str
    ) -> list[Callable]:
        """Look up skill for a prompt and generate its baseline scorers.

        Returns empty list if no skill match found.
        """
        skill = self._reader.get_skill_for_prompt(agent_code, prompt_name)
        if skill is None:
            return []
        return self.create_scorers(skill)
