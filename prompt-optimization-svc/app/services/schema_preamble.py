"""Schema Preamble Generator — auto-generate and inject protected schema zones (US-053).

Generates a structured text preamble from a SkillDefinition's input/output
schemas, marks it with delimiters so GEPA optimization cannot modify it,
and provides utilities to inject, extract, and strip preambles from prompts.
"""

from __future__ import annotations

import re
from typing import Optional

from app.registries.skill_definitions import SkillDefinition
from app.services.skill_registry_reader import SkillRegistryReader

# Protected zone delimiters
PREAMBLE_START = "<!-- SCHEMA_PREAMBLE_START -->"
PREAMBLE_END = "<!-- SCHEMA_PREAMBLE_END -->"

# Regex to match the full preamble block (including markers)
_PREAMBLE_PATTERN = re.compile(
    re.escape(PREAMBLE_START) + r".*?" + re.escape(PREAMBLE_END),
    re.DOTALL,
)


class SchemaPreambleGenerator:
    """Generates and manages schema preambles for prompt protection."""

    def __init__(self, skill_registry_reader: SkillRegistryReader) -> None:
        self._reader = skill_registry_reader

    def generate(self, skill: SkillDefinition) -> str:
        """Generate a schema preamble from a SkillDefinition.

        Returns a structured block with input/output schema tables,
        wrapped in PREAMBLE_START/END markers.
        """
        lines = [
            PREAMBLE_START,
            "[SCHEMA CONSTRAINT — DO NOT MODIFY]",
            f"Skill: {skill.skill_id} ({skill.name})",
            "",
            "## Expected Input",
            "| Field | Type | Required |",
            "|-------|------|----------|",
        ]

        for field in skill.input_schema:
            field_name = field.get("field", "unknown")
            field_type = field.get("type", "unknown")
            required = "yes" if field.get("required", True) else "no"
            lines.append(f"| {field_name} | {field_type} | {required} |")

        lines.append("")
        lines.append("## Required Output")
        lines.append("| Field | Type | Max Length |")
        lines.append("|-------|------|-----------|")

        for field in skill.output_schema:
            max_len = str(field.max_length) if field.max_length else "—"
            lines.append(f"| {field.field} | {field.type} | {max_len} |")

        lines.append("")
        idempotent_str = "yes" if skill.idempotent else "no"
        lines.append(f"Timeout: {skill.timeout_ms}ms | Idempotent: {idempotent_str}")
        lines.append(PREAMBLE_END)

        return "\n".join(lines)

    def generate_for_prompt(self, agent_code: str, prompt_name: str) -> Optional[str]:
        """Look up the skill for a prompt and generate its preamble.

        Returns None if no skill match found.
        """
        skill = self._reader.get_skill_for_prompt(agent_code, prompt_name)
        if skill is None:
            return None
        return self.generate(skill)

    def inject(self, prompt_template: str, preamble: str) -> str:
        """Prepend the preamble to a prompt template.

        If a preamble already exists in the template, it is replaced.
        The content portion is stripped to ensure idempotent injection.
        """
        if self.is_protected(prompt_template):
            content = _PREAMBLE_PATTERN.sub("", prompt_template).strip()
        else:
            content = prompt_template.strip()
        return preamble + "\n\n" + content

    def strip(self, prompt_text: str) -> str:
        """Remove the preamble section from prompt text."""
        if not self.is_protected(prompt_text):
            return prompt_text
        result = _PREAMBLE_PATTERN.sub("", prompt_text)
        return result.strip()

    def extract(self, prompt_text: str) -> Optional[str]:
        """Extract the preamble section from prompt text, or None."""
        match = _PREAMBLE_PATTERN.search(prompt_text)
        if match:
            return match.group(0)
        return None

    def is_protected(self, prompt_text: str) -> bool:
        """Check if prompt text contains a valid schema preamble block."""
        return self.extract(prompt_text) is not None

    def has_changed(self, prompt_text: str, skill: SkillDefinition) -> bool:
        """Check if the embedded preamble differs from current skill schema.

        Returns True if the preamble is missing or outdated.
        """
        existing = self.extract(prompt_text)
        if existing is None:
            return True
        current = self.generate(skill)
        return existing != current
