"""WF2 brand strategy scorers."""

from app.scorers.wf2.architecture_coherence import architecture_coherence
from app.scorers.wf2.name_quality import name_quality
from app.scorers.wf2.narrative_engagement import narrative_engagement
from app.scorers.wf2.positioning_clarity import positioning_clarity
from app.scorers.wf2.voice_consistency import voice_consistency

WF2_SCORERS = [
    positioning_clarity,
    architecture_coherence,
    voice_consistency,
    name_quality,
    narrative_engagement,
]

__all__ = [
    "WF2_SCORERS",
    "positioning_clarity",
    "architecture_coherence",
    "voice_consistency",
    "name_quality",
    "narrative_engagement",
]
