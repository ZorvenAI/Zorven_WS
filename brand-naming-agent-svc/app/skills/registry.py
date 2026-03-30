"""Skill registry for the NTA service — 14 skills."""

import logging

logger = logging.getLogger(__name__)

SKILL_CATALOG = [
    {
        "id": "SKL-NTA-01",
        "name": "Brand Context Loader",
        "module": "app.logic.brand_context_loader",
        "class": "BrandContextLoader",
        "phase": "research",
        "description": "Load brand context from BAA hierarchy for sub-brand naming constraints",
    },
    {
        "id": "SKL-NTA-02",
        "name": "Audience Psychology Analyzer",
        "module": "app.logic.audience_psychology_analyzer",
        "class": "AudiencePsychologyAnalyzer",
        "phase": "research",
        "description": "Analyze audience psychographics for name resonance",
    },
    {
        "id": "SKL-NTA-03",
        "name": "Competitive Naming Analyzer",
        "module": "app.logic.competitive_naming_analyzer",
        "class": "CompetitiveNamingAnalyzer",
        "phase": "research",
        "description": "Analyze competitor naming patterns, identify white space",
    },
    {
        "id": "SKL-NTA-04",
        "name": "Identity Seed Loader",
        "module": "app.logic.identity_seed_loader",
        "class": "IdentitySeedLoader",
        "phase": "research",
        "description": "Load identity/values from BPV (Aaker dimensions, archetype, values)",
    },
    {
        "id": "SKL-NTA-05",
        "name": "RAG Retriever",
        "module": "app.logic.rag_retriever",
        "class": "RAGRetriever",
        "phase": "research",
        "description": "Retrieve relevant naming docs from Vertex AI RAG",
    },
    {
        "id": "SKL-NTA-06",
        "name": "Domain Checker",
        "module": "app.logic.domain_checker",
        "class": "DomainChecker",
        "phase": "availability",
        "description": "DNS lookup for .com/.io/.co availability",
    },
    {
        "id": "SKL-NTA-07",
        "name": "Social Handle Checker",
        "module": "app.logic.social_handle_checker",
        "class": "SocialHandleChecker",
        "phase": "availability",
        "description": "HTTP HEAD for Twitter/Instagram/LinkedIn handle availability",
    },
    {
        "id": "SKL-NTA-08",
        "name": "Trademark Searcher",
        "module": "app.logic.trademark_searcher",
        "class": "TrademarkSearcher",
        "phase": "availability",
        "description": "Tavily web search for existing trademark conflicts",
    },
    {
        "id": "SKL-NTA-09",
        "name": "Name Generator",
        "module": "app.logic.name_generator",
        "class": "NameGenerator",
        "phase": "generation",
        "description": "Build Claude system/user prompt for name generation",
    },
    {
        "id": "SKL-NTA-10",
        "name": "Name Scorer",
        "module": "app.logic.name_scorer",
        "class": "NameScorer",
        "phase": "generation",
        "description": "Multi-dimensional scoring: linguistic, memorability, availability, strategy alignment",
    },
    {
        "id": "SKL-NTA-11",
        "name": "Tagline Synthesizer",
        "module": "app.logic.tagline_synthesizer",
        "class": "TaglineSynthesizer",
        "phase": "synthesis",
        "description": "Build Claude prompt for tagline generation for shortlisted names",
    },
    {
        "id": "SKL-NTA-12",
        "name": "Naming Brief Builder",
        "module": "app.logic.naming_brief_builder",
        "class": "NamingBriefBuilder",
        "phase": "synthesis",
        "description": "Compile final naming brief document",
    },
    {
        "id": "SKL-NTA-13",
        "name": "Naming Persister",
        "module": "app.logic.naming_persister",
        "class": "NamingPersister",
        "phase": "persist",
        "description": "Persist naming results to Django Redis cache + GCS + RAG",
    },
    {
        "id": "SKL-NTA-14",
        "name": "Human Escalation",
        "module": "app.logic.human_escalation",
        "class": "HumanEscalation",
        "phase": "persist",
        "description": "Confidence threshold check for human review",
    },
]


class SkillRegistry:
    """Registry of NTA executable skills."""

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
