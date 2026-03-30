"""Skill registry for the BSA service — 14 skills."""

import logging

logger = logging.getLogger(__name__)

SKILL_CATALOG = [
    {
        "id": "SKL-BSA-01",
        "name": "WF2 Strategy Context Loader",
        "module": "app.logic.wf2_strategy_context_loader",
        "class": "WF2StrategyContextLoader",
        "phase": "research",
        "description": "Load full WF2 strategy context (all prior agents) + Company seeds",
    },
    {
        "id": "SKL-BSA-02",
        "name": "Audience Emotional Synthesizer",
        "module": "app.logic.audience_emotional_synthesizer",
        "class": "AudienceEmotionalSynthesizer",
        "phase": "research",
        "description": "Synthesize APA emotional drivers + VoCA language patterns into emotional arc",
    },
    {
        "id": "SKL-BSA-03",
        "name": "Cultural Narrative Scanner",
        "module": "app.logic.cultural_narrative_scanner",
        "class": "CulturalNarrativeScanner",
        "phase": "research",
        "description": "TCIA cultural trends mapped to narrative patterns (rising/fading)",
    },
    {
        "id": "SKL-BSA-04",
        "name": "Existing Narrative Analyzer",
        "module": "app.logic.existing_narrative_analyzer",
        "class": "ExistingNarrativeAnalyzer",
        "phase": "research",
        "description": "Analyze Company model seeds vs BPA/BPV alignment gap analysis",
    },
    {
        "id": "SKL-BSA-05",
        "name": "Competitor Narrative Mapper",
        "module": "app.logic.competitor_narrative_mapper",
        "class": "CompetitorNarrativeMapper",
        "phase": "research",
        "description": "CIA competitor story archetypes mapped to narrative white space",
    },
    {
        "id": "SKL-BSA-06",
        "name": "Origin Story Crafter",
        "module": "app.logic.origin_story_crafter",
        "class": "OriginStoryCrafter",
        "phase": "generation",
        "description": "Build Claude prompt for origin story (3 versions: 500/800/1500 words)",
    },
    {
        "id": "SKL-BSA-07",
        "name": "Mission Vision Refiner",
        "module": "app.logic.mission_vision_refiner",
        "class": "MissionVisionRefiner",
        "phase": "generation",
        "description": "Build Claude prompt for mission/vision (refine existing or generate new)",
    },
    {
        "id": "SKL-BSA-08",
        "name": "Elevator Pitch Generator",
        "module": "app.logic.elevator_pitch_generator",
        "class": "ElevatorPitchGenerator",
        "phase": "generation",
        "description": "Build Claude prompt for pitches (15s/30s/60s at 150 wpm)",
    },
    {
        "id": "SKL-BSA-09",
        "name": "Channel Narrative Adapter",
        "module": "app.logic.channel_narrative_adapter",
        "class": "ChannelNarrativeAdapter",
        "phase": "synthesis",
        "description": "Build Claude prompt for channel-specific narratives",
    },
    {
        "id": "SKL-BSA-10",
        "name": "Story Style Guide Builder",
        "module": "app.logic.story_style_guide_builder",
        "class": "StoryStyleGuideBuilder",
        "phase": "synthesis",
        "description": "Build Claude prompt for story style guide",
    },
    {
        "id": "SKL-BSA-11",
        "name": "Sub-Brand Story Variation",
        "module": "app.logic.subbrand_story_variation",
        "class": "SubBrandStoryVariation",
        "phase": "synthesis",
        "description": "Sub-brand story variation (if BAA + brand_context_id)",
    },
    {
        "id": "SKL-BSA-12",
        "name": "Brand Narrative Synthesizer",
        "module": "app.logic.brand_narrative_synthesizer",
        "class": "BrandNarrativeSynthesizer",
        "phase": "synthesis",
        "description": "Capstone: assemble all artifacts into final narrative package",
    },
    {
        "id": "SKL-BSA-13",
        "name": "Story Persister",
        "module": "app.logic.story_persister",
        "class": "StoryPersister",
        "phase": "persist",
        "description": "Persist narrative results to Redis cache + GCS",
    },
    {
        "id": "SKL-BSA-14",
        "name": "Human Escalation",
        "module": "app.logic.human_escalation",
        "class": "HumanEscalation",
        "phase": "persist",
        "description": "Confidence threshold check for human review",
    },
]


class SkillRegistry:
    """Registry of BSA executable skills."""

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
