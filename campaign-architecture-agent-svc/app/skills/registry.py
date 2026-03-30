"""Skill registry for the CAA service — 12 skills."""

import logging

logger = logging.getLogger(__name__)

SKILL_CATALOG = [
    {
        "id": "SKL-CAA-01",
        "name": "Strategy Context Loader",
        "module": "app.logic.strategy_context_loader",
        "class": "StrategyContextLoader",
        "phase": "research",
        "description": ("Consolidate WF1+WF2+Company into CampaignStrategyContext"),
    },
    {
        "id": "SKL-CAA-02",
        "name": "Market Benchmark Researcher",
        "module": "app.logic.market_benchmark_researcher",
        "class": "MarketBenchmarkResearcher",
        "phase": "research",
        "description": ("Tavily search for industry CPM/CTR/CPC/CPA/ROAS benchmarks"),
    },
    {
        "id": "SKL-CAA-03",
        "name": "Competitor Ad Analyzer",
        "module": "app.logic.competitor_ad_analyzer",
        "class": "CompetitorAdAnalyzer",
        "phase": "research",
        "description": ("Tavily search for competitor ad patterns (Meta Ad Library)"),
    },
    {
        "id": "SKL-CAA-04",
        "name": "Odoo Customer Loader",
        "module": "app.logic.odoo_customer_loader",
        "class": "OdooCustomerLoader",
        "phase": "research",
        "description": (
            "Extract customer segments from Odoo for custom/lookalike audiences"
        ),
    },
    {
        "id": "SKL-CAA-05",
        "name": "RAG Intelligence Retriever",
        "module": "app.logic.rag_intelligence_retriever",
        "class": "RAGIntelligenceRetriever",
        "phase": "research",
        "description": (
            "Search RAG for prior campaign learnings (empty for first campaign)"
        ),
    },
    {
        "id": "SKL-CAA-06",
        "name": "Funnel Objective Mapper",
        "module": "app.logic.funnel_objective_mapper",
        "class": "FunnelObjectiveMapper",
        "phase": "synthesis",
        "description": (
            "Build prompt: funnel stage -> Meta objective mapping, budget %"
        ),
    },
    {
        "id": "SKL-CAA-07",
        "name": "Audience Targeting Builder",
        "module": "app.logic.audience_targeting_builder",
        "class": "AudienceTargetingBuilder",
        "phase": "synthesis",
        "description": ("Build prompt: APA personas -> Meta targeting specs"),
    },
    {
        "id": "SKL-CAA-08",
        "name": "Placement Budget Builder",
        "module": "app.logic.placement_budget_builder",
        "class": "PlacementBudgetBuilder",
        "phase": "synthesis",
        "description": ("Build prompt: placement strategy, CBO/ABO, budget allocation"),
    },
    {
        "id": "SKL-CAA-09",
        "name": "A/B Test Planner",
        "module": "app.logic.ab_test_planner",
        "class": "ABTestPlanner",
        "phase": "synthesis",
        "description": (
            "Build prompt: A/B test plan (variables, variants, sample sizes)"
        ),
    },
    {
        "id": "SKL-CAA-10",
        "name": "Blueprint Synthesizer",
        "module": "app.logic.blueprint_synthesizer",
        "class": "BlueprintSynthesizer",
        "phase": "synthesis",
        "description": ("Capstone: assemble full CampaignBlueprint JSON"),
    },
    {
        "id": "SKL-CAA-11",
        "name": "Blueprint Persister",
        "module": "app.logic.blueprint_persister",
        "class": "BlueprintPersister",
        "phase": "persist",
        "description": ("Persist blueprint to Redis cache + GCS for downstream agents"),
    },
    {
        "id": "SKL-CAA-12",
        "name": "Human Escalation",
        "module": "app.logic.human_escalation",
        "class": "HumanEscalation",
        "phase": "persist",
        "description": (
            "Confidence < 0.7, unrealistic KPIs, budget issues -> escalate"
        ),
    },
]


class SkillRegistry:
    """Registry of CAA executable skills."""

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
