"""SkillRegistryReader — loads skills.yaml from any agent service (US-052).

Provides read-only access to the standardized skills.yaml files created
by US-051 across all 15 Zorven agent services. Supports skill lookup by
ID and prompt-name slug matching for the GEPA optimization pipeline.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from app.registries.skill_definitions import SkillDefinition, SkillsFile

# Agent code → service directory name
AGENT_SERVICE_DIRS: dict[str, str] = {
    "mra": "market-research-agent-svc",
    "cia": "competitor-intel-agent-svc",
    "apa": "audience-persona-agent-svc",
    "tcia": "trend-cultural-agent-svc",
    "voca": "voc-agent-svc",
    "bpa": "brand-positioning-agent-svc",
    "baa": "brand-architecture-agent-svc",
    "bpv": "brand-personality-agent-svc",
    "nta": "brand-naming-agent-svc",
    "bsa": "brand-story-agent-svc",
    "caa": "campaign-architecture-agent-svc",
    "cga": "creative-generation-agent-svc",
    "adpub": "ad-publishing-agent-svc",
    "coa": "campaign-optimization-agent-svc",
    "ila": "intelligence-loop-agent-svc",
}

# Prompt naming pattern: zorven-wf{N}-{agent_code}-{slug}
PROMPT_NAME_PATTERN = re.compile(r"^zorven-wf[123]-([a-z]+)-(.+)$")


def _default_repo_root() -> Path:
    """Resolve the monorepo root (4 levels up from this file)."""
    return Path(__file__).resolve().parent.parent.parent.parent


class SkillRegistryReader:
    """Read-only loader for agent skills.yaml files."""

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self._repo_root = repo_root or _default_repo_root()
        self._cache: dict[str, SkillsFile] = {}

    def _skill_path(self, agent_code: str) -> Path:
        svc_dir = AGENT_SERVICE_DIRS.get(agent_code)
        if svc_dir is None:
            raise ValueError(
                f"Unknown agent code '{agent_code}'. "
                f"Valid codes: {sorted(AGENT_SERVICE_DIRS.keys())}"
            )
        return self._repo_root / svc_dir / "config" / "skills.yaml"

    def load_skills(self, agent_code: str) -> SkillsFile:
        """Load and validate all skills for an agent.

        Raises ValueError for unknown agent_code,
        FileNotFoundError for missing YAML.
        """
        if agent_code in self._cache:
            return self._cache[agent_code]

        path = self._skill_path(agent_code)
        with open(path) as f:
            raw = yaml.safe_load(f)

        skills_file = SkillsFile(**raw)
        self._cache[agent_code] = skills_file
        return skills_file

    def get_skill(self, agent_code: str, skill_id: str) -> Optional[SkillDefinition]:
        """Look up a single skill by agent code and skill_id."""
        skills_file = self.load_skills(agent_code)
        for skill in skills_file.skills:
            if skill.skill_id == skill_id:
                return skill
        return None

    def get_skill_for_prompt(
        self, agent_code: str, prompt_name: str
    ) -> Optional[SkillDefinition]:
        """Match a prompt name to a skill via slug matching.

        Prompt naming convention: zorven-wf{N}-{agent_code}-{skill_slug}
        Example: 'zorven-wf1-mra-synthesis' → slug='synthesis'

        The slug is matched against skill.name using case-insensitive
        substring matching.
        """
        slug = extract_slug(prompt_name)
        if slug is None:
            return None

        skills_file = self.load_skills(agent_code)
        slug_lower = slug.lower()

        for skill in skills_file.skills:
            if slug_lower in skill.name.lower():
                return skill
        return None

    def list_agent_codes(self) -> list[str]:
        """Return all 15 supported agent codes."""
        return sorted(AGENT_SERVICE_DIRS.keys())

    def all_skills(self) -> list[tuple[str, SkillDefinition]]:
        """Return (agent_code, SkillDefinition) for every skill across all agents."""
        results: list[tuple[str, SkillDefinition]] = []
        for agent_code in sorted(AGENT_SERVICE_DIRS.keys()):
            skills_file = self.load_skills(agent_code)
            for skill in skills_file.skills:
                results.append((agent_code, skill))
        return results

    def clear_cache(self) -> None:
        """Clear the internal cache, forcing re-reads from disk."""
        self._cache.clear()


def extract_slug(prompt_name: str) -> Optional[str]:
    """Extract the skill slug from a prompt name.

    'zorven-wf1-mra-synthesis' → 'synthesis'
    'zorven-wf2-bpa-positioning' → 'positioning'
    'zorven-wf3-cga-compliance' → 'compliance'
    """
    match = PROMPT_NAME_PATTERN.match(prompt_name)
    if match:
        return match.group(2)
    return None
