"""Skill registry for the Brand Architecture Agent.

12 skills (SKL-BAA-01 through SKL-BAA-12) organized in 3 phases:
  Phase 1 — Research (parallel): 01-05
  Phase 2 — Architecture Design (sequential): 06-10
  Phase 3 — Persist + Escalation: 11-12
"""

import logging

logger = logging.getLogger(__name__)

SKILL_CATALOG = [
    {
        "skill_id": "SKL-BAA-01",
        "name": "competitor_arch_analyzer",
        "phase": "research",
        "description": "Analyze competitor brand architecture patterns from CIA data",
    },
    {
        "skill_id": "SKL-BAA-02",
        "name": "audience_alignment",
        "phase": "research",
        "description": "Align APA + VoCA personas with BPA needs hierarchy",
    },
    {
        "skill_id": "SKL-BAA-03",
        "name": "portfolio_loader",
        "phase": "research",
        "description": "Load Company model + Odoo product portfolio",
    },
    {
        "skill_id": "SKL-BAA-04",
        "name": "positioning_loader",
        "phase": "research",
        "description": "Load BPA positioning strategy as architecture input",
    },
    {
        "skill_id": "SKL-BAA-05",
        "name": "rag_retriever",
        "phase": "research",
        "description": "Retrieve prior architecture docs from RAG store",
    },
    {
        "skill_id": "SKL-BAA-06",
        "name": "model_recommender",
        "phase": "design",
        "description": "Score 5 architecture models (4 dims x 0-25 = 0-100)",
    },
    {
        "skill_id": "SKL-BAA-07",
        "name": "hierarchy_builder",
        "phase": "design",
        "description": "Build brand hierarchy tree (JSON for React Flow)",
    },
    {
        "skill_id": "SKL-BAA-08",
        "name": "naming_designer",
        "phase": "design",
        "description": "Design naming patterns + consistency scoring",
    },
    {
        "skill_id": "SKL-BAA-09",
        "name": "growth_planner",
        "phase": "design",
        "description": "Plan phased portfolio growth roadmap",
    },
    {
        "skill_id": "SKL-BAA-10",
        "name": "strategy_synthesizer",
        "phase": "design",
        "description": "Assemble capstone architecture strategy document",
    },
    {
        "skill_id": "SKL-BAA-11",
        "name": "strategy_persister",
        "phase": "persist",
        "description": "Persist strategy to GCS + RAG + Redis registry",
    },
    {
        "skill_id": "SKL-BAA-12",
        "name": "human_escalation",
        "phase": "persist",
        "description": "Evaluate escalation triggers (low confidence, misalignment)",
    },
]


class SkillRegistry:
    """Registry for BAA skills."""

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
