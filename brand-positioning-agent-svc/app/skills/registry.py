"""Skill registry for the Brand Positioning Agent.

12 skills (SKL-BPA-01 through SKL-BPA-12) organized in 3 phases:
  Phase 1 — Research (parallel): 01-05
  Phase 2 — Synthesis (sequential): 06-10
  Phase 3 — Persist + Escalation: 11-12
"""

import logging

logger = logging.getLogger(__name__)

SKILL_CATALOG = [
    {
        "skill_id": "SKL-BPA-01",
        "name": "competitive_mapper",
        "phase": "research",
        "description": "Analyze CIA competitor matrix, map perceptual space",
    },
    {
        "skill_id": "SKL-BPA-02",
        "name": "needs_synthesizer",
        "phase": "research",
        "description": "Synthesize APA + VoCA into needs hierarchy",
    },
    {
        "skill_id": "SKL-BPA-03",
        "name": "trend_scanner",
        "phase": "research",
        "description": "Analyze TCIA trends for positioning alignment",
    },
    {
        "skill_id": "SKL-BPA-04",
        "name": "identity_loader",
        "phase": "research",
        "description": "Load brand identity context",
    },
    {
        "skill_id": "SKL-BPA-05",
        "name": "rag_retriever",
        "phase": "research",
        "description": "Retrieve prior positioning from RAG store",
    },
    {
        "skill_id": "SKL-BPA-06",
        "name": "positioning_generator",
        "phase": "synthesis",
        "description": "Generate framework-agnostic positioning candidates",
    },
    {
        "skill_id": "SKL-BPA-07",
        "name": "canvas_builder",
        "phase": "synthesis",
        "description": "Build Value Proposition Canvas",
    },
    {
        "skill_id": "SKL-BPA-08",
        "name": "perceptual_mapper",
        "phase": "synthesis",
        "description": "Generate perceptual maps with migration vectors",
    },
    {
        "skill_id": "SKL-BPA-09",
        "name": "differentiation_builder",
        "phase": "synthesis",
        "description": "Build POPs/PODs/RTBs differentiation framework",
    },
    {
        "skill_id": "SKL-BPA-10",
        "name": "strategy_synthesizer",
        "phase": "synthesis",
        "description": "Assemble capstone strategy document",
    },
    {
        "skill_id": "SKL-BPA-11",
        "name": "strategy_persister",
        "phase": "persist",
        "description": "Persist strategy to GCS + RAG + Redis",
    },
    {
        "skill_id": "SKL-BPA-12",
        "name": "human_escalation",
        "phase": "persist",
        "description": "Evaluate escalation triggers",
    },
]


class SkillRegistry:
    """Registry for BPA skills."""

    def __init__(self) -> None:
        self._skills = {s["skill_id"]: s for s in SKILL_CATALOG}

    def get_skill(self, skill_id: str) -> dict | None:
        """Get a skill by ID."""
        return self._skills.get(skill_id)

    def get_all_skills(self) -> dict:
        """Return all registered skills."""
        return dict(self._skills)

    def skill_ids(self) -> list[str]:
        """Return all skill IDs."""
        return list(self._skills.keys())

    def skills_by_phase(self, phase: str) -> list[dict]:
        """Return skills for a given phase."""
        return [s for s in self._skills.values() if s["phase"] == phase]
