"""Skill registry for the BPV service — 12 skills."""

import logging

logger = logging.getLogger(__name__)

SKILL_CATALOG = [
    {
        "id": "SKL-BPV-01",
        "name": "Audience Psychology Analyzer",
        "module": "app.logic.audience_psychology_analyzer",
        "class": "AudiencePsychologyAnalyzer",
        "phase": "research",
        "description": "Extract psychographics from APA + VoCA data",
    },
    {
        "id": "SKL-BPV-02",
        "name": "Brand Perception Analyzer",
        "module": "app.logic.brand_perception_analyzer",
        "class": "BrandPerceptionAnalyzer",
        "phase": "research",
        "description": "Extract brand perception from VoCA + TCIA data",
    },
    {
        "id": "SKL-BPV-03",
        "name": "Identity Values Seed Loader",
        "module": "app.logic.identity_values_seed_loader",
        "class": "IdentityValuesSeedLoader",
        "phase": "research",
        "description": "Map Company.brand_voice to Aaker seed weights",
    },
    {
        "id": "SKL-BPV-04",
        "name": "RAG Retriever",
        "module": "app.logic.rag_retriever",
        "class": "RAGRetriever",
        "phase": "research",
        "description": "Retrieve prior personality documents (stub v2)",
    },
    {
        "id": "SKL-BPV-05",
        "name": "Aaker Profiler",
        "module": "app.logic.aaker_profiler",
        "class": "AakerProfiler",
        "phase": "design",
        "description": "Validate/normalize Aaker 5D personality scores",
    },
    {
        "id": "SKL-BPV-06",
        "name": "Archetype Selector",
        "module": "app.logic.archetype_selector",
        "class": "ArchetypeSelector",
        "phase": "design",
        "description": "Validate Jungian archetype selection",
    },
    {
        "id": "SKL-BPV-07",
        "name": "Values Hierarchy Builder",
        "module": "app.logic.values_hierarchy_builder",
        "class": "ValuesHierarchyBuilder",
        "phase": "design",
        "description": "Validate values tiers (core/supporting/aspirational)",
    },
    {
        "id": "SKL-BPV-08",
        "name": "Emotional Attribute Mapper",
        "module": "app.logic.emotional_attribute_mapper",
        "class": "EmotionalAttributeMapper",
        "phase": "design",
        "description": "Validate per-persona emotional intensity scores",
    },
    {
        "id": "SKL-BPV-09",
        "name": "Voice Matrix Designer",
        "module": "app.logic.voice_matrix_designer",
        "class": "VoiceMatrixDesigner",
        "phase": "design",
        "description": "Validate voice matrix structure",
    },
    {
        "id": "SKL-BPV-10",
        "name": "Character Brief Synthesizer",
        "module": "app.logic.character_brief_synthesizer",
        "class": "CharacterBriefSynthesizer",
        "phase": "design",
        "description": "Validate character brief + positioning alignment",
    },
    {
        "id": "SKL-BPV-11",
        "name": "Personality Persister",
        "module": "app.logic.personality_persister",
        "class": "PersonalityPersister",
        "phase": "persist",
        "description": "Redis registry persistence + Django brand context sync",
    },
    {
        "id": "SKL-BPV-12",
        "name": "Human Escalation",
        "module": "app.logic.human_escalation",
        "class": "HumanEscalation",
        "phase": "persist",
        "description": "Confidence threshold check for human review",
    },
]


class SkillRegistry:
    """Registry of BPV executable skills."""

    def __init__(self):
        self._skills = {s["id"]: s for s in SKILL_CATALOG}

    def get_skill(self, skill_id: str) -> dict | None:
        """Get skill by ID."""
        return self._skills.get(skill_id)

    def list_skills(self) -> list[dict]:
        """List all registered skills."""
        return SKILL_CATALOG

    @property
    def count(self) -> int:
        """Number of registered skills."""
        return len(self._skills)
