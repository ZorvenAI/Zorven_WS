"""Prompt naming convention validator (§3.1).

Pattern: zorven-wf<n>-<agent_code>-<skill>[-<variant>]

Examples:
    zorven-wf1-mra-landscape           # Standard skill prompt
    zorven-wf1-mra-landscape-v2        # Variant
    zorven-wf1-mra-system              # System prompt
    zorven-wf1-mra-planner             # Planner prompt (PG-01)
    zorven-wf3-cga-creative-v3         # WF3 variant
"""

import re
from dataclasses import dataclass
from typing import Optional

# Valid agent codes per workflow
VALID_AGENT_CODES: dict[int, set[str]] = {
    1: {"mra", "cia", "apa", "tcia", "voca"},
    2: {"bpa", "baa", "bpv", "nta", "bsa"},
    3: {"caa", "cga", "adpub", "coa", "ila"},
}

ALL_AGENT_CODES: set[str] = set()
for codes in VALID_AGENT_CODES.values():
    ALL_AGENT_CODES |= codes

# Reserved skill names that are always valid
RESERVED_SKILLS = {"system", "planner"}

# Regex for structural validation
_NAME_PATTERN = re.compile(
    r"^zorven-wf([1-3])-([a-z][a-z0-9]*)-([a-z][a-z0-9_]*)(?:-([a-z0-9][a-z0-9_]*))?$"
)

EXPECTED_FORMAT = "zorven-wf<1|2|3>-<agent_code>-<skill>[-<variant>]"


@dataclass(frozen=True)
class PromptNameParts:
    """Parsed components of a validated prompt name."""

    workflow: int
    agent_code: str
    skill: str
    variant: Optional[str] = None

    @property
    def is_system(self) -> bool:
        return self.skill == "system"

    @property
    def is_planner(self) -> bool:
        return self.skill == "planner"

    @property
    def base_name(self) -> str:
        """Name without variant suffix."""
        return f"zorven-wf{self.workflow}-{self.agent_code}-{self.skill}"

    @property
    def full_name(self) -> str:
        """Full name including variant if present."""
        if self.variant:
            return f"{self.base_name}-{self.variant}"
        return self.base_name


def validate_prompt_name(name: str) -> PromptNameParts:
    """Validate a prompt name against the §3.1 naming convention.

    Args:
        name: The prompt name to validate.

    Returns:
        Parsed PromptNameParts on success.

    Raises:
        ValueError: If the name is invalid, with a corrective message.
    """
    if not name:
        raise ValueError(
            f"Prompt name cannot be empty. Expected format: {EXPECTED_FORMAT}"
        )

    match = _NAME_PATTERN.match(name)
    if not match:
        raise ValueError(
            f"Invalid prompt name '{name}'. "
            f"Expected format: {EXPECTED_FORMAT}. "
            f"Names must be lowercase with hyphens. "
            f"Valid agent codes: {', '.join(sorted(ALL_AGENT_CODES))}"
        )

    workflow = int(match.group(1))
    agent_code = match.group(2)
    skill = match.group(3)
    variant = match.group(4)

    # Validate agent code belongs to the specified workflow
    if agent_code not in VALID_AGENT_CODES[workflow]:
        valid_for_wf = ", ".join(sorted(VALID_AGENT_CODES[workflow]))
        raise ValueError(
            f"Agent code '{agent_code}' is not valid for workflow {workflow}. "
            f"Valid WF{workflow} agent codes: {valid_for_wf}. "
            f"Use the correct workflow number for this agent."
        )

    return PromptNameParts(
        workflow=workflow,
        agent_code=agent_code,
        skill=skill,
        variant=variant,
    )
